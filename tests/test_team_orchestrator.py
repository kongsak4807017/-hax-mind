from engine.mission_engine import create_mission
from engine.project_manager import register_project
from engine.team_orchestrator import create_team_plan, get_team_plan, list_team_plans


def test_create_and_list_team_plans(tmp_path):
    project = register_project("HAXMind", "workspace/haxmind", root=tmp_path)
    mission = create_mission(project["id"], "Improve memory retrieval and testing workflow", root=tmp_path)

    plan = create_team_plan(mission["id"], root=tmp_path)

    assert plan["mission_id"] == mission["id"]
    assert len(plan["lanes"]) == 4
    assert any(lane["role"] == "executor" for lane in plan["lanes"])

    loaded = get_team_plan(mission["id"], root=tmp_path)
    assert loaded["mission_description"] == mission["description"]

    listed = list_team_plans(root=tmp_path)
    assert listed
    assert listed[0]["mission_id"] == mission["id"]


def test_team_plan_includes_proposed_changes_for_structured_mission(tmp_path):
    project_root = tmp_path / "workspace" / "docsproj"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "README.md").write_text("before\n", encoding="utf-8")

    project = register_project("DocsProj", str(project_root), root=tmp_path)
    mission = create_mission(project["id"], "replace README.md :: after\n", root=tmp_path)
    plan = create_team_plan(mission["id"], root=tmp_path)

    assert plan["proposed_changes"]
    assert plan["proposed_changes"][0]["path"] == "README.md"
