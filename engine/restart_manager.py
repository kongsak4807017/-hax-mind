from __future__ import annotations

import subprocess
from pathlib import Path

from engine.utils import ROOT, now_iso


def request_bot_restart(root: Path = ROOT, delay_seconds: int = 2) -> dict[str, str]:
    script = root / "scripts" / "restart-telegram-bot.ps1"
    if not script.exists():
        raise FileNotFoundError(f"Restart script not found: {script}")

    subprocess.Popen(
        [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ProjectRoot",
            str(root),
            "-DelaySeconds",
            str(delay_seconds),
        ],
        cwd=str(root),
    )
    return {
        "status": "scheduled",
        "requested_at": now_iso(),
        "delay_seconds": str(delay_seconds),
        "script": str(script.relative_to(root)),
    }
