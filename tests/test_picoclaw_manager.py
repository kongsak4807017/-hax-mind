from engine.mission_engine import create_mission
from engine.picoclaw_manager import (
    claim_remote_job,
    complete_remote_job,
    issue_remote_job_from_mission,
    picoclaw_plan,
    picoclaw_status,
    record_worker_heartbeat,
)
from engine.project_manager import register_project


def test_picoclaw_status_and_plan(tmp_path):
    state = picoclaw_status(root=tmp_path)
    assert state["component"] == "PicoClaw"
    assert state["readiness"]["local_telegram_bot"] is True
    assert state["readiness"]["remote_job_queue"] is True

    plan = picoclaw_plan(root=tmp_path)
    assert "PicoClaw Phase 2 Plan" in plan
    assert (tmp_path / "docs" / "picoclaw-phase2.md").exists()


def test_picoclaw_heartbeat_requires_shared_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("PICOCLAW_SHARED_SECRET", "phase2-secret")
    record = record_worker_heartbeat(
        "termux-alpha",
        "phase2-secret",
        platform="termux",
        capabilities=["read_only_repo"],
        root=tmp_path,
    )
    assert record["worker_id"] == "termux-alpha"
    state = picoclaw_status(root=tmp_path)
    assert state["readiness"]["worker_auth_secret_configured"] is True
    assert state["readiness"]["heartbeat_endpoint"] is True
    assert state["readiness"]["termux_worker_installed"] is True
    assert "termux-alpha" in state["workers"]


def test_picoclaw_queue_claim_complete_remote_job(tmp_path, monkeypatch):
    monkeypatch.setenv("PICOCLAW_SHARED_SECRET", "phase2-secret")
    register_project("HAXMind", str(tmp_path), root=tmp_path)
    mission = create_mission("haxmind", "Inspect the repo and summarize the next safe changes", root=tmp_path)

    job = issue_remote_job_from_mission(mission["id"], root=tmp_path)
    assert job["status"] == "pending"
    assert job["mode"] == "remote_read_only"

    claim = claim_remote_job("termux-alpha", "phase2-secret", root=tmp_path)
    assert claim is not None
    assert claim["id"] == job["id"]
    assert claim["status"] == "claimed"

    completed = complete_remote_job(
        job["id"],
        "termux-alpha",
        "phase2-secret",
        status="completed",
        summary="Repo inspected without source modifications.",
        root=tmp_path,
    )
    assert completed["status"] == "completed"
    assert completed["result"]["summary"] == "Repo inspected without source modifications."

    state = picoclaw_status(root=tmp_path)
    assert state["queue"]["completed"] == 1
