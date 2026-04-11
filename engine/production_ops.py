from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from engine.alerting import evaluate_alerts
from engine.local_health import local_health_snapshot
from engine.secret_ops import audit_secret_status
from engine.utils import ROOT, ensure_dir, now_iso


def _latest_validation(root: Path) -> dict:
    path = root / "runtime" / "reports" / "local_daily_driver_validation.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _latest_restore_drill(root: Path) -> dict:
    path = root / "runtime" / "reports" / "restore_drill.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _backup_inventory(root: Path) -> dict:
    backup_dir = root / "runtime" / "backups"
    if not backup_dir.exists():
        return {"bundle_count": 0, "latest_bundle": None, "proposal_backup_dirs": 0}
    bundles = sorted(backup_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    backup_dirs = [path for path in backup_dir.iterdir() if path.is_dir()]
    latest = str(bundles[0].relative_to(root)) if bundles else None
    return {"bundle_count": len(bundles), "latest_bundle": latest, "proposal_backup_dirs": len(backup_dirs)}


def _report_inventory(root: Path) -> dict:
    report_dir = root / "runtime" / "reports"
    if not report_dir.exists():
        return {"count": 0}
    items = sorted([path for path in report_dir.iterdir() if path.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "count": len(items),
        "latest": [str(path.relative_to(root)) for path in items[:5]],
    }


def generate_production_status(root: Path = ROOT) -> dict:
    ensure_dir(root / "runtime" / "reports" / "history")
    health = local_health_snapshot(root=root)
    alerts = evaluate_alerts(root=root)
    secrets = audit_secret_status(root=root)
    payload = {
        "generated_at": now_iso(),
        "health": health,
        "validation": _latest_validation(root),
        "restore_drill": _latest_restore_drill(root),
        "alerts": alerts,
        "secrets": secrets,
        "backups": _backup_inventory(root),
        "reports": _report_inventory(root),
    }
    latest_path = root / "runtime" / "reports" / "production_status.json"
    history_path = root / "runtime" / "reports" / "history" / f"production_status_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}.json"
    latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    history_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def render_production_dashboard(payload: dict) -> str:
    health = payload["health"]
    queue = health["queue"]
    memory = health["memory"]
    bot = health["bot"]
    validation = payload.get("validation") or {}
    validation_success = validation.get("success")
    validation_time = validation.get("validated_at")
    restore_drill = payload.get("restore_drill") or {}
    restore_success = restore_drill.get("success")
    restore_time = restore_drill.get("restored_at")
    alerts = payload.get("alerts") or {}
    secrets = payload.get("secrets") or {}
    latest_reports = payload["reports"].get("latest", [])
    backup_latest = payload["backups"].get("latest_bundle")
    backup_count = payload["backups"].get("bundle_count", 0)
    required_secret_count = len([item for item in secrets.get("secrets", []) if item.get("required")])
    present_required_secret_count = len([item for item in secrets.get("secrets", []) if item.get("required") and item.get("present")])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HAX-Mind Production Status</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; background: #0b1220; color: #e5eefc; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    .card {{ background: #121c30; border: 1px solid #24324f; border-radius: 12px; padding: 16px; }}
    .ok {{ color: #7ee787; }}
    .warn {{ color: #ffd866; }}
    code {{ color: #9ecbff; }}
    ul {{ margin-top: 8px; }}
  </style>
</head>
<body>
  <h1>HAX-Mind Production Status</h1>
  <p>Generated: <code>{payload['generated_at']}</code></p>
  <div class="grid">
    <div class="card">
      <h2>Bot</h2>
      <p class="{'ok' if bot['running'] else 'warn'}">Running: {bot['running']}</p>
      <p>PID: <code>{bot['pid']}</code></p>
      <p>Supervisor running: <code>{bot['supervisor_running']}</code></p>
    </div>
    <div class="card">
      <h2>Queue</h2>
      <p>Pending proposals: <code>{queue['pending_proposals']}</code></p>
      <p>Known proposals: <code>{queue['known_proposals']}</code></p>
      <p>Missions: <code>{queue['missions']}</code></p>
    </div>
    <div class="card">
      <h2>Memory</h2>
      <p>Tools: <code>{memory['tools']}</code></p>
      <p>Notes: <code>{memory['notes']}</code></p>
      <p>Decisions: <code>{memory.get('decisions', 0)}</code></p>
      <p>Vectors: <code>{memory.get('vector_documents', 0)}</code></p>
    </div>
    <div class="card">
      <h2>Validation</h2>
      <p class="{'ok' if validation_success else 'warn'}">Success: {validation_success}</p>
      <p>Validated at: <code>{validation_time}</code></p>
      <p>Backup bundles: <code>{backup_count}</code></p>
      <p>Latest backup: <code>{backup_latest}</code></p>
    </div>
    <div class="card">
      <h2>Restore drill</h2>
      <p class="{'ok' if restore_success else 'warn'}">Success: {restore_success}</p>
      <p>Restored at: <code>{restore_time}</code></p>
      <p>Destination: <code>{restore_drill.get('destination')}</code></p>
    </div>
    <div class="card">
      <h2>Alerts</h2>
      <p class="{'ok' if alerts.get('alert_count', 0) == 0 else 'warn'}">Alert count: {alerts.get('alert_count', 0)}</p>
      <p>Required secrets present: <code>{present_required_secret_count}/{required_secret_count}</code></p>
    </div>
  </div>
  <div class="card" style="margin-top:16px;">
    <h2>Latest reports</h2>
    <ul>
      {''.join(f'<li><code>{item}</code></li>' for item in latest_reports) or '<li>None</li>'}
    </ul>
  </div>
  <div class="card" style="margin-top:16px;">
    <h2>Active alerts</h2>
    <ul>
      {''.join(f"<li><code>[{alert['level']}] {alert['code']}</code> - {alert['message']}</li>" for alert in alerts.get('alerts', [])) or '<li>No active alerts.</li>'}
    </ul>
  </div>
</body>
</html>
"""


def write_production_dashboard(root: Path = ROOT, payload: dict | None = None) -> Path:
    payload = payload or generate_production_status(root=root)
    dashboard_dir = root / "runtime" / "dashboard"
    ensure_dir(dashboard_dir)
    path = dashboard_dir / "index.html"
    path.write_text(render_production_dashboard(payload), encoding="utf-8")
    return path


def _backup_sources(root: Path) -> list[Path]:
    return [
        root / "bot",
        root / "docs",
        root / "engine",
        root / "jobs",
        root / "memory",
        root / "policies",
        root / "runtime" / "reports",
        root / "runtime" / "missions",
        root / "runtime" / "proposals",
        root / "runtime" / "task_plans",
        root / "runtime" / "dashboard",
        root / "scripts",
        root / "workspace",
        root / "README.md",
        root / "requirements.txt",
        root / "run-health.cmd",
        root / "run-recover.cmd",
        root / "run-validate-local.cmd",
    ]


def create_backup_bundle(root: Path = ROOT) -> Path:
    backup_dir = root / "runtime" / "backups"
    ensure_dir(backup_dir)
    bundle_name = f"haxmind_backup_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}.zip"
    bundle_path = backup_dir / bundle_name

    with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
        for source in _backup_sources(root):
            if not source.exists():
                continue
            if source.is_file():
                archive.write(source, source.relative_to(root))
                continue
            for path in source.rglob("*"):
                if path.is_dir():
                    continue
                if "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                archive.write(path, path.relative_to(root))
    return bundle_path


def latest_backup_bundle(root: Path = ROOT) -> Path | None:
    backup_dir = root / "runtime" / "backups"
    bundles = sorted(backup_dir.glob("haxmind_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return bundles[0] if bundles else None


def restore_backup_bundle(bundle_path: Path | None = None, *, destination: Path | None = None, root: Path = ROOT) -> dict:
    bundle_path = bundle_path or latest_backup_bundle(root=root)
    if bundle_path is None or not bundle_path.exists():
        raise FileNotFoundError("No backup bundle found")

    destination = destination or (root / "runtime" / "restore_drills" / f"restore_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}")
    ensure_dir(destination)

    with ZipFile(bundle_path, "r") as archive:
        archive.extractall(destination)
        members = archive.namelist()

    manifest = {
        "bundle": str(bundle_path.relative_to(root) if bundle_path.is_relative_to(root) else bundle_path),
        "destination": str(destination.relative_to(root) if destination.is_relative_to(root) else destination),
        "restored_at": now_iso(),
        "file_count": len(members),
        "sample_files": members[:20],
    }
    (destination / "restore_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def validate_restore_target(destination: Path, root: Path = ROOT) -> dict:
    required = [
        "README.md",
        "requirements.txt",
        "bot/telegram_bot.py",
        "engine/apply_engine.py",
        "scripts/get-local-health.ps1",
        "docs/cto-handoff-status.md",
    ]
    missing = [path for path in required if not (destination / path).exists()]
    result = {
        "validated_at": now_iso(),
        "destination": str(destination.relative_to(root) if destination.is_relative_to(root) else destination),
        "required_count": len(required),
        "missing": missing,
        "success": len(missing) == 0,
    }
    (destination / "restore_validation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def run_restore_drill(root: Path = ROOT, bundle_path: Path | None = None) -> dict:
    destination = root / "runtime" / "restore_drills" / f"restore_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}"
    manifest = restore_backup_bundle(bundle_path=bundle_path, destination=destination, root=root)
    validation = validate_restore_target(destination, root=root)
    summary = {
        "bundle": manifest["bundle"],
        "destination": manifest["destination"],
        "restored_at": manifest["restored_at"],
        "file_count": manifest["file_count"],
        "success": validation["success"],
        "missing": validation["missing"],
    }
    ensure_dir(root / "runtime" / "reports")
    latest_path = root / "runtime" / "reports" / "restore_drill.json"
    latest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
