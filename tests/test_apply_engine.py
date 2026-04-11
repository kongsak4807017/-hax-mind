from pathlib import Path

import pytest

import engine.apply_engine as apply_engine
from engine.proposal_engine import create_proposal, get_proposal, update_proposal_status
from engine.rollback_engine import rollback_proposal


def _proposal_metadata(path: str, content: str, mode: str = "replace") -> dict:
    return {"file_changes": [{"path": path, "content": content, "mode": mode}]}


def test_execute_proposal_safe_requires_approval(tmp_path):
    proposal = create_proposal(
        title="test proposal",
        component="tests",
        problem="need test",
        root_cause="test",
        solution="run tests",
        expected_impact="verified",
        risk="medium",
        files_to_modify=[],
        tests_to_run=["tests/test_tool_registry.py"],
        rollback_plan="none",
        root=tmp_path,
    )
    with pytest.raises(PermissionError):
        apply_engine.execute_proposal_safe(proposal["id"], root=tmp_path)


def test_execute_proposal_safe_runs_tests_without_changes(tmp_path, monkeypatch):
    proposal = create_proposal(
        title="test proposal approved",
        component="tests",
        problem="need test",
        root_cause="test",
        solution="run tests",
        expected_impact="verified",
        risk="medium",
        files_to_modify=[],
        tests_to_run=["tests/test_tool_registry.py"],
        rollback_plan="none",
        root=tmp_path,
    )
    update_proposal_status(proposal["id"], "approved", root=tmp_path)
    monkeypatch.setattr(apply_engine, "run_tests", lambda targets: {"all_passed": True, "results": [{"target": targets[0], "passed": True}]})

    result = apply_engine.execute_proposal_safe(proposal["id"], root=tmp_path)

    assert result["status"] == "executed_safe"
    assert result["all_passed"] is True
    saved = get_proposal(proposal["id"], root=tmp_path)
    assert saved["execution_mode"] == "safe_check_only_no_source_modifications"


def test_execute_proposal_real_apply_creates_backup_and_diff(tmp_path, monkeypatch):
    target = tmp_path / "docs" / "apply_target.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("before\n", encoding="utf-8")

    proposal = create_proposal(
        title="real apply",
        component="docs",
        problem="need update",
        root_cause="test",
        solution="write file",
        expected_impact="updated",
        risk="low",
        files_to_modify=["docs/apply_target.md"],
        tests_to_run=["tests"],
        rollback_plan="restore backup",
        metadata=_proposal_metadata("docs/apply_target.md", "after\n"),
        root=tmp_path,
    )
    update_proposal_status(proposal["id"], "approved", root=tmp_path)
    monkeypatch.setattr(apply_engine, "run_tests", lambda targets: {"all_passed": True, "results": [{"target": "tests", "passed": True}]})

    result = apply_engine.execute_proposal_safe(proposal["id"], root=tmp_path)

    assert result["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "after\n"
    assert (tmp_path / "runtime" / "patches" / f"{proposal['id']}.diff").exists()
    assert (tmp_path / "runtime" / "backups" / proposal["id"] / "manifest.json").exists()
    saved = get_proposal(proposal["id"], root=tmp_path)
    assert saved["status"] == "applied"
    assert saved["applied_files"] == ["docs/apply_target.md"]


def test_execute_proposal_real_apply_rolls_back_on_failed_tests(tmp_path, monkeypatch):
    target = tmp_path / "docs" / "rollback_target.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("before\n", encoding="utf-8")

    proposal = create_proposal(
        title="rollback apply",
        component="docs",
        problem="need update",
        root_cause="test",
        solution="write file",
        expected_impact="updated",
        risk="low",
        files_to_modify=["docs/rollback_target.md"],
        tests_to_run=["tests"],
        rollback_plan="restore backup",
        metadata=_proposal_metadata("docs/rollback_target.md", "after\n"),
        root=tmp_path,
    )
    update_proposal_status(proposal["id"], "approved", root=tmp_path)
    monkeypatch.setattr(apply_engine, "run_tests", lambda targets: {"all_passed": False, "results": [{"target": "tests", "passed": False}]})

    result = apply_engine.execute_proposal_safe(proposal["id"], root=tmp_path)

    assert result["status"] == "rolled_back_failed_tests"
    assert result["rolled_back"] is True
    assert target.read_text(encoding="utf-8") == "before\n"
    saved = get_proposal(proposal["id"], root=tmp_path)
    assert saved["status"] == "rolled_back_failed_tests"


def test_execute_proposal_real_apply_blocks_protected_paths(tmp_path):
    proposal = create_proposal(
        title="protected path",
        component="secrets",
        problem="bad write",
        root_cause="test",
        solution="write env",
        expected_impact="none",
        risk="low",
        files_to_modify=[".env"],
        tests_to_run=["tests"],
        rollback_plan="none",
        metadata=_proposal_metadata(".env", "SHOULD_NOT_WRITE=1\n"),
        root=tmp_path,
    )
    update_proposal_status(proposal["id"], "approved", root=tmp_path)

    with pytest.raises(PermissionError):
        apply_engine.execute_proposal_safe(proposal["id"], root=tmp_path)


def test_rollback_removes_newly_created_files(tmp_path):
    proposal = create_proposal(
        title="create file",
        component="docs",
        problem="need file",
        root_cause="test",
        solution="create file",
        expected_impact="created",
        risk="low",
        files_to_modify=["docs/new_file.md"],
        tests_to_run=["tests"],
        rollback_plan="delete created file",
        metadata=_proposal_metadata("docs/new_file.md", "created\n", mode="create"),
        root=tmp_path,
    )
    update_proposal_status(proposal["id"], "approved", root=tmp_path)

    # Create backup manifest by executing backup/apply helpers through main flow with passing tests.
    original_run_tests = apply_engine.run_tests
    try:
        apply_engine.run_tests = lambda targets: {"all_passed": True, "results": [{"target": "tests", "passed": True}]}
        result = apply_engine.execute_proposal_safe(proposal["id"], root=tmp_path)
        assert result["status"] == "applied"
    finally:
        apply_engine.run_tests = original_run_tests

    created = tmp_path / "docs" / "new_file.md"
    assert created.exists()

    rollback = rollback_proposal(proposal["id"], root=tmp_path)
    assert rollback["ok"] is True
    assert not created.exists()
