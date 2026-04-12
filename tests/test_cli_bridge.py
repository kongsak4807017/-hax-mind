from pathlib import Path

from engine.cli_bridge import (
    approve_cli_session,
    close_cli_session,
    continue_cli_session,
    create_cli_improvement_proposal,
    get_cli_session,
    get_cli_job,
    latest_cli_job,
    latest_cli_session,
    open_cli_session,
    render_cli_job_detail,
    render_cli_jobs_summary,
    render_cli_session_detail,
    render_cli_sessions_summary,
    set_cli_session_profile,
    start_cli_session,
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
    launcher = tmp_path / stored["launcher_path"]
    assert launcher.exists()
    assert "help me inspect this repo" in launcher.read_text(encoding="utf-8")


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
    assert latest_cli_job(root=tmp_path)["id"] == job["id"]
    assert "CLI job:" in render_cli_job_detail(job)


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


def test_kimi_session_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.cli_bridge._available_tool_or_raise", lambda tool_key: type("Tool", (), {"key": tool_key, "title": tool_key, "mode": "hybrid", "executable": "fake.exe", "scripted_session": True})())
    monkeypatch.setattr("engine.cli_bridge.log_event", lambda *args, **kwargs: None)

    class Result:
        returncode = 0
        stdout = "step ok"
        stderr = ""

    monkeypatch.setattr("engine.cli_bridge.subprocess.run", lambda *args, **kwargs: Result())

    session, first_job = start_cli_session("kimi", "first step", root=tmp_path)
    next_job = continue_cli_session(session["id"], "second step", root=tmp_path)
    session_state = get_cli_session(session["id"], root=tmp_path)
    closed = close_cli_session(session["id"], root=tmp_path)

    assert first_job["session_id"] == session["id"]
    assert next_job["session_id"] == session["id"]
    assert session_state["step_count"] == 2
    assert latest_cli_session(root=tmp_path)["id"] == session["id"]
    assert "CLI session:" in render_cli_session_detail(session_state)
    assert session["id"] in render_cli_sessions_summary(root=tmp_path)
    assert closed["status"] == "closed"


def test_codex_session_requires_approval_for_write_capable_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.cli_bridge._available_tool_or_raise", lambda tool_key: type("Tool", (), {"key": tool_key, "title": tool_key, "mode": "hybrid", "executable": "fake.exe", "scripted_session": True})())
    monkeypatch.setattr("engine.cli_bridge.log_event", lambda *args, **kwargs: None)

    class Result:
        returncode = 0
        stdout = '{"type":"thread.started","thread_id":"thread-1"}\n{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}'
        stderr = ""

    monkeypatch.setattr("engine.cli_bridge._run_subprocess", lambda *args, **kwargs: Result())

    session, first_job = start_cli_session("codex", "first review", root=tmp_path, profile="review")
    session = set_cli_session_profile(session["id"], "default", root=tmp_path)
    try:
        continue_cli_session(session["id"], "write now", root=tmp_path)
        assert False, "Expected approval gate to block continuation"
    except PermissionError:
        pass
    approved = approve_cli_session(session["id"], root=tmp_path)
    next_job = continue_cli_session(session["id"], "write now", root=tmp_path)

    assert first_job["session_id"] == session["id"]
    assert approved["approved"] is True
    assert next_job["session_id"] == session["id"]


def test_gemini_session_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.cli_bridge._available_tool_or_raise", lambda tool_key: type("Tool", (), {"key": tool_key, "title": tool_key, "mode": "hybrid", "executable": "fake.exe", "scripted_session": True})())
    monkeypatch.setattr("engine.cli_bridge.log_event", lambda *args, **kwargs: None)

    class Result:
        returncode = 0
        stdout = "gemini ok"
        stderr = ""

    monkeypatch.setattr("engine.cli_bridge._run_subprocess", lambda *args, **kwargs: Result())
    monkeypatch.setattr("engine.cli_bridge._list_gemini_sessions", lambda cwd: "1. Test [gem-session-1]")

    session, job = start_cli_session("gemini", "hello", root=tmp_path, profile="plan")
    next_job = continue_cli_session(session["id"], "second", root=tmp_path)

    assert session["tool"] == "gemini"
    assert session["profile"] == "plan"
    assert job["session_id"] == session["id"]
    assert next_job["session_id"] == session["id"]


def test_omx_session_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.cli_bridge._available_tool_or_raise", lambda tool_key: type("Tool", (), {"key": tool_key, "title": tool_key, "mode": "hybrid", "executable": "fake.exe", "scripted_session": True})())
    monkeypatch.setattr("engine.cli_bridge.log_event", lambda *args, **kwargs: None)

    class Result:
        returncode = 0
        stdout = '{"type":"thread.started","thread_id":"omx-thread"}\n{"type":"item.completed","item":{"type":"agent_message","text":"omx ok"}}'
        stderr = ""

    monkeypatch.setattr("engine.cli_bridge._run_subprocess", lambda *args, **kwargs: Result())

    session, job = start_cli_session("omx", "hello", root=tmp_path, profile="review")
    approved = approve_cli_session(session["id"], root=tmp_path)
    next_job = continue_cli_session(session["id"], "second", root=tmp_path)

    assert session["tool"] == "omx"
    assert approved["approved"] is True
    assert job["session_id"] == session["id"]
    assert next_job["session_id"] == session["id"]
