from engine.mission_engine import create_execution_proposal_from_mission, create_mission, list_missions, update_mission_status
from engine.project_manager import get_project, list_projects, register_project


def test_register_project_and_create_mission(tmp_path):
    project = register_project("Demo", "kongsak4807017/demo", root=tmp_path)
    assert project["id"] == "demo"
    assert get_project("demo", root=tmp_path)["path_or_repo"] == "kongsak4807017/demo"
    assert len(list_projects(root=tmp_path)) == 1

    mission = create_mission("demo", "build a Telegram command for reports", root=tmp_path)
    assert mission["project_id"] == "demo"
    assert mission["status"] == "planned"
    assert (tmp_path / "runtime" / "task_plans" / f"{mission['id']}.md").exists()
    assert len(list_missions(root=tmp_path)) == 1

    updated = update_mission_status(mission["id"], "done", root=tmp_path)
    assert updated["status"] == "done"


def test_create_execution_proposal_from_mission(tmp_path, monkeypatch):
    project = register_project("Demo", "kongsak4807017/demo", root=tmp_path)
    mission = create_mission(project["id"], "write a safe implementation plan", root=tmp_path)

    import engine.mission_engine as mission_engine

    monkeypatch.setattr(mission_engine, "ROOT", tmp_path)
    proposal = create_execution_proposal_from_mission(mission["id"], root=tmp_path)

    assert proposal["metadata"]["mission_id"] == mission["id"]
    assert proposal["risk"] == "medium"
    assert proposal["status"] == "pending"


def test_create_execution_proposal_from_structured_mission(tmp_path):
    project_root = tmp_path / "workspace" / "demo"
    project_root.mkdir(parents=True, exist_ok=True)
    readme = project_root / "README.md"
    readme.write_text("# Demo\n", encoding="utf-8")

    project = register_project("Demo", str(project_root), root=tmp_path)
    mission = create_mission(project["id"], "append README.md :: Added from mission", root=tmp_path)
    proposal = create_execution_proposal_from_mission(mission["id"], root=tmp_path)

    assert mission["execution_directive"]["action"] == "append"
    assert proposal["metadata"]["execution_mode"] == "guarded_real_apply"
    assert proposal["files_to_modify"] == ["README.md"]
    assert proposal["metadata"]["file_changes"][0]["content"] == "# Demo\nAdded from mission"
