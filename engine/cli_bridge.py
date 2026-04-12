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
MAX_PROMPT_LENGTH = 4000


@dataclass(frozen=True)
class CLITool:
    key: str
    title: str
    mode: str  # interactive | one_shot | hybrid
    executable: str


ALLOWED_CLI_TOOLS: dict[str, CLITool] = {
    "codex": CLITool("codex", "OpenAI Codex CLI", "hybrid", os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd")),
    "omx": CLITool("omx", "oh-my-codex", "hybrid", os.path.join(os.environ.get("APPDATA", ""), "npm", "omx.cmd")),
    "gemini": CLITool("gemini", "Gemini CLI", "hybrid", os.path.join(os.environ.get("APPDATA", ""), "npm", "gemini.cmd")),
    "kimi": CLITool("kimi", "Kimi CLI", "hybrid", shutil.which("kimi") or "kimi"),
}


def _job_path(job_id: str, root: Path = ROOT) -> Path:
    return root / "runtime" / "cli_jobs" / f"{job_id}.json"


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


def open_cli_session(tool_key: str, prompt: str, *, root: Path = ROOT, cwd: Path | None = None) -> dict[str, Any]:
    tool = _available_tool_or_raise(tool_key)
    safe_prompt = _sanitize_prompt(prompt)
    cwd = (cwd or root).resolve()
    record = _cli_job_record(tool_key=tool.key, prompt=safe_prompt, mode="interactive", root=root, cwd=cwd)
    command = _interactive_command(tool, safe_prompt, cwd)
    subprocess.Popen(
        ["cmd.exe", "/c", "start", f'"HAX-Mind {tool.key}"', "cmd.exe", "/k", *command],
        cwd=str(cwd),
    )
    record["status"] = "opened"
    record["opened_at"] = now_iso()
    record["command_preview"] = command
    _save_job(record, root=root)
    log_event("cli_job", f"Opened interactive {tool.key} CLI job {record['id']}", topic="cli", importance="high")
    return record


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
