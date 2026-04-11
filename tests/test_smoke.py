from pathlib import Path

from bot.command_parser import parse_command
from engine.memory_analyzer import summarize_today
from engine.morning_report import generate_morning_report
from engine.self_improvement_engine import generate_improvement_proposal


def test_project_dirs_exist():
    for name in ["memory", "runtime", "policies", "engine", "bot", "jobs"]:
        assert Path(name).exists()


def test_command_parser():
    cmd = parse_command("/approve prop_123")
    assert cmd.action == "approve"
    assert cmd.target == "prop_123"


def test_memory_summary_runs():
    assert "Daily Summary" in summarize_today()


def test_proposal_creation_and_report():
    proposal = generate_improvement_proposal()
    proposal_path = Path("runtime/proposals", f"{proposal['id']}.json")
    assert proposal["risk"] == "low"
    assert proposal_path.exists()
    report = generate_morning_report()
    assert "Morning Report" in report
    proposal_path.unlink(missing_ok=True)
