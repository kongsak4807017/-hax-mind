"""
Worker Log Ingestion System for PicoClaw Phase 2
Handles ingestion of logs from remote workers (Termux)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.memory_store import write_json, write_text
from engine.picoclaw_manager import _logs_dir
from engine.utils import ROOT, ensure_dir, now_iso

WORKER_LOGS_DIR = ROOT / "memory" / "raw_logs" / "worker"
WORKER_LOG_INDEX = ROOT / "memory" / "indexes" / "worker_logs.json"


def ensure_worker_log_dirs() -> None:
    """Ensure all worker log directories exist"""
    ensure_dir(WORKER_LOGS_DIR)
    ensure_dir(WORKER_LOG_INDEX.parent)


def ingest_worker_log(
    worker_id: str,
    log_content: str,
    log_type: str = "stdout",
    job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    """
    Ingest a log from a remote worker
    
    Args:
        worker_id: Unique identifier for the worker
        log_content: The log content to ingest
        log_type: Type of log (stdout, stderr, system, etc.)
        job_id: Optional associated job ID
        metadata: Optional additional metadata
        root: Project root path
    
    Returns:
        Record of the ingested log
    """
    ensure_worker_log_dirs()
    
    timestamp = now_iso()
    date_str = timestamp[:10]  # YYYY-MM-DD
    
    record = {
        "id": f"wlog_{worker_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": timestamp,
        "worker_id": worker_id,
        "log_type": log_type,
        "job_id": job_id,
        "content": log_content,
        "metadata": metadata or {},
        "content_length": len(log_content),
    }
    
    # Save to daily log file
    daily_file = WORKER_LOGS_DIR / f"{date_str}_{worker_id}.jsonl"
    ensure_dir(daily_file.parent)
    
    with open(daily_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # Update index
    _update_log_index(record, root)
    
    return record


def _update_log_index(record: dict[str, Any], root: Path) -> None:
    """Update the worker log index"""
    index_path = WORKER_LOG_INDEX
    
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        except json.JSONDecodeError:
            index = {"logs": [], "workers": {}, "total_entries": 0}
    else:
        index = {"logs": [], "workers": {}, "total_entries": 0}
    
    # Add to recent logs (keep last 1000)
    index["logs"].insert(0, {
        "id": record["id"],
        "timestamp": record["timestamp"],
        "worker_id": record["worker_id"],
        "log_type": record["log_type"],
        "job_id": record["job_id"],
    })
    index["logs"] = index["logs"][:1000]
    
    # Update worker stats
    worker_id = record["worker_id"]
    if worker_id not in index["workers"]:
        index["workers"][worker_id] = {
            "first_seen": record["timestamp"],
            "last_seen": record["timestamp"],
            "log_count": 0,
        }
    index["workers"][worker_id]["last_seen"] = record["timestamp"]
    index["workers"][worker_id]["log_count"] += 1
    
    index["total_entries"] += 1
    index["updated_at"] = now_iso()
    
    write_json(index_path, index)


def get_worker_logs(
    worker_id: str | None = None,
    log_type: str | None = None,
    since: str | None = None,
    limit: int = 100,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    """
    Retrieve worker logs with optional filtering
    
    Args:
        worker_id: Filter by specific worker
        log_type: Filter by log type
        since: ISO timestamp to filter logs after
        limit: Maximum number of logs to return
        root: Project root path
    
    Returns:
        List of log records
    """
    ensure_worker_log_dirs()
    
    logs = []
    
    # Read all daily log files
    for log_file in sorted(WORKER_LOGS_DIR.glob("*.jsonl"), reverse=True):
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    
                    # Apply filters
                    if worker_id and record.get("worker_id") != worker_id:
                        continue
                    if log_type and record.get("log_type") != log_type:
                        continue
                    if since and record.get("timestamp", "") < since:
                        continue
                    
                    logs.append(record)
                    
                    if len(logs) >= limit:
                        return logs
                        
                except json.JSONDecodeError:
                    continue
    
    return logs


def get_worker_log_summary(root: Path = ROOT) -> dict[str, Any]:
    """Get summary of worker logs"""
    ensure_worker_log_dirs()
    
    index_path = WORKER_LOG_INDEX
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            return {
                "total_entries": index.get("total_entries", 0),
                "workers": list(index.get("workers", {}).keys()),
                "worker_count": len(index.get("workers", {})),
                "updated_at": index.get("updated_at"),
            }
        except json.JSONDecodeError:
            pass
    
    return {
        "total_entries": 0,
        "workers": [],
        "worker_count": 0,
        "updated_at": None,
    }


def cleanup_old_worker_logs(days: int = 30, root: Path = ROOT) -> int:
    """
    Remove worker logs older than specified days
    
    Args:
        days: Number of days to keep
        root: Project root path
    
    Returns:
        Number of files removed
    """
    ensure_worker_log_dirs()
    
    cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
    removed = 0
    
    for log_file in WORKER_LOGS_DIR.glob("*.jsonl"):
        if log_file.stat().st_mtime < cutoff:
            log_file.unlink()
            removed += 1
    
    return removed


def ingest_worker_log_from_file(
    worker_id: str,
    log_file_path: Path,
    log_type: str = "stdout",
    job_id: str | None = None,
    root: Path = ROOT,
) -> dict[str, Any] | None:
    """
    Ingest worker log from a file (for batch ingestion)
    
    Args:
        worker_id: Worker identifier
        log_file_path: Path to log file
        log_type: Type of log
        job_id: Optional job ID
        root: Project root path
    
    Returns:
        Ingestion record or None if file not found
    """
    if not log_file_path.exists():
        return None
    
    content = log_file_path.read_text(encoding="utf-8")
    return ingest_worker_log(
        worker_id=worker_id,
        log_content=content,
        log_type=log_type,
        job_id=job_id,
        metadata={"source_file": str(log_file_path)},
        root=root,
    )
