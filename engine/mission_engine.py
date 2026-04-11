from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from engine.dreaming import recall, remember_text, run_dream_cycle
from engine.memory_store import initialize_memory_dirs, write_json, write_text
from engine.project_manager import get_project
from engine.proposal_engine import create_proposal
from engine.utils import ROOT, now_iso


MISSIONS_DIR = ROOT / "runtime" / "missions"
TASK_PLANS_DIR = ROOT / "runtime" / "task_plans"
EXECUTABLE_DIRECTIVE_RE = re.compile(
    r"^(?P<action>append|replace|create|delete)\s+(?P<path>\S+)(?:\s*::\s*(?P<content>[\s\S]*))?$",
    re.IGNORECASE,
)


def _mission_id() -> str:
    return f"task_{now_iso()[:10].replace('-', '')}_{uuid.uuid4().hex[:6]}"


def _project_local_root(project_path_or_repo: str, root: Path) -> Path | None:
    candidate = Path(project_path_or_repo)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    relative = (root / project_path_or_repo).resolve()
    if relative.exists():
        return relative
    return None


def _parse_execution_directive(description: str, project_path_or_repo: str, root: Path) -> dict | None:
    match = EXECUTABLE_DIRECTIVE_RE.match(description.strip())
    if not match:
        return None

    action = match.group("action").lower()
    relative_path = match.group("path").replace("\\", "/")
    content = match.group("content") or ""
    project_root = _project_local_root(project_path_or_repo, root=root)

    if action == "delete":
        file_change = {"path": relative_path, "mode": "delete", "content": ""}
        return {"action": action, "path": relative_path, "file_changes": [file_change], "project_root": str(project_root) if project_root else None}

    if not content.strip():
        return None

    file_change = {"path": relative_path, "mode": "replace", "content": content}
    if action == "create":
        file_change["mode"] = "create"
    elif action == "append":
        if not project_root:
            return None
        target = (project_root / relative_path).resolve()
        existing = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else ""
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        file_change["mode"] = "create" if not target.exists() else "replace"
        file_change["content"] = f"{existing}{separator}{content}"

    return {
        "action": action,
        "path": relative_path,
        "file_changes": [file_change],
        "project_root": str(project_root) if project_root else None,
    }


def _mission_risk(description: str, directive: dict | None) -> str:
    if directive:
        path = str(directive["path"]).lower()
        if path.endswith((".md", ".txt")):
            return "low"
    if any(keyword in description.lower() for keyword in ("engine/", "bot/", ".py", "refactor", "implement", "code")):
        return "medium"
    return "medium"


def create_mission(project_id: str, description: str, root: Path = ROOT) -> dict:
    if not description.strip():
        raise ValueError("Task description is required")
    initialize_memory_dirs(root)
    project = get_project(project_id, root=root)
    related_memory = recall(description.split()[0], root=root, limit=5) if description.split() else []
    execution_directive = _parse_execution_directive(description.strip(), project["path_or_repo"], root=root)
    mission = {
        "id": _mission_id(),
        "project_id": project["id"],
        "project_name": project["name"],
        "project_path_or_repo": project["path_or_repo"],
        "description": description.strip(),
        "status": "planned",
        "risk": _mission_risk(description.strip(), execution_directive),
        "created_at": now_iso(),
        "related_memory": related_memory,
        "execution_policy": "guarded_real_apply_after_approval" if execution_directive else "plan_only_until_approved",
        "execution_directive": execution_directive,
    }
    write_json(root / "runtime" / "missions" / f"{mission['id']}.json", mission)
    remember_text(f"Mission created for {project['name']}: {description}", topic=f"project:{project['id']}", root=root)
    write_text(root / "runtime" / "task_plans" / f"{mission['id']}.md", render_mission_plan(mission))
    run_dream_cycle(root=root, trigger=f"mission_created:{mission['id']}")
    return mission


def render_mission_plan(mission: dict) -> str:
    directive = mission.get("execution_directive")
    return "\n".join(
        [
            f"# Mission Plan: {mission['id']}",
            "",
            f"- Project: {mission['project_name']} (`{mission['project_id']}`)",
            f"- Target: {mission['project_path_or_repo']}",
            f"- Status: {mission['status']}",
            f"- Risk: {mission['risk']}",
            f"- Policy: {mission['execution_policy']}",
            "",
            "## Task",
            mission["description"],
            "",
            "## Safe next steps",
            "1. Inspect relevant project files or repo metadata.",
            "2. Produce a concrete implementation plan with test commands.",
            "3. Create a proposal if code changes are required.",
            "4. Require explicit approval before applying medium/high-risk changes.",
            "5. Run tests and update memory after completion.",
            "",
            "## Executable directive",
            (
                f"- Detected: {directive['action']} {directive['path']}"
                if directive
                else "- No executable directive detected. Use syntax like `append README.md :: new text` for real guarded apply proposals."
            ),
            *([f"- Project root: {directive['project_root']}"] if directive and directive.get("project_root") else []),
            *([f"- Prepared changes: {len(directive['file_changes'])}"] if directive else []),
            "",
            "## Related memory",
            *[f"- {item['title']} | {item['path']}" for item in mission.get("related_memory", [])],
            "",
        ]
    )


def list_missions(root: Path = ROOT, limit: int = 10) -> list[dict]:
    directory = root / "runtime" / "missions"
    directory.mkdir(parents=True, exist_ok=True)
    missions = []
    for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        missions.append(json.loads(path.read_text(encoding="utf-8")))
    return missions


def get_mission(mission_id: str, root: Path = ROOT) -> dict:
    path = root / "runtime" / "missions" / f"{mission_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Mission not found: {mission_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def update_mission_status(mission_id: str, status: str, root: Path = ROOT) -> dict:
    mission = get_mission(mission_id, root=root)
    mission["status"] = status
    mission["updated_at"] = now_iso()
    write_json(root / "runtime" / "missions" / f"{mission_id}.json", mission)
    return mission


def create_execution_proposal_from_mission(mission_id: str, root: Path = ROOT) -> dict:
    mission = get_mission(mission_id, root=root)
    plan_path = f"runtime/task_plans/{mission_id}.md"
    directive = mission.get("execution_directive")
    file_changes = (directive or {}).get("file_changes", [])
    real_apply = bool(file_changes)
    return create_proposal(
        title=f"Execute mission {mission_id} for {mission['project_name']}",
        component=f"project:{mission['project_id']}",
        problem=mission["description"],
        root_cause="User created a Telegram mission that needs an approval gate before execution.",
        solution=(
            f"Use the mission plan at {plan_path}; apply the explicit file changes in guarded mode after approval."
            if real_apply
            else f"Use the mission plan at {plan_path}; execution stays in safe-check mode until explicit file changes are prepared."
        ),
        expected_impact=(
            "Mission becomes executable through guarded real apply with backup, diff generation, tests, and rollback."
            if real_apply
            else "Mission becomes trackable through proposal approval, safe test execution, memory, and reporting."
        ),
        risk=mission.get("risk", "medium"),
        files_to_modify=[change["path"] for change in file_changes],
        tests_to_run=["tests"],
        rollback_plan=(
            "Restore backed-up files automatically if post-apply tests fail."
            if real_apply
            else "No source files are modified by safe execution; revert mission/proposal JSON if needed."
        ),
        metadata={
            "mission_id": mission_id,
            "plan_path": plan_path,
            "execution_mode": "guarded_real_apply" if real_apply else "safe_check_only",
            "file_changes": file_changes,
        },
        root=root,
    )
