"""
Remote Read-Only Commands for PicoClaw Phase 2
Safe commands that can be executed by remote workers without write permissions
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from engine.utils import ROOT


@dataclass
class CommandResult:
    """Result of a remote command execution"""
    success: bool
    command: str
    stdout: str
    stderr: str
    exit_code: int
    metadata: dict[str, Any]


# Registry of available read-only commands
READONLY_COMMANDS: dict[str, Callable[..., CommandResult]] = {}


def register_readonly_command(name: str) -> Callable:
    """Decorator to register a read-only command"""
    def decorator(func: Callable[..., CommandResult]) -> Callable[..., CommandResult]:
        READONLY_COMMANDS[name] = func
        return func
    return decorator


def execute_readonly_command(
    command_name: str,
    args: dict[str, Any] | None = None,
    cwd: Path | None = None,
) -> CommandResult:
    """
    Execute a registered read-only command
    
    Args:
        command_name: Name of the command to execute
        args: Arguments for the command
        cwd: Working directory (ignored for safety)
    
    Returns:
        CommandResult with execution details
    """
    if command_name not in READONLY_COMMANDS:
        return CommandResult(
            success=False,
            command=command_name,
            stdout="",
            stderr=f"Unknown command: {command_name}",
            exit_code=127,
            metadata={"available_commands": list(READONLY_COMMANDS.keys())},
        )
    
    try:
        return READONLY_COMMANDS[command_name](**(args or {}))
    except Exception as e:
        return CommandResult(
            success=False,
            command=command_name,
            stdout="",
            stderr=f"Command execution failed: {str(e)}",
            exit_code=1,
            metadata={"error_type": type(e).__name__},
        )


def _run_safe_command(
    cmd: list[str],
    command_name: str,
    cwd: Path | None = None,
    timeout: int = 60,
) -> CommandResult:
    """Run a shell command safely"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
        )
        return CommandResult(
            success=result.returncode == 0,
            command=command_name,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            metadata={"timeout": timeout},
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False,
            command=command_name,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            exit_code=124,
            metadata={"timeout": timeout},
        )
    except Exception as e:
        return CommandResult(
            success=False,
            command=command_name,
            stdout="",
            stderr=str(e),
            exit_code=1,
            metadata={"error_type": type(e).__name__},
        )


# ==================== Read-Only Commands ====================

@register_readonly_command("ping")
def cmd_ping(host: str = "127.0.0.1", count: int = 1) -> CommandResult:
    """Ping a host (read-only network check)"""
    return _run_safe_command(
        ["ping", "-n", str(count), host],
        f"ping {host}",
        timeout=30,
    )


@register_readonly_command("system_info")
def cmd_system_info() -> CommandResult:
    """Get basic system information"""
    result = _run_safe_command(["systeminfo"], "systeminfo", timeout=30)
    return result


@register_readonly_command("disk_usage")
def cmd_disk_usage() -> CommandResult:
    """Get disk usage information"""
    return _run_safe_command(["wmic", "logicaldisk", "get", "size,freespace,caption"], "disk_usage")


@register_readonly_command("memory_usage")
def cmd_memory_usage() -> CommandResult:
    """Get memory usage information"""
    return _run_safe_command(
        ["wmic", "computersystem", "get", "totalphysicalmemory"],
        "memory_total",
    )


@register_readonly_command("list_directory")
def cmd_list_directory(path: str = ".") -> CommandResult:
    """List contents of a directory (safely)"""
    # Sanitize path - only allow relative paths within project
    safe_path = Path(path).resolve()
    if not str(safe_path).startswith(str(ROOT.resolve())):
        return CommandResult(
            success=False,
            command=f"list_directory {path}",
            stdout="",
            stderr="Path is outside project directory",
            exit_code=1,
            metadata={},
        )
    
    return _run_safe_command(
        ["dir", "/b", str(safe_path)],
        f"list_directory {path}",
    )


@register_readonly_command("read_file")
def cmd_read_file(path: str, max_lines: int = 100_000) -> CommandResult:
    """Read contents of a file (safely)"""
    # Sanitize path
    safe_path = Path(path).resolve()
    if not str(safe_path).startswith(str(ROOT.resolve())):
        return CommandResult(
            success=False,
            command=f"read_file {path}",
            stdout="",
            stderr="Path is outside project directory",
            exit_code=1,
            metadata={},
        )
    
    if not safe_path.exists():
        return CommandResult(
            success=False,
            command=f"read_file {path}",
            stdout="",
            stderr="File not found",
            exit_code=1,
            metadata={},
        )
    
    if not safe_path.is_file():
        return CommandResult(
            success=False,
            command=f"read_file {path}",
            stdout="",
            stderr="Path is not a file",
            exit_code=1,
            metadata={},
        )
    
    try:
        with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[:max_lines]
            content = "".join(lines)
        
        return CommandResult(
            success=True,
            command=f"read_file {path}",
            stdout=content,
            stderr="",
            exit_code=0,
            metadata={"lines_read": len(lines), "truncated": len(lines) >= max_lines},
        )
    except Exception as e:
        return CommandResult(
            success=False,
            command=f"read_file {path}",
            stdout="",
            stderr=str(e),
            exit_code=1,
            metadata={},
        )


@register_readonly_command("git_status")
def cmd_git_status(repo_path: str = ".") -> CommandResult:
    """Get git status of a repository"""
    safe_path = Path(repo_path).resolve()
    if not str(safe_path).startswith(str(ROOT.resolve())):
        return CommandResult(
            success=False,
            command=f"git_status {repo_path}",
            stdout="",
            stderr="Path is outside project directory",
            exit_code=1,
            metadata={},
        )
    
    return _run_safe_command(
        ["git", "status", "--short"],
        f"git_status {repo_path}",
        cwd=safe_path,
    )


@register_readonly_command("git_log")
def cmd_git_log(repo_path: str = ".", count: int = 10) -> CommandResult:
    """Get recent git log"""
    safe_path = Path(repo_path).resolve()
    if not str(safe_path).startswith(str(ROOT.resolve())):
        return CommandResult(
            success=False,
            command=f"git_log {repo_path}",
            stdout="",
            stderr="Path is outside project directory",
            exit_code=1,
            metadata={},
        )
    
    return _run_safe_command(
        ["git", "log", f"--max-count={count}", "--oneline"],
        f"git_log {repo_path}",
        cwd=safe_path,
    )


@register_readonly_command("env_info")
def cmd_env_info() -> CommandResult:
    """Get environment information (safe only)"""
    safe_vars = [
        "PATH",
        "HOME",
        "USERPROFILE",
        "TEMP",
        "TMP",
        "OS",
        "PROCESSOR_ARCHITECTURE",
        "PYTHON_VERSION",
        "COMPUTERNAME",
    ]
    
    import os
    info = {var: os.environ.get(var, "") for var in safe_vars}
    
    return CommandResult(
        success=True,
        command="env_info",
        stdout=json.dumps(info, indent=2),
        stderr="",
        exit_code=0,
        metadata={"vars_shown": len(safe_vars)},
    )


@register_readonly_command("python_version")
def cmd_python_version() -> CommandResult:
    """Get Python version"""
    import sys
    return CommandResult(
        success=True,
        command="python_version",
        stdout=f"Python {sys.version}",
        stderr="",
        exit_code=0,
        metadata={
            "version": sys.version,
            "version_info": list(sys.version_info),
        },
    )


@register_readonly_command("uptime")
def cmd_uptime() -> CommandResult:
    """Get system uptime"""
    return _run_safe_command(
        ["wmic", "path", "Win32_OperatingSystem", "get", "LastBootUpTime"],
        "uptime",
    )


def get_available_commands() -> dict[str, str]:
    """Get list of available read-only commands with descriptions"""
    return {
        name: func.__doc__ or "No description"
        for name, func in READONLY_COMMANDS.items()
    }


def execute_remote_job_payload(
    payload: dict[str, Any],
    job_id: str | None = None,
) -> CommandResult:
    """
    Execute a remote job payload
    
    Args:
        payload: Job payload containing command and args
        job_id: Optional job ID for logging
    
    Returns:
        CommandResult
    """
    command_name = payload.get("command")
    args = payload.get("args", {})
    
    if not command_name:
        return CommandResult(
            success=False,
            command="",
            stdout="",
            stderr="No command specified in payload",
            exit_code=1,
            metadata={"job_id": job_id},
        )
    
    result = execute_readonly_command(command_name, args)
    result.metadata["job_id"] = job_id
    return result
