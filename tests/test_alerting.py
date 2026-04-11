from engine.alerting import evaluate_alerts, render_alert_summary
from engine.memory_store import initialize_memory_dirs


def test_alerting_reports_missing_validation_and_backups(tmp_path, monkeypatch):
    initialize_memory_dirs(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    payload = evaluate_alerts(root=tmp_path)
    text = render_alert_summary(payload)

    assert payload["alert_count"] >= 2
    assert "validation_stale" in text
    assert "no_backup_bundle" in text
