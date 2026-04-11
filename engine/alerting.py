from __future__ import annotations

import json
from pathlib import Path

from engine.local_health import local_health_snapshot
from engine.utils import ROOT, ensure_dir, now_iso


def evaluate_alerts(root: Path = ROOT) -> dict:
    health = local_health_snapshot(root=root)
    reports_dir = root / "runtime" / "reports"
    validation_path = reports_dir / "local_daily_driver_validation.json"
    restore_path = reports_dir / "restore_drill.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else {}
    restore = json.loads(restore_path.read_text(encoding="utf-8")) if restore_path.exists() else {}
    backup_count = len(list((root / "runtime" / "backups").glob("haxmind_backup_*.zip")))
    alerts: list[dict] = []

    bot = health["bot"]
    queue = health["queue"]

    def add_alert(level: str, code: str, message: str) -> None:
        alerts.append({"level": level, "code": code, "message": message})

    if not bot.get("running"):
        add_alert("critical", "bot_down", "Telegram bot is not running.")
    if not bot.get("supervisor_running"):
        add_alert("high", "supervisor_missing", "Telegram bot supervisor is not running.")
    if queue.get("pending_proposals", 0) > 0:
        add_alert("medium", "pending_proposals", f"Pending proposals remain: {queue['pending_proposals']}.")
    if not validation.get("success", False):
        add_alert("medium", "validation_stale", "Local daily-driver validation is missing or failing.")
    if not restore.get("success", False):
        add_alert("medium", "restore_drill_missing", "Restore drill is missing or failing.")
    if backup_count == 0:
        add_alert("high", "no_backup_bundle", "No backup bundle exists.")

    payload = {
        "generated_at": now_iso(),
        "alert_count": len(alerts),
        "alerts": alerts,
        "status_snapshot": {
            "bot_running": bot.get("running"),
            "supervisor_running": bot.get("supervisor_running"),
            "pending_proposals": queue.get("pending_proposals", 0),
            "backup_bundles": backup_count,
            "restore_success": restore.get("success"),
            "validation_success": validation.get("success"),
        },
    }
    ensure_dir(reports_dir / "history")
    (reports_dir / "alerts.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    history = reports_dir / "history" / f"alerts_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}.json"
    history.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def render_alert_summary(payload: dict) -> str:
    lines = [f"Alerts - {payload['generated_at']}", f"Alert count: {payload['alert_count']}", ""]
    if not payload["alerts"]:
        lines.append("No active alerts.")
    else:
        for alert in payload["alerts"]:
            lines.append(f"- [{alert['level']}] {alert['code']}: {alert['message']}")
    return "\n".join(lines) + "\n"
