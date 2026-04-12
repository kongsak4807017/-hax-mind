from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.utils import ROOT, ensure_dir, now_iso


CONFIRMATION_DIR = ROOT / "runtime" / "confirmations"
CONFIRM_WORDS = {"yes", "y", "confirm", "confirmed", "ok", "okay", "do it", "run it", "execute it", "ยืนยัน", "ตกลง"}
CANCEL_WORDS = {"no", "n", "cancel", "stop", "abort", "ไม่", "ไม่เอา", "ยกเลิก"}


def _confirmation_path(chat_id: int | str, root: Path = ROOT) -> Path:
    return root / "runtime" / "confirmations" / f"{chat_id}.json"


def get_pending_confirmation(chat_id: int | str, *, root: Path = ROOT) -> dict[str, Any] | None:
    path = _confirmation_path(chat_id, root=root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return None
    if not isinstance(data, dict):
        path.unlink(missing_ok=True)
        return None
    return data


def save_pending_confirmation(
    chat_id: int | str,
    *,
    user_id: int | None,
    action: str,
    plan: dict[str, Any],
    summary: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    path = _confirmation_path(chat_id, root=root)
    ensure_dir(path.parent)
    payload = {
        "created_at": now_iso(),
        "chat_id": chat_id,
        "user_id": user_id,
        "action": action,
        "plan": plan,
        "summary": summary,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def clear_pending_confirmation(chat_id: int | str, *, root: Path = ROOT) -> None:
    _confirmation_path(chat_id, root=root).unlink(missing_ok=True)


def interpret_confirmation_reply(text: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    if normalized in CONFIRM_WORDS:
        return "confirm"
    if normalized in CANCEL_WORDS:
        return "cancel"
    return "unknown"
