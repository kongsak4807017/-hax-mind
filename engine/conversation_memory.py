from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.utils import ROOT, ensure_dir, now_iso


CHAT_MEMORY_DIR = ROOT / "runtime" / "chat_memory"
MAX_STORED_TURNS = 24


def _chat_memory_path(chat_id: int | str, root: Path = ROOT) -> Path:
    return root / "runtime" / "chat_memory" / f"{chat_id}.json"


def read_conversation(chat_id: int | str, *, root: Path = ROOT) -> list[dict[str, Any]]:
    path = _chat_memory_path(chat_id, root=root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def append_conversation_turn(
    chat_id: int | str,
    *,
    role: str,
    content: str,
    user_id: int | None = None,
    root: Path = ROOT,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = _chat_memory_path(chat_id, root=root)
    ensure_dir(path.parent)
    turns = read_conversation(chat_id, root=root)
    turn = {
        "timestamp": now_iso(),
        "role": role,
        "content": content,
    }
    if user_id is not None:
        turn["user_id"] = user_id
    if metadata:
        turn["metadata"] = metadata
    turns.append(turn)
    trimmed = turns[-MAX_STORED_TURNS:]
    path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return turn


def get_recent_context(chat_id: int | str, *, root: Path = ROOT, limit: int = 8) -> list[dict[str, str]]:
    turns = read_conversation(chat_id, root=root)[-limit:]
    return [
        {"role": str(turn.get("role", "user")), "content": str(turn.get("content", ""))}
        for turn in turns
        if turn.get("content")
    ]
