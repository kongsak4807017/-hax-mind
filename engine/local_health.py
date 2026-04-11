from __future__ import annotations

import json
import os
import ctypes
from pathlib import Path
from typing import Any, Callable

from engine.dreaming import memory_status
from engine.proposal_engine import list_proposals
from engine.utils import ROOT, now_iso


def _read_json_files(directory: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return records


def _default_pid_checker(pid: int) -> bool:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if process:
            kernel32.CloseHandle(process)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _bot_snapshot(root: Path, pid_checker: Callable[[int], bool]) -> dict[str, Any]:
    pid_path = root / "runtime" / "telegram_bot.pid"
    supervisor_pid_path = root / "runtime" / "telegram_bot_supervisor.pid"
    lifecycle_log = root / "runtime" / "logs" / "telegram_bot.lifecycle.log"
    supervisor_log = root / "runtime" / "logs" / "telegram_bot_supervisor.log"
    pid = None
    running = False
    supervisor_pid = None
    supervisor_running = False
    if pid_path.exists():
        raw = pid_path.read_text(encoding="utf-8", errors="ignore").strip()
        if raw.isdigit():
            pid = int(raw)
            running = pid_checker(pid)
    if supervisor_pid_path.exists():
        raw = supervisor_pid_path.read_text(encoding="utf-8", errors="ignore").strip()
        if raw.isdigit():
            supervisor_pid = int(raw)
            supervisor_running = pid_checker(supervisor_pid)
    return {
        "pid": pid,
        "pid_file_exists": pid_path.exists(),
        "running": running,
        "supervisor_pid": supervisor_pid,
        "supervisor_pid_file_exists": supervisor_pid_path.exists(),
        "supervisor_running": supervisor_running,
        "lifecycle_log_exists": lifecycle_log.exists(),
        "supervisor_log_exists": supervisor_log.exists(),
    }


def _report_snapshot(root: Path) -> dict[str, Any]:
    report_path = root / "runtime" / "reports" / "morning_report.txt"
    if not report_path.exists():
        return {"exists": False, "updated_at": None}
    return {"exists": True, "updated_at": report_path.stat().st_mtime}


def _automation_snapshot() -> dict[str, Any]:
    startup_launcher = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/HAX-Mind-Telegram-Bot.cmd"
    return {"startup_launcher_exists": startup_launcher.exists(), "startup_launcher": str(startup_launcher)}


def local_health_snapshot(root: Path = ROOT, pid_checker: Callable[[int], bool] | None = None) -> dict[str, Any]:
    pid_checker = pid_checker or _default_pid_checker
    proposals = list_proposals(limit=200, root=root)
    missions = _read_json_files(root / "runtime" / "missions", limit=50)
    reports = _report_snapshot(root)
    bot = _bot_snapshot(root, pid_checker=pid_checker)
    memory = memory_status(root)
    pending = [proposal for proposal in proposals if proposal.get("status") == "pending"]
    archived = [proposal for proposal in proposals if proposal.get("status") == "archived_duplicate"]
    return {
        "generated_at": now_iso(),
        "bot": bot,
        "reports": reports,
        "queue": {
            "pending_proposals": len(pending),
            "known_proposals": len(proposals),
            "archived_duplicates": len(archived),
            "missions": len(missions),
        },
        "memory": memory,
        "automation": _automation_snapshot(),
    }


def render_local_health_summary(root: Path = ROOT, pid_checker: Callable[[int], bool] | None = None) -> str:
    snapshot = local_health_snapshot(root=root, pid_checker=pid_checker)
    bot = snapshot["bot"]
    queue = snapshot["queue"]
    memory = snapshot["memory"]
    reports = snapshot["reports"]
    automation = snapshot["automation"]
    lines = [
        f"Local Health - {snapshot['generated_at']}",
        "",
        "Bot:",
        f"- Running: {bot['running']}",
        f"- PID file: {bot['pid_file_exists']}",
        f"- PID: {bot['pid'] or 'none'}",
        f"- Supervisor PID file: {bot['supervisor_pid_file_exists']}",
        f"- Supervisor PID: {bot['supervisor_pid'] or 'none'}",
        f"- Supervisor running: {bot['supervisor_running']}",
        f"- Lifecycle log: {bot['lifecycle_log_exists']}",
        f"- Supervisor log: {bot['supervisor_log_exists']}",
        "",
        "Reports:",
        f"- Morning report exists: {reports['exists']}",
        f"- Morning report mtime: {reports['updated_at']}",
        "",
        "Queue:",
        f"- Pending proposals: {queue['pending_proposals']}",
        f"- Known proposals: {queue['known_proposals']}",
        f"- Archived duplicates: {queue['archived_duplicates']}",
        f"- Missions: {queue['missions']}",
        "",
        "Memory:",
        (
            f"- tools={memory['tools']} repos={memory['repos']} notes={memory['notes']} dreams={memory['dreams']} "
            f"decisions={memory.get('decisions', 0)} vectors={memory.get('vector_documents', 0)} "
            f"clusters={memory.get('topic_clusters', 0)} duplicates={memory.get('duplicate_candidates', 0)}"
        ),
        "",
        "Automation:",
        f"- Startup fallback exists: {automation['startup_launcher_exists']}",
        f"- Startup fallback path: {automation['startup_launcher']}",
    ]
    return "\n".join(lines) + "\n"
