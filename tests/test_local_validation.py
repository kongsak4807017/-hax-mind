from engine.local_validation import build_validation_payload, render_local_daily_driver_validation


def test_build_validation_payload_and_render(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    steps = [
        {"name": "startup_launcher_recovery", "success": True, "detail": "ok"},
        {"name": "tool_ingest_job", "success": True, "detail": "ok"},
    ]

    payload = build_validation_payload(steps, root=tmp_path)
    text = render_local_daily_driver_validation(payload, root=tmp_path)

    assert payload["success"] is True
    assert "## Validation steps" in text
    assert "startup_launcher_recovery" in text
    assert "Local Health Snapshot" in text
