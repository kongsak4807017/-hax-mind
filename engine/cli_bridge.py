from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.memory_analyzer import log_event
from engine.proposal_engine import create_proposal
from engine.utils import ROOT, ensure_dir, now_iso


CLI_JOBS_DIR = ROOT / "runtime" / "cli_jobs"
CLI_OUTPUTS_DIR = CLI_JOBS_DIR / "outputs"
CLI_LAUNCHERS_DIR = CLI_JOBS_DIR / "launchers"
CLI_SESSIONS_DIR = CLI_JOBS_DIR / "sessions"
MAX_PROMPT_LENGTH = 4000

CLI_TOOL_PROFILES: dict[str, tuple[str, ...]] = {
    "kimi": ("default", "thinking", "yolo"),
    "gemini": ("default", "plan", "yolo"),
    "codex": ("review", "default", "yolo"),
    "omx": ("review", "default", "yolo"),
}


@dataclass(frozen=True)
class CLITool:
    key: str
    title: str
    mode: str  # interactive | one_shot | hybrid
    executable: str
    scripted_session: bool = False


ALLOWED_CLI_TOOLS: dict[str, CLITool] = {
    "codex": CLITool("codex", "OpenAI Codex CLI", "hybrid", os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd"), scripted_session=True),
    "omx": CLITool("omx", "oh-my-codex", "hybrid", os.path.join(os.environ.get("APPDATA", ""), "npm", "omx.cmd"), scripted_session=True),
    "gemini": CLITool("gemini", "Gemini CLI", "hybrid", os.path.join(os.environ.get("APPDATA", ""), "npm", "gemini.cmd"), scripted_session=True),
    "kimi": CLITool("kimi", "Kimi CLI", "hybrid", shutil.which("kimi") or "kimi", scripted_session=True),
}


def _job_path(job_id: str, root: Path = ROOT) -> Path:
    return root / "runtime" / "cli_jobs" / f"{job_id}.json"


def _session_path(session_id: str, root: Path = ROOT) -> Path:
    return root / "runtime" / "cli_jobs" / "sessions" / f"{session_id}.json"


def _safe_tool_key(value: str) -> str:
    key = value.strip().lower()
    if key not in ALLOWED_CLI_TOOLS:
        raise ValueError(f"Unsupported CLI tool: {value}. Allowed: {', '.join(sorted(ALLOWED_CLI_TOOLS))}")
    return key


def _sanitize_prompt(prompt: str) -> str:
    text = re.sub(r"\s+", " ", prompt.strip())
    if not text:
        raise ValueError("CLI prompt is required")
    if len(text) > MAX_PROMPT_LENGTH:
        raise ValueError(f"CLI prompt is too long ({len(text)} chars); limit is {MAX_PROMPT_LENGTH}")
    return text


def _normalize_profile(tool_key: str, profile: str | None) -> str:
    allowed = CLI_TOOL_PROFILES.get(tool_key, ("default",))
    chosen = (profile or allowed[0]).strip().lower()
    if chosen not in allowed:
        raise ValueError(f"Unsupported profile '{profile}' for {tool_key}. Allowed: {', '.join(allowed)}")
    return chosen


def detect_cli_tools() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key, tool in ALLOWED_CLI_TOOLS.items():
        path = tool.executable
        available = bool(path) and (Path(path).exists() if os.path.isabs(path) else shutil.which(path) is not None)
        records.append(
            {
                "key": key,
                "title": tool.title,
                "mode": tool.mode,
                "executable": path,
                "available": available,
                "scripted_session": tool.scripted_session,
                "profiles": list(CLI_TOOL_PROFILES.get(tool.key, ("default",))),
            }
        )
    return records


def _available_tool_or_raise(tool_key: str) -> CLITool:
    key = _safe_tool_key(tool_key)
    tool = ALLOWED_CLI_TOOLS[key]
    path = tool.executable
    available = bool(path) and (Path(path).exists() if os.path.isabs(path) else shutil.which(path) is not None)
    if not available:
        raise FileNotFoundError(f"CLI tool '{tool.key}' is not installed on this machine.")
    return tool


def _cli_job_record(
    *,
    tool_key: str,
    prompt: str,
    mode: str,
    root: Path = ROOT,
    cwd: Path | None = None,
) -> dict[str, Any]:
    ensure_dir(root / "runtime" / "cli_jobs")
    ensure_dir(root / "runtime" / "cli_jobs" / "outputs")
    ensure_dir(root / "runtime" / "cli_jobs" / "launchers")
    ensure_dir(root / "runtime" / "cli_jobs" / "sessions")
    job_id = f"clijob_{now_iso()[:10].replace('-', '')}_{uuid.uuid4().hex[:8]}"
    record = {
        "id": job_id,
        "created_at": now_iso(),
        "tool": tool_key,
        "prompt": prompt,
        "mode": mode,
        "cwd": str((cwd or root).resolve()),
        "status": "created",
    }
    _job_path(job_id, root=root).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def _save_job(record: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _job_path(record["id"], root=root).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def _save_session(record: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    ensure_dir(root / "runtime" / "cli_jobs" / "sessions")
    _session_path(record["id"], root=root).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def list_cli_jobs(*, root: Path = ROOT, limit: int = 20) -> list[dict[str, Any]]:
    directory = root / "runtime" / "cli_jobs"
    directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("clijob_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return records


def get_cli_job(job_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    path = _job_path(job_id, root=root)
    if not path.exists():
        raise FileNotFoundError(f"CLI job not found: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def latest_cli_job(*, root: Path = ROOT) -> dict[str, Any] | None:
    jobs = list_cli_jobs(root=root, limit=1)
    return jobs[0] if jobs else None


def list_cli_sessions(*, root: Path = ROOT, limit: int = 20) -> list[dict[str, Any]]:
    directory = root / "runtime" / "cli_jobs" / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("clisession_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return records


def get_cli_session(session_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    path = _session_path(session_id, root=root)
    if not path.exists():
        raise FileNotFoundError(f"CLI session not found: {session_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def latest_cli_session(*, root: Path = ROOT) -> dict[str, Any] | None:
    sessions = list_cli_sessions(root=root, limit=1)
    return sessions[0] if sessions else None


def _interactive_command(tool: CLITool, prompt: str, cwd: Path) -> list[str]:
    if tool.key == "codex":
        return [tool.executable, "-C", str(cwd), prompt]
    if tool.key == "omx":
        return [tool.executable, prompt]
    if tool.key == "gemini":
        return [tool.executable, "--prompt-interactive", prompt]
    if tool.key == "kimi":
        return [tool.executable, "--work-dir", str(cwd), "--prompt", prompt]
    raise ValueError(f"No interactive command profile for {tool.key}")


def _windows_quote(arg: str) -> str:
    return subprocess.list2cmdline([arg])


def _write_windows_launcher(*, record: dict[str, Any], command: list[str], root: Path, output_path: Path | None = None) -> Path:
    launcher_path = root / "runtime" / "cli_jobs" / "launchers" / f"{record['id']}.cmd"
    command_line = " ".join(_windows_quote(str(part)) for part in command)
    
    # If output_path is provided, redirect output to file while also displaying on console
    if output_path:
        # Create a wrapper that runs command, displays output, and saves to file
        # Using cmd to redirect stderr to stdout, then use tee-like behavior
        content = "\r\n".join(
            [
                "@echo off",
                "chcp 65001 >nul",
                "setlocal EnableDelayedExpansion",
                f'cd /d "{record["cwd"]}"',
                "echo [HAX-Mind] Starting CLI session...",
                f'echo [HAX-Mind] Output will be saved to: {output_path}',
                "echo.",
                # Run command and redirect both stdout and stderr to file
                f'{command_line} > "{output_path}" 2>&1',
                "set EXIT_CODE=!ERRORLEVEL!",
                "echo.",
                "echo [HAX-Mind] CLI session completed. Output:",
                "echo ========================================",
                # Display the output file content
                f'type "{output_path}"',
                "echo ========================================",
                "echo.",
                "echo [HAX-Mind] CLI session finished. Press any key to close this window.",
                "pause >nul",
            ]
        ) + "\r\n"
    else:
        content = "\r\n".join(
            [
                "@echo off",
                "chcp 65001 >nul",
                "setlocal",
                f'cd /d "{record["cwd"]}"',
                command_line,
                "echo.",
                "echo [HAX-Mind] CLI session finished. Press any key to close this window.",
                "pause >nul",
            ]
        ) + "\r\n"
    launcher_path.write_text(content, encoding="utf-8")
    return launcher_path


def _oneshot_command(tool: CLITool, prompt: str, cwd: Path) -> list[str]:
    if tool.key == "codex":
        return [tool.executable, "exec", prompt, "-C", str(cwd), "--skip-git-repo-check", "--json", "-s", "read-only"]
    if tool.key == "omx":
        return [tool.executable, "ask", "gemini", "--prompt", prompt]
    if tool.key == "gemini":
        return [tool.executable, "--prompt", prompt, "--approval-mode", "plan", "--output-format", "text"]
    if tool.key == "kimi":
        return [tool.executable, "--work-dir", str(cwd), "--print", "--prompt", prompt, "--output-format", "text"]
    raise ValueError(f"No one-shot command profile for {tool.key}")


def _session_turn_command(tool: CLITool, session_id: str, prompt: str, cwd: Path) -> list[str]:
    if tool.key == "kimi":
        return [tool.executable, "--work-dir", str(cwd), "--session", session_id, "--print", "--prompt", prompt, "--output-format", "text"]
    raise ValueError(f"Scripted sessions are not supported for {tool.key}")


def _run_subprocess(command: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        # Check if it's a PowerShell execution policy error
        error_str = str(e).lower()
        if "cannot be loaded because running scripts is disabled" in error_str or \
           "unauthorizedaccess" in error_str or \
           "execution policies" in error_str:
            # Fallback: run through cmd.exe explicitly
            cmd_line = " ".join(_windows_quote(str(part)) for part in command)
            return subprocess.run(
                ["cmd.exe", "/c", cmd_line],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
        raise


def _extract_gemini_session_id(output: str) -> str | None:
    match = re.search(r"\[([0-9a-fA-F-]{8,})\]", output)
    return match.group(1) if match else None


def _list_gemini_sessions(cwd: Path) -> str:
    tool = _available_tool_or_raise("gemini")
    result = _run_subprocess([tool.executable, "--list-sessions"], cwd=cwd, timeout=60)
    return result.stdout


def _extract_codex_thread_id(output: str) -> str | None:
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "thread.started":
            return payload.get("thread_id")
    return None


def _extract_codex_final_message(output: str) -> str:
    last_text = ""
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "item.completed":
            item = payload.get("item") or {}
            if item.get("type") == "agent_message":
                last_text = item.get("text") or last_text
    return last_text


def _git_diff_excerpt(cwd: Path) -> str:
    try:
        result = _run_subprocess(["git", "diff", "--stat"], cwd=cwd, timeout=30)
    except Exception:
        return ""
    return result.stdout.strip()[:2000]


def open_cli_session(tool_key: str, prompt: str, *, root: Path = ROOT, cwd: Path | None = None) -> dict[str, Any]:
    tool = _available_tool_or_raise(tool_key)
    safe_prompt = _sanitize_prompt(prompt)
    cwd = (cwd or root).resolve()
    record = _cli_job_record(tool_key=tool.key, prompt=safe_prompt, mode="interactive", root=root, cwd=cwd)
    command = _interactive_command(tool, safe_prompt, cwd)
    
    # Create output file for capturing CLI output
    output_path = root / "runtime" / "cli_jobs" / "outputs" / f"{record['id']}.txt"
    
    if os.name == "nt":
        launcher_path = _write_windows_launcher(record=record, command=command, root=root, output_path=output_path)
        popen_command = ["cmd.exe", "/k", str(launcher_path)]
        subprocess.Popen(
            popen_command,
            cwd=str(cwd),
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
        record["launcher_path"] = str(launcher_path.relative_to(root))
    else:
        # For non-Windows, use tee if available
        with open(output_path, "w", encoding="utf-8") as out_f:
            subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=out_f,
                stderr=subprocess.STDOUT,
            )
    
    record["status"] = "opened"
    record["opened_at"] = now_iso()
    record["command_preview"] = command
    record["output_path"] = str(output_path.relative_to(root))
    _save_job(record, root=root)
    log_event("cli_job", f"Opened interactive {tool.key} CLI job {record['id']}", topic="cli", importance="high")
    return record


def get_cli_output(job_id: str, *, root: Path = ROOT, max_chars: int = 4000) -> str:
    """Get the current output of a CLI job from its output file."""
    try:
        job = get_cli_job(job_id, root=root)
        output_path_str = job.get("output_path")
        if not output_path_str:
            return "No output file configured for this job."
        
        output_path = root / output_path_str
        if not output_path.exists():
            return "Output file not yet created. CLI may still be starting up."
        
        # Read the output file
        content = output_path.read_text(encoding="utf-8", errors="replace")
        
        # Return the last max_chars characters (most recent output)
        if len(content) > max_chars:
            return "..." + content[-(max_chars-3):]
        return content
    except FileNotFoundError:
        return f"CLI job not found: {job_id}"
    except Exception as e:
        return f"Error reading output: {e}"


def run_cli_once(tool_key: str, prompt: str, *, root: Path = ROOT, cwd: Path | None = None, timeout: int = 180) -> dict[str, Any]:
    tool = _available_tool_or_raise(tool_key)
    safe_prompt = _sanitize_prompt(prompt)
    cwd = (cwd or root).resolve()
    record = _cli_job_record(tool_key=tool.key, prompt=safe_prompt, mode="one_shot", root=root, cwd=cwd)
    command = _oneshot_command(tool, safe_prompt, cwd)
    try:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        stdout = result.stdout[-12000:]
        stderr = result.stderr[-4000:]
        output_path = root / "runtime" / "cli_jobs" / "outputs" / f"{record['id']}.txt"
        output_path.write_text(stdout + ("\n\n[stderr]\n" + stderr if stderr else ""), encoding="utf-8")
        record.update(
            {
                "status": "completed" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "finished_at": now_iso(),
                "stdout_excerpt": stdout[:2000],
                "stderr_excerpt": stderr[:1000],
                "output_path": str(output_path.relative_to(root)),
                "command_preview": command,
            }
        )
    except subprocess.TimeoutExpired as exc:
        record.update(
            {
                "status": "timeout",
                "finished_at": now_iso(),
                "stderr_excerpt": f"Timed out after {timeout}s",
                "command_preview": command,
            }
        )
    _save_job(record, root=root)
    log_event("cli_job", f"Ran one-shot {tool.key} CLI job {record['id']} status={record['status']}", topic="cli", importance="high")
    return record


def render_cli_tools_summary() -> str:
    records = detect_cli_tools()
    return "\n".join(
        f"{item['key']} | available={item['available']} | mode={item['mode']} | {item['title']}"
        for item in records
    )


def render_cli_jobs_summary(*, root: Path = ROOT, limit: int = 10) -> str:
    jobs = list_cli_jobs(root=root, limit=limit)
    if not jobs:
        return "No CLI jobs yet."
    return "\n".join(f"{job['id']} | {job['tool']} | {job['mode']} | {job['status']}" for job in jobs)


def render_cli_sessions_summary(*, root: Path = ROOT, limit: int = 10) -> str:
    sessions = list_cli_sessions(root=root, limit=limit)
    if not sessions:
        return "No CLI sessions yet."
    return "\n".join(
        f"{session['id']} | {session['tool']} | steps={session.get('step_count', 0)} | status={session.get('status', 'open')}"
        for session in sessions
    )


def render_cli_job_detail(job: dict[str, Any]) -> str:
    lines = [
        f"CLI job: {job['id']}",
        f"Tool: {job['tool']}",
        f"Mode: {job['mode']}",
        f"Status: {job['status']}",
        f"CWD: {job.get('cwd', '-')}",
        f"Created at: {job.get('created_at', '-')}",
    ]
    if job.get("opened_at"):
        lines.append(f"Opened at: {job['opened_at']}")
    if job.get("finished_at"):
        lines.append(f"Finished at: {job['finished_at']}")
    if job.get("output_path"):
        lines.append(f"Output: {job['output_path']}")
    if job.get("command_preview"):
        lines.append("Command preview:")
        lines.append(" ".join(str(part) for part in job["command_preview"]))
    if job.get("stdout_excerpt"):
        lines.append("Output excerpt:")
        lines.append(job["stdout_excerpt"][:1500])
    return "\n".join(lines)


def render_cli_session_detail(session: dict[str, Any]) -> str:
    lines = [
        f"CLI session: {session['id']}",
        f"Tool: {session['tool']}",
        f"Status: {session.get('status', 'open')}",
        f"Profile: {session.get('profile', 'default')}",
        f"Approved: {session.get('approved', False)}",
        f"Step count: {session.get('step_count', 0)}",
        f"CWD: {session.get('cwd', '-')}",
        f"Created at: {session.get('created_at', '-')}",
        f"Last job: {session.get('last_job_id', '-')}",
    ]
    if session.get("closed_at"):
        lines.append(f"Closed at: {session['closed_at']}")
    history = session.get("history", [])
    if history:
        lines.append("Recent prompts:")
        for item in history[-3:]:
            lines.append(f"- [{item['step']}] {item['prompt'][:120]}")
    return "\n".join(lines)


def create_cli_improvement_proposal(*, root: Path = ROOT) -> dict[str, Any]:
    jobs = list_cli_jobs(root=root, limit=50)
    failed = [job for job in jobs if job.get("status") in {"failed", "timeout"}]
    problem = "Local CLI orchestration needs hardening and skill growth from job history."
    if failed:
        problem = f"Recent CLI jobs are failing or timing out ({len(failed)} recent failures)."
    failed_tools = sorted({job["tool"] for job in failed}) if failed else []
    return create_proposal(
        title="Improve local CLI orchestration and skill growth",
        component="cli_orchestration",
        problem=problem,
        root_cause=(
            "CLI execution is newly integrated and needs continuous refinement from real Telegram-driven usage."
        ),
        solution=(
            "Review recent CLI jobs, refine prompts/tool routing, and improve allowlists, summaries, and failure handling."
        ),
        expected_impact=(
            "HAX-Mind becomes better at delegating work to Codex/OMX/Gemini/Kimi and learning from repeated usage."
        ),
        risk="medium",
        files_to_modify=[
            "engine/cli_bridge.py",
            "engine/orchestrator.py",
            "bot/telegram_bot.py",
        ],
        tests_to_run=[
            "tests/test_cli_bridge.py",
            "tests/test_orchestrator.py",
        ],
        rollback_plan="Revert CLI orchestration changes and restore prior Telegram command behavior from version control.",
        metadata={"failed_tools": failed_tools, "recent_job_count": len(jobs)},
        root=root,
    )


def _run_scripted_turn(tool: CLITool, session: dict[str, Any], prompt: str, *, root: Path, timeout: int) -> dict[str, Any]:
    safe_prompt = _sanitize_prompt(prompt)
    cwd = Path(session["cwd"])
    record = _cli_job_record(tool_key=tool.key, prompt=safe_prompt, mode="session_turn", root=root, cwd=cwd)

    if tool.key == "kimi":
        command = _session_turn_command(tool, session["id"], safe_prompt, cwd)
        result = _run_subprocess(command, cwd=cwd, timeout=timeout)
        stdout = result.stdout[-12000:]
        stderr = result.stderr[-4000:]
        external_session_id = session.get("external_session_id") or session["id"]
        final_message = stdout
    elif tool.key == "gemini":
        approval_mode = session.get("profile", "default")
        command = [tool.executable]
        if session.get("external_session_id"):
            command += ["--resume", session["external_session_id"]]
        command += ["--prompt", safe_prompt, "--output-format", "text", "--approval-mode", approval_mode]
        result = _run_subprocess(command, cwd=cwd, timeout=timeout)
        stdout = result.stdout[-12000:]
        stderr = result.stderr[-4000:]
        external_session_id = session.get("external_session_id") or _extract_gemini_session_id(_list_gemini_sessions(cwd))
        final_message = stdout
    elif tool.key in {"codex", "omx"}:
        profile = session.get("profile", "review")
        base = [tool.executable, "exec", "--json", "--skip-git-repo-check"]
        if profile == "review":
            base += ["-s", "read-only"]
        elif profile == "default":
            base += ["-s", "workspace-write"]
        elif profile == "yolo":
            base += ["--dangerously-bypass-approvals-and-sandbox"]
        if session.get("external_session_id"):
            command = [*base, "resume", session["external_session_id"], safe_prompt]
        else:
            command = [*base, safe_prompt]
        result = _run_subprocess(command, cwd=cwd, timeout=timeout)
        stdout = result.stdout[-12000:]
        stderr = result.stderr[-4000:]
        external_session_id = session.get("external_session_id") or _extract_codex_thread_id(stdout)
        final_message = _extract_codex_final_message(stdout) or stdout
    else:
        raise ValueError(f"Scripted sessions are not supported for {tool.key}")

    output_path = root / "runtime" / "cli_jobs" / "outputs" / f"{record['id']}.txt"
    output_path.write_text(stdout + ("\n\n[stderr]\n" + stderr if stderr else ""), encoding="utf-8")
    record.update(
        {
            "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "finished_at": now_iso(),
            "stdout_excerpt": final_message[:2000],
            "stderr_excerpt": stderr[:1000],
            "output_path": str(output_path.relative_to(root)),
            "command_preview": command,
            "session_id": session["id"],
        }
    )
    if tool.key in {"codex", "omx"}:
        diff_excerpt = _git_diff_excerpt(cwd)
        if diff_excerpt:
            record["diff_excerpt"] = diff_excerpt

    _save_job(record, root=root)
    session["step_count"] = int(session.get("step_count", 0)) + 1
    session["last_job_id"] = record["id"]
    session["external_session_id"] = external_session_id
    session.setdefault("history", []).append({"step": session["step_count"], "prompt": safe_prompt, "job_id": record["id"], "status": record["status"]})
    _save_session(session, root=root)
    log_event("cli_session", f"Ran {tool.key} session {session['id']} step={session['step_count']} status={record['status']}", topic="cli", importance="high")
    return record


def start_cli_session(tool_key: str, prompt: str, *, root: Path = ROOT, cwd: Path | None = None, timeout: int = 180, profile: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    tool = _available_tool_or_raise(tool_key)
    if not tool.scripted_session:
        raise ValueError(f"Tool '{tool.key}' does not support step sessions yet.")
    cwd = (cwd or root).resolve()
    session = {
        "id": f"clisession_{now_iso()[:10].replace('-', '')}_{uuid.uuid4().hex[:8]}",
        "tool": tool.key,
        "cwd": str(cwd),
        "created_at": now_iso(),
        "status": "open",
        "profile": _normalize_profile(tool.key, profile),
        "step_count": 0,
        "history": [],
        "last_job_id": None,
        "approved": False,
    }
    if tool.key in {"gemini", "kimi"}:
        session["approved"] = True
    _save_session(session, root=root)
    job = continue_cli_session(session["id"], prompt, root=root, timeout=timeout)
    return get_cli_session(session["id"], root=root), job


def continue_cli_session(session_ref: str, prompt: str, *, root: Path = ROOT, timeout: int = 180) -> dict[str, Any]:
    session = latest_cli_session(root=root) if session_ref == "latest" else get_cli_session(session_ref, root=root)
    if not session:
        raise FileNotFoundError("No CLI session exists yet.")
    tool = _available_tool_or_raise(session["tool"])
    if not tool.scripted_session:
        raise ValueError(f"Tool '{tool.key}' does not support scripted continuation.")
    if tool.key in {"codex", "omx"} and session.get("profile", "review") != "review" and not session.get("approved", False):
        raise PermissionError(f"{tool.key.upper()} session requires approval before continuing in write-capable mode. Use /cli approve <session_id|latest> first.")
    return _run_scripted_turn(tool, session, prompt, root=root, timeout=timeout)


def set_cli_session_profile(session_ref: str, profile: str, *, root: Path = ROOT) -> dict[str, Any]:
    session = latest_cli_session(root=root) if session_ref == "latest" else get_cli_session(session_ref, root=root)
    if not session:
        raise FileNotFoundError("No CLI session exists yet.")
    session["profile"] = _normalize_profile(session["tool"], profile)
    if session["tool"] in {"codex", "omx"} and session["profile"] == "review":
        session["approved"] = True
    _save_session(session, root=root)
    return session


def approve_cli_session(session_ref: str, *, root: Path = ROOT) -> dict[str, Any]:
    session = latest_cli_session(root=root) if session_ref == "latest" else get_cli_session(session_ref, root=root)
    if not session:
        raise FileNotFoundError("No CLI session exists yet.")
    session["approved"] = True
    if session["tool"] in {"codex", "omx"} and session.get("profile") == "review":
        session["profile"] = "default"
    _save_session(session, root=root)
    return session


def close_cli_session(session_ref: str, *, root: Path = ROOT) -> dict[str, Any]:
    session = latest_cli_session(root=root) if session_ref == "latest" else get_cli_session(session_ref, root=root)
    if not session:
        raise FileNotFoundError("No CLI session exists yet.")
    session["status"] = "closed"
    session["closed_at"] = now_iso()
    _save_session(session, root=root)
    return session
