from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.utils import ROOT, ensure_dir, now_iso

MEMORY_DIR = ROOT / "memory"
RAW_LOG_DIR = MEMORY_DIR / "raw_logs"
RAW_SOURCE_DIR = MEMORY_DIR / "raw_sources"
DAILY_SUMMARY_DIR = MEMORY_DIR / "daily_summaries"
TOPIC_SUMMARY_DIR = MEMORY_DIR / "topic_summaries"
CANONICAL_DIR = MEMORY_DIR / "canonical"


def initialize_memory_dirs(root: Path = ROOT) -> None:
    base = root / "memory"
    for path in [
        base / "raw_logs",
        base / "raw_sources" / "tool_repos",
        base / "daily_summaries",
        base / "topic_summaries",
        base / "canonical" / "tools",
        base / "canonical" / "notes",
        base / "canonical" / "dreams",
        base / "canonical" / "decisions",
        base / "canonical" / "repo_knowledge",
        base / "canonical" / "design_patterns",
        base / "indexes",
        root / "workspace" / "projects",
        root / "runtime" / "missions",
        root / "runtime" / "task_plans",
    ]:
        ensure_dir(path)


def append_raw_log(event_type: str, content: str, topic: str = "general", importance: str = "normal", root: Path = ROOT) -> Path:
    initialize_memory_dirs(root)
    path = root / "memory" / "raw_logs" / f"{now_iso()[:10]}.log"
    item = {
        "timestamp": now_iso(),
        "type": event_type,
        "topic": topic,
        "importance": importance,
        "content": content,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, content: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    return path
