from pathlib import Path

from engine.dreaming import run_dream_cycle
from engine.mission_engine import create_mission
from engine.orchestrator import (
    OrchestrationPlan,
    _call_openrouter_for_plan,
    execute_orchestration_plan,
    looks_like_plain_text_request,
    orchestrate_message,
    route_message_to_plan,
)
from engine.project_manager import register_project
from engine.proposal_engine import get_proposal


def test_plain_text_detection() -> None:
    assert looks_like_plain_text_request("create a task for haxmind") is True
    assert looks_like_plain_text_request("/start") is False
    assert looks_like_plain_text_request("   ") is False


def test_execute_orchestration_plan_create_task(tmp_path: Path) -> None:
    register_project("HAXMind", str(tmp_path), root=tmp_path)

    plan = OrchestrationPlan(
        action="create_task",
        reply="",
        project_name="HAXMind",
        description="append README.md :: hello world",
    )

    message = execute_orchestration_plan(plan, root=tmp_path)

    assert "Task created:" in message
    missions = list((tmp_path / "runtime" / "missions").glob("*.json"))
    assert len(missions) == 1


def test_execute_orchestration_plan_create_and_approve_proposal(tmp_path: Path) -> None:
    register_project("HAXMind", str(tmp_path), root=tmp_path)
    mission = create_mission("haxmind", "append README.md :: hello world", root=tmp_path)

    message = execute_orchestration_plan(
        OrchestrationPlan(action="create_proposal", reply="", task_id=mission["id"]),
        root=tmp_path,
    )

    assert "Proposal created:" in message
    proposal_id = message.splitlines()[0].split(": ", 1)[1]
    approved = execute_orchestration_plan(
        OrchestrationPlan(action="approve_proposal", reply="", proposal_id=proposal_id),
        root=tmp_path,
    )
    assert approved == f"Approved: {proposal_id}"
    assert get_proposal(proposal_id, root=tmp_path)["status"] == "approved"


def test_orchestrate_message_uses_llm_plan(tmp_path: Path, monkeypatch) -> None:
    register_project("HAXMind", str(tmp_path), root=tmp_path)
    monkeypatch.setattr("engine.orchestrator.log_event", lambda *args, **kwargs: None)

    def fake_llm(system_prompt: str, user_message: str) -> dict:
        assert "Current context" in system_prompt
        assert user_message == "create a task to append README.md"
        return {
            "action": "create_task",
            "reply": "Creating the task now.",
            "project_name": "HAXMind",
            "description": "append README.md :: hello from llm",
        }

    result = orchestrate_message("create a task to append README.md", root=tmp_path, llm_callable=fake_llm)

    assert "Task created:" in result


def test_route_message_to_plan_passes_recent_conversation(tmp_path: Path) -> None:
    register_project("HAXMind", str(tmp_path), root=tmp_path)
    captured = {}

    def fake_llm(system_prompt: str, user_message: str) -> dict:
        captured["system_prompt"] = system_prompt
        captured["user_message"] = user_message
        return {"action": "help", "reply": "ok"}

    plan = route_message_to_plan(
        "do the same thing again",
        root=tmp_path,
        llm_callable=fake_llm,
        conversation_history=[{"role": "user", "content": "create a task for haxmind"}],
    )

    assert plan.action == "help"
    assert "Recent conversation" in captured["system_prompt"]
    assert "create a task for haxmind" in captured["system_prompt"]


def test_execute_orchestration_plan_can_explain_and_convert_dream(tmp_path: Path) -> None:
    register_project("HAXMind", str(tmp_path), root=tmp_path)
    dream = run_dream_cycle(root=tmp_path, trigger="test-orchestrator-dream")

    explanation = execute_orchestration_plan(OrchestrationPlan(action="explain_dream", reply=""), root=tmp_path)
    created = execute_orchestration_plan(
        OrchestrationPlan(action="create_task_from_dream", reply="", project_name="HAXMind", dream_id=dream["id"]),
        root=tmp_path,
    )

    assert "generated memory-reflection note" in explanation
    assert "Task created from dream:" in created


def test_router_salvages_truncated_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.orchestrator.chat_completion",
        lambda **kwargs: {
            "choices": [
                {
                    "message": {
                        "content": '{"action":"help","reply":"ฉันช่วยดูสถานะ สร้าง task และ proposal ได้'
                    }
                }
            ]
        },
    )

    payload = _call_openrouter_for_plan("system", "user")

    assert payload["action"] == "help"
    assert payload["reply"]


def test_route_message_to_plan_shortcuts_cli_open(tmp_path: Path) -> None:
    register_project("HAXMind", str(tmp_path), root=tmp_path)

    plan = route_message_to_plan("เปิด kimi cli ใน workspace แล้วอธิบายงาน hax-mind", root=tmp_path)

    assert plan.action == "start_cli_session"
    assert plan.cli_tool == "kimi"


def test_route_message_to_plan_shortcuts_kimi_continue(tmp_path: Path) -> None:
    register_project("HAXMind", str(tmp_path), root=tmp_path)

    plan = route_message_to_plan("ต่อเลย kimi ช่วยแตก step ถัดไป", root=tmp_path)

    assert plan.action == "continue_cli_session"
    assert plan.cli_tool == "kimi"
