from __future__ import annotations

from pathlib import Path

from engine.dreaming import get_dream, latest_dream
from engine.mission_engine import create_mission
from engine.project_manager import get_project, list_projects
from engine.utils import ROOT


def _resolve_project_id(project_id: str | None, *, root: Path) -> str:
    if project_id:
        return get_project(project_id, root=root)["id"]
    projects = list_projects(root=root)
    if len(projects) == 1:
        return projects[0]["id"]
    if not projects:
        raise FileNotFoundError("No projects registered. Register a project first.")
    raise ValueError("Multiple projects exist. Please specify which project should receive the dream task.")


def _dream_task_description(dream: dict) -> str:
    trigger = dream.get("trigger", "unknown")
    patterns = ", ".join((dream.get("rem", {}) or {}).get("patterns", [])[:6]) or "none"
    next_actions = (dream.get("rem", {}) or {}).get("next_actions", [])[:3]
    actions_block = "\n".join(f"- {action}" for action in next_actions) if next_actions else "- Review the latest dream and convert it into a concrete implementation step."
    return (
        f"Dream follow-up from {dream['id']} (trigger: {trigger}).\n"
        f"Observed patterns: {patterns}\n"
        "Convert the dream recommendations into an executable plan:\n"
        f"{actions_block}"
    )


def create_task_from_dream(*, project_id: str | None = None, dream_id: str | None = None, root: Path = ROOT) -> dict:
    resolved_project_id = _resolve_project_id(project_id, root=root)
    dream = get_dream(dream_id, root=root) if dream_id else latest_dream(root=root)
    if not dream:
        raise FileNotFoundError("No dream exists yet. Run /dream now or analyze a repo first.")
    mission = create_mission(resolved_project_id, _dream_task_description(dream), root=root)
    mission["source_dream_id"] = dream["id"]
    return mission
