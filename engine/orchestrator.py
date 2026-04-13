from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from engine.apply_engine import execute_proposal_safe
from engine.cli_bridge import (
    close_cli_session,
    continue_cli_session,
    create_cli_improvement_proposal,
    get_cli_job,
    get_cli_session,
    latest_cli_job,
    latest_cli_session,
    open_cli_session,
    render_cli_job_detail,
    render_cli_jobs_summary,
    render_cli_session_detail,
    render_cli_sessions_summary,
    start_cli_session,
    render_cli_tools_summary,
    run_cli_once,
)
from engine.dream_tasks import create_task_from_dream
from engine.dreaming import explain_dream, latest_dream
from engine.local_health import render_local_health_summary
from engine.memory_analyzer import log_event
from engine.mission_engine import create_execution_proposal_from_mission, create_mission, get_mission, list_missions
from engine.morning_report import generate_morning_report
from engine.openrouter_client import OpenRouterError, chat_completion, extract_message_text
from engine.project_manager import list_projects, register_project
from engine.proposal_engine import get_proposal, list_proposals, update_proposal_status
from engine.repo_analyzer import analyze_github_repo_and_dream
from engine.research_engine import render_research_reply, run_research
from engine.rollback_engine import rollback_proposal
from engine.utils import ROOT


LLMCallable = Callable[[str, str], dict[str, Any]]


@dataclass(frozen=True)
class OrchestrationPlan:
    action: str
    reply: str
    project_id: str = ""
    project_name: str = ""
    path_or_repo: str = ""
    task_id: str = ""
    description: str = ""
    proposal_id: str = ""
    repo_target: str = ""
    dream_id: str = ""
    cli_tool: str = ""
    cli_job_id: str = ""


def _projects_summary(root: Path) -> list[dict[str, str]]:
    return [
        {"id": item["id"], "name": item["name"], "path_or_repo": item["path_or_repo"]}
        for item in list_projects(root=root)[:8]
    ]


def _tasks_summary(root: Path) -> list[dict[str, str]]:
    return [
        {
            "id": item["id"],
            "project_id": item["project_id"],
            "project_name": item["project_name"],
            "status": item["status"],
            "description": item["description"][:120],
        }
        for item in list_missions(root=root, limit=8)
    ]


def _proposals_summary(root: Path) -> list[dict[str, str]]:
    return [
        {
            "id": item["id"],
            "status": item["status"],
            "risk": item["risk"],
            "title": item["title"][:120],
        }
        for item in list_proposals(root=root, limit=8)
    ]


def _build_system_prompt(root: Path, conversation_history: list[dict[str, str]] | None = None) -> str:
    context = {
        "projects": _projects_summary(root),
        "tasks": _tasks_summary(root),
        "proposals": _proposals_summary(root),
    }
    history = conversation_history or []
    return (
        "You are the HAX-Mind orchestration router for Telegram.\n"
        "Map a user's natural-language request to one safe action using the existing HAX-Mind engine.\n"
        "Return valid JSON only with keys: "
        '{"action": string, "reply": string, "project_id": string, "project_name": string, '
        '"path_or_repo": string, "task_id": string, "description": string, "proposal_id": string, "repo_target": string, "dream_id": string, "cli_tool": string, "cli_job_id": string}.\n'
        "Allowed actions: reply, help, status, list_projects, create_project, list_tasks, task_status, "
        "create_task, create_proposal, list_proposals, approve_proposal, reject_proposal, execute_proposal, "
        "rollback_proposal, morning_report, analyze_repo, explain_dream, create_task_from_dream, research, "
        "list_cli_tools, list_cli_jobs, list_cli_sessions, cli_job_status, cli_session_status, start_cli_session, continue_cli_session, close_cli_session, open_cli_session, run_cli_once, cli_improve.\n"
        "Rules:\n"
        "- Use current ids from context when possible.\n"
        "- create_task requires project_id or a project_name that matches context.\n"
        "- create_proposal requires an existing task id.\n"
        "- execute_proposal must only be chosen when the user clearly asks to run/apply/execute a proposal.\n"
        "- approve_proposal and reject_proposal must only be chosen when the user explicitly says approve/reject.\n"
        "- If the request is ambiguous, unsafe, or missing an id, use reply and explain what is missing.\n"
        "- Use the recent conversation to resolve pronouns like 'that', 'it', 'the latest one', or 'same project'.\n"
        "- Keep reply concise and useful.\n"
        "- reply must be <= 160 characters.\n"
        "- Do not output markdown fences or explanations outside the JSON object.\n"
        f"Current context: {json.dumps(context, ensure_ascii=False)}\n"
        f"Recent conversation: {json.dumps(history, ensure_ascii=False)}"
    )


def _salvage_router_payload(content: str) -> dict[str, Any]:
    action_match = re.search(r'"action"\s*:\s*"([^"]+)"', content)
    action = action_match.group(1).strip() if action_match else "reply"

    def _field(name: str) -> str:
        match = re.search(rf'"{name}"\s*:\s*"([^"]*)"', content)
        return match.group(1).strip() if match else ""

    reply = _field("reply")
    if not reply:
        if action == "help":
            reply = "ผมช่วยดูสถานะ สร้าง task สร้าง proposal อนุมัติ/ปฏิเสธ proposal รัน proposal ที่อนุมัติแล้ว และ analyze repo ได้"
        else:
            reply = "ผมตีความคำขอนี้ได้ไม่สมบูรณ์ ลองระบุ id หรือคำสั่งให้ชัดขึ้นอีกนิด"

    return {
        "action": action,
        "reply": reply[:160],
        "project_id": _field("project_id"),
        "project_name": _field("project_name"),
        "path_or_repo": _field("path_or_repo"),
        "task_id": _field("task_id"),
        "description": _field("description"),
        "proposal_id": _field("proposal_id"),
        "repo_target": _field("repo_target"),
        "dream_id": _field("dream_id"),
        "cli_tool": _field("cli_tool"),
        "cli_job_id": _field("cli_job_id"),
    }


def _detect_cli_intent(user_message: str) -> dict[str, Any] | None:
    text = " ".join(user_message.strip().split())
    if not text:
        return None
    lowered = text.lower()
    tool = next((name for name in ("codex", "omx", "gemini", "kimi") if re.search(rf"\b{name}\b", lowered)), None)
    if any(token in lowered for token in ["sessions", "session list", "\u0e23\u0e32\u0e22\u0e01\u0e32\u0e23 session"]):
        return {"action": "list_cli_sessions", "reply": "Showing CLI sessions."}
    if any(token in lowered for token in ["latest cli", "proof", "\u0e2b\u0e25\u0e31\u0e01\u0e10\u0e32\u0e19", "job \u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14"]):
        return {"action": "cli_job_status", "reply": "Showing the latest CLI proof."}
    if any(token in lowered for token in ["ค้นหา", "หาข้อมูล", "วิจัย", "research", "search web", "ข่าวล่าสุด", "latest news", "ค้นเว็บ"]):
        return {
            "action": "research",
            "reply": "Searching external sources now.",
            "description": text,
        }
    if tool is None:
        return None
    if any(token in lowered for token in ["continue", "\u0e2a\u0e48\u0e07\u0e15\u0e48\u0e2d", "step \u0e15\u0e48\u0e2d", "\u0e15\u0e48\u0e2d\u0e40\u0e25\u0e22"]) and tool in {"kimi", "gemini", "codex"}:
        return {
            "action": "continue_cli_session",
            "reply": f"Continuing the latest {tool} session.",
            "cli_tool": tool,
            "description": text,
        }
    if any(token in lowered for token in ["\u0e1b\u0e34\u0e14 session", "close session", f"close {tool}", "\u0e08\u0e1a session"]) and tool in {"kimi", "gemini", "codex"}:
        return {
            "action": "close_cli_session",
            "reply": f"Closing the latest {tool} session.",
            "cli_tool": tool,
        }
    if any(token in lowered for token in ["\u0e40\u0e1b\u0e34\u0e14", "open", "launch"]) and tool in {"kimi", "gemini", "codex"}:
        return {
            "action": "start_cli_session",
            "reply": f"Starting a {tool} session in the workspace now.",
            "cli_tool": tool,
            "description": text,
        }
    if any(token in lowered for token in ["\u0e40\u0e1b\u0e34\u0e14", "open", "launch"]):
        return {
            "action": "open_cli_session",
            "reply": f"Opening {tool} CLI in the workspace now.",
            "cli_tool": tool,
            "description": text,
        }
    if any(token in lowered for token in ["\u0e23\u0e31\u0e19", "run", "summarize", "\u0e2a\u0e23\u0e38\u0e1b", "\u0e2d\u0e18\u0e34\u0e1a\u0e32\u0e22", "explain"]) and tool not in {"kimi", "gemini", "codex"}:
        return {
            "action": "run_cli_once",
            "reply": f"Running {tool} once in the workspace now.",
            "cli_tool": tool,
            "description": text,
        }
    return None



def _call_openrouter_for_plan(system_prompt: str, user_message: str) -> dict[str, Any]:
    shortcut = _detect_cli_intent(user_message)
    if shortcut is not None:
        return shortcut
    payload = chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        max_tokens=280,
        temperature=0.1,
    )
    content = extract_message_text(payload)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return _salvage_router_payload(content)


def _normalize_plan(payload: dict[str, Any]) -> OrchestrationPlan:
    def _text(key: str) -> str:
        value = payload.get(key, "")
        return value.strip() if isinstance(value, str) else ""

    return OrchestrationPlan(
        action=_text("action") or "reply",
        reply=_text("reply"),
        project_id=_text("project_id"),
        project_name=_text("project_name"),
        path_or_repo=_text("path_or_repo"),
        task_id=_text("task_id"),
        description=_text("description"),
        proposal_id=_text("proposal_id"),
        repo_target=_text("repo_target"),
        dream_id=_text("dream_id"),
        cli_tool=_text("cli_tool"),
        cli_job_id=_text("cli_job_id"),
    )


def _resolve_project_id(project_id: str, project_name: str, root: Path) -> str | None:
    projects = list_projects(root=root)
    if project_id:
        for project in projects:
            if project["id"] == project_id:
                return project["id"]
    if project_name:
        wanted = project_name.strip().lower()
        for project in projects:
            if project["name"].strip().lower() == wanted or project["id"] == wanted:
                return project["id"]
        for project in projects:
            if wanted in project["name"].strip().lower():
                return project["id"]
    if len(projects) == 1:
        return projects[0]["id"]
    return None


def _format_projects(root: Path) -> str:
    projects = list_projects(root=root)
    if not projects:
        return "No projects registered yet. Say: add a project named <name> pointing to <path_or_repo>."
    return "\n".join(f"{p['id']} | {p['name']} | {p['path_or_repo']}" for p in projects[:10])


def _format_tasks(root: Path) -> str:
    missions = list_missions(root=root, limit=10)
    if not missions:
        return "No tasks yet."
    return "\n".join(f"{m['id']} | {m['project_name']} | {m['status']} | {m['description'][:80]}" for m in missions)


def _format_proposals(root: Path) -> str:
    proposals = list_proposals(root=root, limit=10)
    if not proposals:
        return "No proposals."
    return "\n".join(f"{p['id']} | {p['status']} | {p['risk']} | {p['title']}" for p in proposals)


def execute_orchestration_plan(plan: OrchestrationPlan, *, root: Path = ROOT) -> str:
    action = plan.action.lower()
    if action in {"reply", "help"}:
        return plan.reply or (
            "I can create tasks, generate proposals, approve/reject proposals, execute approved proposals, show status, and analyze repos."
        )
    if action == "status":
        return render_local_health_summary()
    if action == "research":
        query = plan.description or plan.reply
        if not query:
            return "Please tell me what topic you want researched."
        record = run_research(query, root=root)
        return render_research_reply(record)
    if action == "list_cli_tools":
        return render_cli_tools_summary()
    if action == "list_cli_jobs":
        return render_cli_jobs_summary(root=root)
    if action == "list_cli_sessions":
        return render_cli_sessions_summary(root=root)
    if action == "cli_job_status":
        if plan.cli_job_id or plan.task_id:
            job = get_cli_job(plan.cli_job_id or plan.task_id, root=root)
        else:
            job = latest_cli_job(root=root)
            if not job:
                return plan.reply or "No CLI jobs yet."
        return render_cli_job_detail(job)
    if action == "cli_session_status":
        ref = plan.cli_job_id or plan.task_id or "latest"
        session = latest_cli_session(root=root) if ref == "latest" else get_cli_session(ref, root=root)
        if not session:
            return plan.reply or "No CLI session yet."
        return render_cli_session_detail(session)
    if action == "explain_dream":
        from engine.dreaming import get_dream

        dream = get_dream(plan.dream_id, root=root) if plan.dream_id else latest_dream(root=root)
        return explain_dream(dream, root=root)
    if action == "list_projects":
        return _format_projects(root)
    if action == "create_project":
        if not plan.project_name or not plan.path_or_repo:
            return plan.reply or "Please tell me both the project name and the local path or GitHub repo."
        project = register_project(plan.project_name, plan.path_or_repo, root=root)
        return f"Project registered: {project['id']} -> {project['path_or_repo']}"
    if action == "list_tasks":
        return _format_tasks(root)
    if action == "task_status":
        if not plan.task_id:
            return plan.reply or "Please specify which task you want to inspect."
        mission = get_mission(plan.task_id, root=root)
        return "\n".join(
            [
                f"Task: {mission['id']}",
                f"Project: {mission['project_name']}",
                f"Status: {mission['status']}",
                f"Risk: {mission['risk']}",
                f"Description: {mission['description'][:500]}",
            ]
        )
    if action == "create_task":
        project_id = _resolve_project_id(plan.project_id, plan.project_name, root)
        if not project_id:
            return plan.reply or "I couldn't determine the project. Please mention the project id or name."
        if not plan.description:
            return plan.reply or "Please tell me what task you want HAX-Mind to create."
        mission = create_mission(project_id, plan.description, root=root)
        return "\n".join(
            [
                f"Task created: {mission['id']}",
                f"Project: {mission['project_name']}",
                f"Status: {mission['status']}",
                f"Risk: {mission['risk']}",
            ]
        )
    if action == "start_cli_session":
        tool_key = (plan.cli_tool or plan.project_name or plan.project_id or "").lower()
        if not tool_key:
            return plan.reply or "Please specify which CLI tool to start."
        if not plan.description:
            return plan.reply or "Please tell me what first prompt should be sent."
        session, job = start_cli_session(tool_key, plan.description, root=root)
        return "\n".join(
            [
                f"Started CLI session: {session['id']}",
                f"Tool: {session['tool']}",
                f"First job: {job['id']}",
            ]
        )
    if action == "continue_cli_session":
        ref = plan.cli_job_id or plan.task_id or "latest"
        if not plan.description:
            return plan.reply or "Please tell me what next prompt should be sent."
        job = continue_cli_session(ref, plan.description, root=root)
        return render_cli_job_detail(job)
    if action == "close_cli_session":
        ref = plan.cli_job_id or plan.task_id or "latest"
        session = close_cli_session(ref, root=root)
        return "\n".join(
            [
                f"Closed CLI session: {session['id']}",
                f"Tool: {session['tool']}",
                f"Steps: {session.get('step_count', 0)}",
            ]
        )
    if action == "open_cli_session":
        tool_key = (plan.cli_tool or plan.project_name or plan.project_id or "").lower()
        if not tool_key:
            return plan.reply or "Please specify which CLI tool to open (codex, omx, gemini, kimi)."
        if not plan.description:
            return plan.reply or "Please tell me what prompt should be sent to the CLI."
        job = open_cli_session(tool_key, plan.description, root=root)
        return f"Opened {job['tool']} interactive CLI.\nJob: {job['id']}"
    if action == "run_cli_once":
        tool_key = (plan.cli_tool or plan.project_name or plan.project_id or "").lower()
        if not tool_key:
            return plan.reply or "Please specify which CLI tool to run (codex, omx, gemini, kimi)."
        if not plan.description:
            return plan.reply or "Please tell me what prompt should be run through the CLI."
        job = run_cli_once(tool_key, plan.description, root=root)
        lines = [
            f"CLI job completed: {job['id']}",
            f"Tool: {job['tool']}",
            f"Status: {job['status']}",
        ]
        if job.get("output_path"):
            lines.append(f"Output: {job['output_path']}")
        if job.get("stdout_excerpt"):
            lines.append(job["stdout_excerpt"])
        return "\n".join(lines)
    if action == "cli_improve":
        proposal = create_cli_improvement_proposal(root=root)
        return "\n".join(
            [
                f"CLI improvement proposal created: {proposal['id']}",
                f"Risk: {proposal['risk']}",
                f"Title: {proposal['title']}",
            ]
        )
    if action == "create_task_from_dream":
        project_id = _resolve_project_id(plan.project_id, plan.project_name, root)
        mission = create_task_from_dream(project_id=project_id, dream_id=plan.dream_id or None, root=root)
        return "\n".join(
            [
                f"Task created from dream: {mission['id']}",
                f"Project: {mission['project_name']}",
                f"Source dream: {mission.get('source_dream_id', 'latest')}",
                f"Status: {mission['status']}",
            ]
        )
    if action == "create_proposal":
        if not plan.task_id:
            return plan.reply or "Please tell me which task id should become a proposal."
        proposal = create_execution_proposal_from_mission(plan.task_id, root=root)
        return "\n".join(
            [
                f"Proposal created: {proposal['id']}",
                f"Title: {proposal['title']}",
                f"Risk: {proposal['risk']}",
                f"Status: {proposal['status']}",
            ]
        )
    if action == "list_proposals":
        return _format_proposals(root)
    if action == "approve_proposal":
        if not plan.proposal_id:
            return plan.reply or "Please specify the proposal id to approve."
        proposal = update_proposal_status(plan.proposal_id, "approved", root=root)
        return f"Approved: {proposal['id']}"
    if action == "reject_proposal":
        if not plan.proposal_id:
            return plan.reply or "Please specify the proposal id to reject."
        proposal = update_proposal_status(plan.proposal_id, "rejected", root=root)
        return f"Rejected: {proposal['id']}"
    if action == "execute_proposal":
        if not plan.proposal_id:
            return plan.reply or "Please specify the proposal id to execute."
        proposal = get_proposal(plan.proposal_id, root=root)
        if proposal.get("status") != "approved":
            return f"Proposal {proposal['id']} is `{proposal.get('status')}`. Approve it first before execution."
        result = execute_proposal_safe(plan.proposal_id, root=root)
        lines = [
            f"Executed proposal: {result['proposal_id']}",
            f"Status: {result['status']}",
            f"All tests passed: {result['all_passed']}",
        ]
        if result.get("patch_artifact"):
            lines.append(f"Patch: {result['patch_artifact']}")
        return "\n".join(lines)
    if action == "rollback_proposal":
        if not plan.proposal_id:
            return plan.reply or "Please specify the proposal id to roll back."
        result = rollback_proposal(plan.proposal_id, root=root)
        return result["message"]
    if action == "morning_report":
        return generate_morning_report(root=root)
    if action == "analyze_repo":
        if not plan.repo_target:
            return plan.reply or "Please provide a GitHub URL or owner/repo to analyze."
        record, dream_result = analyze_github_repo_and_dream(plan.repo_target, root=root)
        return "\n".join(
            [
                f"Analyzed: {record['repo']}",
                f"Files: {record['file_count']}",
                f"Stack: {', '.join(record['inferred_stack']) or 'unknown'}",
                f"Dream: {dream_result['id']}",
            ]
        )
    # Unknown action - HAX-Mind doesn't understand this request
    # This will trigger auto-learning to capture the knowledge gap
    return plan.reply or "I couldn't map that request to a safe HAX-Mind action. Please use /help to see available commands, or the system will learn from this gap."


def route_message_to_plan(
    text: str,
    *,
    root: Path = ROOT,
    llm_callable: LLMCallable | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> OrchestrationPlan:
    router = llm_callable or _call_openrouter_for_plan
    return _normalize_plan(router(_build_system_prompt(root, conversation_history=conversation_history), text))


def orchestrate_message(
    text: str,
    *,
    root: Path = ROOT,
    llm_callable: LLMCallable | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    plan = route_message_to_plan(text, root=root, llm_callable=llm_callable, conversation_history=conversation_history)
    log_event("command", f"orchestrator:{plan.action} :: {text[:240]}", topic="orchestrator", importance="high")
    return execute_orchestration_plan(plan, root=root)


def looks_like_plain_text_request(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped.startswith("/"):
        return False
    return bool(re.search(r"\w", stripped, re.UNICODE))
