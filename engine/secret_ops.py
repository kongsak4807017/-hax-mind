from __future__ import annotations

import json
import os
from pathlib import Path

from engine.utils import ROOT, now_iso, read_env_file

REQUIRED_SECRETS = [
    {"name": "TELEGRAM_BOT_TOKEN", "required": True, "rotation_days": 90},
    {"name": "OPENROUTER_API_KEY", "required": False, "rotation_days": 90},
    {"name": "BRAVE_SEARCH_API_KEY", "required": False, "rotation_days": 90},
    {"name": "NEWS_API", "required": False, "rotation_days": 90},
    {"name": "NEWS_API_KEY", "required": False, "rotation_days": 90},
    {"name": "PICOCLAW_SHARED_SECRET", "required": False, "rotation_days": 90},
    {"name": "PICOCLAW_WORKER_SECRET", "required": False, "rotation_days": 90},
]


def audit_secret_status(root: Path = ROOT) -> dict:
    read_env_file()
    env_candidates = [root / ".env", root / ".env.txt"]
    payload = {
        "generated_at": now_iso(),
        "env_files": [{"path": str(path.relative_to(root)), "exists": path.exists()} for path in env_candidates],
        "secrets": [],
    }
    for item in REQUIRED_SECRETS:
        value = os.environ.get(item["name"])
        payload["secrets"].append(
            {
                "name": item["name"],
                "required": item["required"],
                "present": bool(value),
                "rotation_days": item["rotation_days"],
            }
        )
    reports_dir = root / "runtime" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "secret_status.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
