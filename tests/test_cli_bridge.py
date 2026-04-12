from pathlib import Path

from engine.cli_bridge import (
    create_cli_improvement_proposal,
    get_cli_job,
    open_cli_session,
    render_cli_jobs_summary,
    run_cli_once,
)


def test_open_cli_session_records_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.cli_bridge._available_tool_or_raise", lambda tool_key: type("Tool", (), {"key": tool_key, "title": tool_key, "mode": "hybrid", "executable": "fake.exe"})())
    monkeypatch.setattr("engine.cli_bridge.subprocess.Popen", lambda *args, **kwargs: None)
    monkeypatch.setattr("engine.cli_bridge.log_event", lambda *args, **kwargs: None)

    job = open_cli_session("codex", "help me inspect this repo", root=tmp_path)

    assert job["status"] == "opened"
    stored = get_cli_job(job["id"], root=tmp_path)
    assert stored["tool"] == "codex"


def test_run_cli_once_records_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.cli_bridge._available_tool_or_raise", lambda tool_key: type("Tool", (), {"key": tool_key, "title": tool_key, "mode": "hybrid", "executable": "fake.exe"})())
    monkeypatch.setattr("engine.cli_bridge.log_event", lambda *args, **kwargs: None)

    class Result:
        returncode = 0
        stdout = "done"
        stderr = ""

    monkeypatch.setattr("engine.cli_bridge.subprocess.run", lambda *args, **kwargs: Result())

    job = run_cli_once("gemini", "summarize status", root=tmp_path)

    assert job["status"] == "completed"
    assert Path(tmp_path / job["output_path"]).exists()
    assert "done" in render_cli_jobs_summary(root=tmp_path, limit=5) or job["id"] in render_cli_jobs_summary(root=tmp_path, limit=5)


def test_cli_improvement_proposal_uses_job_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.cli_bridge._available_tool_or_raise", lambda tool_key: type("Tool", (), {"key": tool_key, "title": tool_key, "mode": "hybrid", "executable": "fake.exe"})())
    monkeypatch.setattr("engine.cli_bridge.log_event", lambda *args, **kwargs: None)

    class Failed:
        returncode = 1
        stdout = ""
        stderr = "bad"

    monkeypatch.setattr("engine.cli_bridge.subprocess.run", lambda *args, **kwargs: Failed())
    run_cli_once("kimi", "do a thing", root=tmp_path)
    proposal = create_cli_improvement_proposal(root=tmp_path)

    assert proposal["component"] == "cli_orchestration"
    assert proposal["risk"] == "medium"
