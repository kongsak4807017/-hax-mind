from __future__ import annotations

import json
from pathlib import Path

from engine.memory_store import append_raw_log, initialize_memory_dirs, write_text
from engine.utils import ROOT, now_iso


def log_event(event_type: str, content: str, topic: str = "general", importance: str = "normal") -> Path:
    return append_raw_log(event_type, content, topic=topic, importance=importance)


def summarize_today(root: Path = ROOT) -> str:
    initialize_memory_dirs(root)
    today = now_iso()[:10]
    src = root / "memory" / "raw_logs" / f"{today}.log"
    dst = root / "memory" / "daily_summaries" / f"{today}.md"
    if not src.exists():
        text = f"# Daily Summary: {today}\n\nNo events found.\n"
        write_text(dst, text)
        return text

    items = []
    for line in src.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    lines = [f"# Daily Summary: {today}", "", "## Highlights"]
    for item in items[:50]:
        lines.append(f"- [{item.get('topic', 'general')}] {item.get('content', '')[:240]}")
    text = "\n".join(lines) + "\n"
    write_text(dst, text)
    return text
