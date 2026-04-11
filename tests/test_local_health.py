from pathlib import Path

from engine.local_health import local_health_snapshot, render_local_health_summary
from engine.memory_store import initialize_memory_dirs
from engine.proposal_engine import create_proposal


def test_local_health_snapshot_reads_bot_queue_and_memory(tmp_path, monkeypatch):
    initialize_memory_dirs(tmp_path)
    (tmp_path / "runtime" / "telegram_bot.pid").write_text("12345", encoding="utf-8")
    (tmp_path / "runtime" / "telegram_bot_supervisor.pid").write_text("12346", encoding="utf-8")
    (tmp_path / "runtime" / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "logs" / "telegram_bot.lifecycle.log").write_text("ok\n", encoding="utf-8")
    (tmp_path / "runtime" / "logs" / "telegram_bot_supervisor.log").write_text("ok\n", encoding="utf-8")
    (tmp_path / "runtime" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "reports" / "morning_report.txt").write_text("Morning Report\n", encoding="utf-8")
    (tmp_path / "runtime" / "missions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "missions" / "task_demo.json").write_text("{}", encoding="utf-8")
    create_proposal(
        title="demo",
        component="demo",
        problem="demo",
        root_cause="demo",
        solution="demo",
        expected_impact="demo",
        risk="low",
        files_to_modify=[],
        tests_to_run=["tests"],
        rollback_plan="none",
        root=tmp_path,
    )

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    startup = Path(tmp_path / "appdata" / "Microsoft/Windows/Start Menu/Programs/Startup")
    startup.mkdir(parents=True, exist_ok=True)
    (startup / "HAX-Mind-Telegram-Bot.cmd").write_text("start\n", encoding="utf-8")

    snapshot = local_health_snapshot(root=tmp_path, pid_checker=lambda pid: pid in {12345, 12346})

    assert snapshot["bot"]["running"] is True
    assert snapshot["bot"]["supervisor_running"] is True
    assert snapshot["queue"]["pending_proposals"] == 1
    assert snapshot["queue"]["missions"] == 1
    assert snapshot["automation"]["startup_launcher_exists"] is True


def test_render_local_health_summary_contains_sections(tmp_path, monkeypatch):
    initialize_memory_dirs(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    text = render_local_health_summary(root=tmp_path, pid_checker=lambda pid: False)

    assert "Bot:" in text
    assert "Queue:" in text
    assert "Memory:" in text
    assert "Automation:" in text
