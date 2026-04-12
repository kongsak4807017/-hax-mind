from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from engine.memory_store import initialize_memory_dirs, write_json, write_text
from engine.proposal_engine import get_proposal
from engine.utils import ROOT, ensure_dir, now_iso, read_env_file

PICOCLAW_STATE = ROOT / "state" / "picoclaw_state.json"
WORKER_STALE_AFTER_MINUTES = 15


def default_picoclaw_state() -> dict:
    return {
        "component": "PicoClaw",
        "phase": 2,
        "status": "planned",
        "role": "Termux/worker gateway for remote execution, scheduling, and always-on relay",
        "created_at": now_iso(),
        "readiness": {
            "local_telegram_bot": True,
            "memory_dreaming_v1": True,
            "task_queue": True,
            "proposal_gate": True,
            "safe_executor": True,
            "termux_worker_installed": False,
            "worker_auth_secret_configured": False,
            "heartbeat_endpoint": False,
            "remote_job_queue": False,
        },
        "next_steps": [
            "Keep the Windows Telegram bot as the source-of-truth command center.",
            "Install PicoClaw/worker on Termux only after local task/proposal loop stays stable.",
            "Add a shared worker auth secret outside git.",
            "Add heartbeat + job queue before allowing remote execution.",
            "Keep remote worker read-only until rollback and logs are proven.",
        ],
    }


def _picoclaw_runtime_dir(root: Path) -> Path:
    return root / "runtime" / "picoclaw"


def _heartbeats_dir(root: Path) -> Path:
    return _picoclaw_runtime_dir(root) / "heartbeats"


def _jobs_dir(root: Path) -> Path:
    return _picoclaw_runtime_dir(root) / "jobs"


def _results_dir(root: Path) -> Path:
    return _picoclaw_runtime_dir(root) / "results"


def _logs_dir(root: Path) -> Path:
    return _picoclaw_runtime_dir(root) / "logs"


def _ensure_picoclaw_dirs(root: Path) -> None:
    initialize_memory_dirs(root)
    for path in [
        root / "state",
        root / "docs",
        _heartbeats_dir(root),
        _jobs_dir(root),
        _results_dir(root),
        _logs_dir(root),
    ]:
        ensure_dir(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _iter_json_records(directory: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    paths = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if limit is not None:
        paths = paths[:limit]
    for path in paths:
        payload = _read_json(path)
        if payload is not None:
            items.append(payload)
    return items


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _heartbeat_liveness(timestamp: str | None, stale_after_minutes: int = WORKER_STALE_AFTER_MINUTES) -> str:
    heartbeat_time = _parse_iso_datetime(timestamp)
    if heartbeat_time is None:
        return "offline"
    age = datetime.now(heartbeat_time.tzinfo) - heartbeat_time
    if age <= timedelta(minutes=stale_after_minutes):
        return "live"
    return "stale"


def _worker_secret() -> str | None:
    read_env_file()
    raw = os.environ.get("PICOCLAW_SHARED_SECRET", "").strip() or os.environ.get("PICOCLAW_WORKER_SECRET", "").strip()
    return raw or None


def _require_worker_secret(provided_secret: str | None) -> None:
    expected = _worker_secret()
    if not expected:
        raise RuntimeError("PICOCLAW_SHARED_SECRET (or legacy PICOCLAW_WORKER_SECRET) is not configured. Add it to .env or .env.txt outside git.")
    if provided_secret != expected:
        raise PermissionError("Invalid PicoClaw worker secret.")


def latest_worker_heartbeat(root: Path = ROOT) -> dict | None:
    records = _iter_json_records(_heartbeats_dir(root), limit=1)
    return records[0] if records else None


def latest_worker_heartbeats(root: Path = ROOT, limit: int = 20) -> list[dict[str, Any]]:
    return _iter_json_records(_heartbeats_dir(root), limit=limit)


def list_workers(root: Path = ROOT, limit: int = 20, include_stale: bool = True) -> list[dict[str, Any]]:
    workers = []
    for worker in latest_worker_heartbeats(root=root, limit=limit):
        item = dict(worker)
        liveness = _heartbeat_liveness(worker.get("timestamp"))
        item["active"] = liveness == "live"
        item["liveness"] = liveness
        if not include_stale and liveness != "live":
            continue
        workers.append(item)
    return workers


def worker_status(root: Path = ROOT) -> dict[str, Any]:
    latest = latest_worker_heartbeat(root)
    if latest is None:
        return {
            "status": "offline",
            "worker_id": None,
            "last_seen_at": None,
            "capabilities": [],
            "summary": "No worker heartbeat has been recorded yet.",
        }
    liveness = _heartbeat_liveness(latest.get("timestamp"))
    summary = {
        "live": "Worker is online and heartbeats are fresh.",
        "stale": "A worker heartbeat exists, but it is stale. The worker is not confirmed online right now.",
        "offline": "No current worker heartbeat is available.",
    }[liveness]
    return {
        "status": liveness,
        "worker_id": latest.get("worker_id"),
        "last_seen_at": latest.get("timestamp"),
        "capabilities": latest.get("capabilities", []),
        "summary": summary,
    }


def list_remote_jobs(status: str | None = None, limit: int = 20, root: Path = ROOT) -> list[dict]:
    jobs = _iter_json_records(_jobs_dir(root), limit=None)
    if status:
        jobs = [job for job in jobs if job.get("status") == status]
    return jobs[:limit]


def _refresh_state(state: dict, root: Path) -> dict:
    latest_heartbeat = latest_worker_heartbeat(root)
    live_worker_status = worker_status(root)
    jobs = _iter_json_records(_jobs_dir(root), limit=None)
    workers = {
        worker["worker_id"]: worker
        for worker in _iter_json_records(_heartbeats_dir(root), limit=None)
        if worker.get("worker_id")
    }
    secret_configured = bool(_worker_secret())

    readiness = default_picoclaw_state()["readiness"]
    readiness.update(state.get("readiness", {}))
    readiness.update(
        {
            "termux_worker_installed": latest_heartbeat is not None,
            "worker_auth_secret_configured": secret_configured,
            "heartbeat_endpoint": latest_heartbeat is not None,
            "remote_job_queue": True,
        }
    )

    queue = {
        "pending": sum(1 for job in jobs if job.get("status") == "pending"),
        "claimed": sum(1 for job in jobs if job.get("status") == "claimed"),
        "completed": sum(1 for job in jobs if job.get("status") == "completed"),
        "failed": sum(1 for job in jobs if job.get("status") == "failed"),
    }

    state["readiness"] = readiness
    state["queue"] = queue
    state["queue_counts"] = {
        "queued": queue["pending"],
        "claimed": queue["claimed"],
        "completed": queue["completed"],
        "failed": queue["failed"],
    }
    state["workers"] = workers
    state["active_workers"] = len(workers)
    state["queued_jobs"] = queue["pending"]
    state["last_heartbeat_at"] = latest_heartbeat.get("timestamp") if latest_heartbeat else None
    state["last_heartbeat_worker_id"] = latest_heartbeat.get("worker_id") if latest_heartbeat else None
    state["latest_heartbeat"] = (
        {
            "worker_id": latest_heartbeat["worker_id"],
            "last_seen_at": latest_heartbeat["timestamp"],
            "capabilities": latest_heartbeat.get("capabilities", []),
            "status": live_worker_status["status"],
        }
        if latest_heartbeat
        else None
    )
    state["worker_runtime_status"] = live_worker_status
    state["updated_at"] = now_iso()

    if live_worker_status["status"] == "live":
        state["status"] = "worker_connected"
    elif latest_heartbeat is not None:
        state["status"] = "worker_stale"
    elif readiness["worker_auth_secret_configured"]:
        state["status"] = "control_plane_ready"
    else:
        state["status"] = "awaiting_worker_secret"
    return state


def ensure_picoclaw_state(root: Path = ROOT) -> dict:
    _ensure_picoclaw_dirs(root)
    path = root / "state" / "picoclaw_state.json"
    existing = _read_json(path) if path.exists() else None
    state = existing or default_picoclaw_state()
    state = _refresh_state(state, root)
    write_json(path, state)
    write_text(root / "docs" / "picoclaw-phase2.md", render_picoclaw_plan(state))
    return state


def render_picoclaw_plan(state: dict | None = None) -> str:
    state = state or default_picoclaw_state()
    queue = state.get("queue", {})
    lines = [
        "# PicoClaw Phase 2 Plan",
        "",
        f"Status: `{state['status']}`",
        "",
        "## Role",
        "",
        state["role"],
        "",
        "## Readiness",
    ]
    lines.extend(f"- {key}: {value}" for key, value in state["readiness"].items())
    lines.extend(
        [
            "",
            "## Control plane",
            "",
            f"- Last heartbeat: {state.get('last_heartbeat_at') or 'none yet'}",
            f"- Last worker: {state.get('last_heartbeat_worker_id') or 'n/a'}",
            f"- Queue pending: {queue.get('pending', 0)}",
            f"- Queue claimed: {queue.get('claimed', 0)}",
            f"- Queue completed: {queue.get('completed', 0)}",
            f"- Queue failed: {queue.get('failed', 0)}",
            "",
            "## Next steps",
        ]
    )
    lines.extend(f"{idx}. {step}" for idx, step in enumerate(state["next_steps"], 1))
    lines.extend(
        [
            "",
            "## Worker secret",
            "",
            "Add this to `.env` or `.env.txt` on the Windows brain and on the worker manually:",
            "",
            "```text",
            "PICOCLAW_SHARED_SECRET=generate_a_long_random_shared_secret",
            "PICOCLAW_WORKER_ID=termux-main",
            "```",
            "",
            "## Runtime paths",
            "",
            "- `runtime/picoclaw/heartbeats/`",
            "- `runtime/picoclaw/jobs/`",
            "- `runtime/picoclaw/results/`",
            "- `runtime/picoclaw/logs/`",
            "",
            "## Local validation",
            "",
            "```powershell",
            ".\\.venv\\Scripts\\python.exe -m pytest tests",
            "$env:PICOCLAW_SHARED_SECRET='YOUR_SECRET'",
            ".\\.venv\\Scripts\\python.exe jobs\\picoclaw_worker.py heartbeat --worker-id termux-smoke --platform termux",
            ".\\.venv\\Scripts\\python.exe jobs\\picoclaw_worker.py cycle --worker-id termux-smoke --platform termux",
            "```",
            "",
            "## Termux install sketch",
            "",
            "```bash",
            "pkg update && pkg upgrade -y",
            "pkg install git nodejs python -y",
            "git clone https://github.com/sipeed/picoclaw.git",
            "cd picoclaw",
            "./picoclaw-linux-arm64",
            "# then run the HAX-Mind worker heartbeat / queue commands",
            "```",
            "",
            "Do not enable remote code execution until heartbeat, auth, logs, rollback, and safe-mode policy are verified.",
        ]
    )
    return "\n".join(lines) + "\n"


def picoclaw_status(root: Path = ROOT) -> dict:
    return ensure_picoclaw_state(root)


def picoclaw_plan(root: Path = ROOT) -> str:
    state = ensure_picoclaw_state(root)
    plan = render_picoclaw_plan(state)
    write_text(root / "docs" / "picoclaw-phase2.md", plan)
    return plan


def record_worker_heartbeat(
    worker_id: str,
    provided_secret: str | None,
    capabilities: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    platform: str = "termux",
    status: str = "online",
    root: Path = ROOT,
) -> dict:
    _require_worker_secret(provided_secret)
    _ensure_picoclaw_dirs(root)
    heartbeat = {
        "id": f"hb_{uuid.uuid4().hex[:8]}",
        "timestamp": now_iso(),
        "worker_id": worker_id.strip() or "unknown-worker",
        "platform": platform,
        "capabilities": capabilities or [],
        "metadata": metadata or {},
        "status": status,
    }
    filename = f"{heartbeat['timestamp'][:19].replace(':', '').replace('-', '')}_{heartbeat['worker_id']}.json"
    write_json(_heartbeats_dir(root) / filename, heartbeat)
    ensure_picoclaw_state(root)
    return heartbeat


def register_worker_heartbeat(
    worker_id: str,
    shared_secret: str | None,
    capabilities: list[str] | None = None,
    status: str = "online",
    metadata: dict[str, Any] | None = None,
    *,
    platform: str = "termux",
    root: Path = ROOT,
) -> dict:
    return record_worker_heartbeat(
        worker_id=worker_id,
        provided_secret=shared_secret,
        capabilities=capabilities,
        metadata=metadata,
        platform=platform,
        status=status,
        root=root,
    )


def enqueue_remote_job(
    job_kind: str,
    payload: dict[str, Any] | None = None,
    *,
    created_by: str | None = None,
    requested_by: str | None = None,
    scope: str = "read_only",
    target_worker: str = "termux-readonly",
    mode: str = "safe_read_only",
    root: Path = ROOT,
) -> dict:
    _ensure_picoclaw_dirs(root)
    job = {
        "id": f"pjob_{uuid.uuid4().hex[:8]}",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "job_kind": job_kind,
        "job_type": job_kind,
        "scope": scope,
        "mode": mode,
        "safe_mode": mode,
        "target_worker": target_worker,
        "created_by": created_by or requested_by or "system",
        "requested_by": requested_by or created_by or "system",
        "status": "pending",
        "payload": payload or {},
        "type": job_kind,
    }
    write_json(_jobs_dir(root) / f"{job['id']}.json", job)
    ensure_picoclaw_state(root)
    return job


def queue_remote_job(
    job_type: str,
    payload: dict[str, Any] | None = None,
    created_by: str = "system",
    mode: str = "safe_read_only",
    root: Path = ROOT,
) -> dict:
    return enqueue_remote_job(job_type, payload or {}, created_by=created_by, mode=mode, root=root)


def get_remote_job(job_id: str, root: Path = ROOT) -> dict[str, Any]:
    path = _jobs_dir(root) / f"{job_id}.json"
    job = _read_json(path)
    if job is None:
        raise FileNotFoundError(job_id)
    return job


def issue_remote_job_from_mission(mission_id: str, root: Path = ROOT) -> dict[str, Any]:
    from engine.mission_engine import get_mission

    mission = get_mission(mission_id, root=root)
    return enqueue_remote_job(
        "mission_read_only",
        {
            "mission_id": mission["id"],
            "project_id": mission["project_id"],
            "project_name": mission["project_name"],
            "project_path_or_repo": mission["project_path_or_repo"],
            "description": mission["description"],
            "allowed_actions": ["inspect", "summarize", "analyze"],
        },
        created_by="telegram",
        scope="read_only",
        target_worker="termux-readonly",
        mode="remote_read_only",
        root=root,
    )


def queue_proposal_for_remote_safe_execution(proposal_id: str, created_by: str, root: Path = ROOT) -> dict:
    proposal = get_proposal(proposal_id, root=root)
    if proposal.get("status") != "approved":
        raise ValueError(f"Proposal {proposal_id} must be approved before it can be queued for PicoClaw.")
    return enqueue_remote_job(
        "proposal_safe_execute",
        {
            "proposal_id": proposal["id"],
            "title": proposal["title"],
            "risk": proposal["risk"],
            "tests_to_run": proposal.get("tests_to_run", []),
            "files_to_modify": proposal.get("files_to_modify", []),
            "metadata": proposal.get("metadata", {}),
        },
        created_by=created_by,
        scope="read_only",
        target_worker="termux-readonly",
        mode="safe_check_only",
        root=root,
    )


def claim_remote_job(worker_id: str, provided_secret: str | None, root: Path = ROOT) -> dict | None:
    _require_worker_secret(provided_secret)
    _ensure_picoclaw_dirs(root)
    pending_jobs = list_remote_jobs(status="pending", limit=1000, root=root)
    for job in reversed(pending_jobs):
        job["status"] = "claimed"
        job["claimed_by"] = worker_id
        job["claimed_at"] = now_iso()
        job["updated_at"] = now_iso()
        write_json(_jobs_dir(root) / f"{job['id']}.json", job)
        ensure_picoclaw_state(root)
        return job
    ensure_picoclaw_state(root)
    return None


def complete_remote_job(
    job_id: str,
    worker_id: str,
    provided_secret: str | None,
    result: dict[str, Any] | None = None,
    *,
    status: str = "completed",
    summary: str | None = None,
    details: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> dict:
    _require_worker_secret(provided_secret)
    _ensure_picoclaw_dirs(root)
    path = _jobs_dir(root) / f"{job_id}.json"
    job = _read_json(path)
    if job is None:
        raise FileNotFoundError(job_id)
    claimed_by = job.get("claimed_by")
    if claimed_by and claimed_by != worker_id:
        raise PermissionError(f"Job {job_id} is claimed by {claimed_by}, not {worker_id}.")
    final_result = result or {"summary": (summary or "").strip(), "details": details or {}}
    if summary is not None:
        final_result.setdefault("summary", summary.strip())
    if details is not None:
        final_result.setdefault("details", details)
    job["status"] = status
    job["completed_by"] = worker_id
    job["completed_at"] = now_iso()
    job["updated_at"] = now_iso()
    job["result"] = final_result
    write_json(path, job)
    record = {
        "job_id": job_id,
        "worker_id": worker_id,
        "status": status,
        "timestamp": now_iso(),
        "result": final_result,
    }
    write_json(_results_dir(root) / f"{job_id}.json", record)
    ensure_picoclaw_state(root)
    return record


def fail_remote_job(
    job_id: str,
    worker_id: str,
    shared_secret: str | None,
    error: str,
    *,
    root: Path = ROOT,
) -> dict:
    return complete_remote_job(
        job_id=job_id,
        worker_id=worker_id,
        provided_secret=shared_secret,
        result={"error": error},
        status="failed",
        root=root,
    )
