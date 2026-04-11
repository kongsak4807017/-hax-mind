from pathlib import Path

from engine.production_ops import create_backup_bundle, generate_production_status, write_production_dashboard
from engine.memory_store import initialize_memory_dirs


def test_generate_production_status_and_dashboard(tmp_path, monkeypatch):
    initialize_memory_dirs(tmp_path)
    (tmp_path / "runtime" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "reports" / "morning_report.txt").write_text("Morning Report\n", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    payload = generate_production_status(root=tmp_path)
    dashboard = write_production_dashboard(root=tmp_path, payload=payload)

    assert (tmp_path / "runtime" / "reports" / "production_status.json").exists()
    assert dashboard.exists()
    assert "health" in payload


def test_create_backup_bundle_writes_zip(tmp_path):
    initialize_memory_dirs(tmp_path)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "sample.md").write_text("sample\n", encoding="utf-8")

    bundle = create_backup_bundle(root=tmp_path)

    assert bundle.exists()
    assert bundle.suffix == ".zip"
