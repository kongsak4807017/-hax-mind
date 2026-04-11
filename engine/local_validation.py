from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.local_health import local_health_snapshot, render_local_health_summary
from engine.utils import ROOT, ensure_dir, now_iso


def render_local_daily_driver_validation(payload: dict[str, Any], root: Path = ROOT) -> str:
    health = payload["health"]
    steps = payload["steps"]
    lines = [
        "# Local Daily Driver Validation",
        "",
        f"Validated: {payload['validated_at']}",
        "",
        "## Summary",
        f"- Overall success: {payload['success']}",
        f"- Startup launcher path: {payload['startup_launcher']}",
        "",
        "## Validation steps",
    ]
    for step in steps:
        lines.extend(
            [
                f"### {step['name']}",
                f"- Success: {step['success']}",
                f"- Detail: {step['detail']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Local Health Snapshot",
            "```text",
            render_local_health_summary(root=root).rstrip(),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def save_local_daily_driver_validation(payload: dict[str, Any], root: Path = ROOT) -> dict[str, str]:
    ensure_dir(root / "runtime" / "reports")
    json_path = root / "runtime" / "reports" / "local_daily_driver_validation.json"
    md_path = root / "docs" / "local-daily-driver-validation.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_local_daily_driver_validation(payload, root=root) + "\n", encoding="utf-8")
    return {
        "json_path": str(json_path.relative_to(root)),
        "markdown_path": str(md_path.relative_to(root)),
    }


def build_validation_payload(steps: list[dict[str, Any]], root: Path = ROOT) -> dict[str, Any]:
    snapshot = local_health_snapshot(root=root)
    success = all(step["success"] for step in steps)
    return {
        "validated_at": now_iso(),
        "success": success,
        "startup_launcher": snapshot["automation"]["startup_launcher"],
        "steps": steps,
        "health": snapshot,
    }
