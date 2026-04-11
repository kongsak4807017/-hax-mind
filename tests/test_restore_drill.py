from engine.memory_store import initialize_memory_dirs
from engine.production_ops import create_backup_bundle, restore_backup_bundle, run_restore_drill, validate_restore_target


def test_restore_backup_bundle_extracts_and_validates(tmp_path):
    initialize_memory_dirs(tmp_path)
    (tmp_path / "bot").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bot" / "telegram_bot.py").write_text("print('bot')\n", encoding="utf-8")
    (tmp_path / "engine" / "apply_engine.py").write_text("print('apply')\n", encoding="utf-8")
    (tmp_path / "scripts" / "get-local-health.ps1").write_text("Write-Host ok\n", encoding="utf-8")
    (tmp_path / "docs" / "cto-handoff-status.md").write_text("# status\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    bundle = create_backup_bundle(root=tmp_path)
    manifest = restore_backup_bundle(bundle_path=bundle, root=tmp_path)
    result = validate_restore_target(tmp_path / manifest["destination"], root=tmp_path)

    assert result["success"] is True


def test_run_restore_drill_writes_summary(tmp_path):
    initialize_memory_dirs(tmp_path)
    (tmp_path / "bot").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bot" / "telegram_bot.py").write_text("print('bot')\n", encoding="utf-8")
    (tmp_path / "engine" / "apply_engine.py").write_text("print('apply')\n", encoding="utf-8")
    (tmp_path / "scripts" / "get-local-health.ps1").write_text("Write-Host ok\n", encoding="utf-8")
    (tmp_path / "docs" / "cto-handoff-status.md").write_text("# status\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    create_backup_bundle(root=tmp_path)
    summary = run_restore_drill(root=tmp_path)

    assert summary["success"] is True
    assert (tmp_path / "runtime" / "reports" / "restore_drill.json").exists()
