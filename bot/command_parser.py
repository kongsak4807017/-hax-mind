from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Command:
    action: str
    target: Optional[str] = None
    args: Optional[str] = None


def parse_command(text: str) -> Command:
    text = text.strip()
    if not text.startswith("/"):
        return Command(action="message", args=text)
    parts = text.split(maxsplit=2)
    action = parts[0][1:].lower()
    target = parts[1] if len(parts) > 1 else None
    args = parts[2] if len(parts) > 2 else None
    return Command(action=action, target=target, args=args)
