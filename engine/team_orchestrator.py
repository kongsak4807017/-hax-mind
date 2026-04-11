from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.memory_intelligence import hybrid_recall
from engine.mission_engine import get_mission
from engine.memory_store import write_json, write_text
from engine.utils import ROOT, now_iso

TEAM_PLANS_DIR = ROOT / "runtime" / "team_plans"


def _team_plan_paths(root: Path, mission_id: str) -> tuple[Path, Path]:
    base = root / "runtime" / "team_plans"
    return base / f"{mission_id}.json", base / f"{mission_id}.md"


def _derive_lanes(mission: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "researcher",
            "objective": f"Collect the most relevant memory, repo context, and external constraints for: {mission['description']}",
            "deliverables": ["evidence summary", "relevant files/repos", "open risks"],
        },
        {
            "role": "architect",
            "objective": "Turn mission intent into a concrete implementation/test plan with minimal risk.",
            "deliverables": ["implementation outline", "test strategy", "rollback notes"],
        },
        {
            "role": "executor",
            "objective": "Implement the approved change set inside the guarded workflow.",
            "deliverables": ["code changes", "verification notes", "changed file list"],
        },
        {
            "role": "verifier",
            "objective": "Re-check the finished work against tests, safety rules, and mission intent.",
            "deliverables": ["test evidence", "remaining risks", "release recommendation"],
        },
    ]


def _render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# Team Plan: {plan['mission_id']}",
        "",
        f"- Project: {plan['project_name']} (`{plan['project_id']}`)",
        f"- Mission: {plan['mission_description']}",
        f"- Status: {plan['status']}",
        f"- Created: {plan['created_at']}",
        "",
        "## Team lanes",
    ]
    for lane in plan["lanes"]:
        lines.extend(
            [
                f"### {lane['role']}",
                f"- Objective: {lane['objective']}",
                *[f"- Deliverable: {item}" for item in lane["deliverables"]],
                "",
            ]
        )
    lines.append("## Related memory")
    if not plan["related_memory"]:
        lines.append("- No related memory found.")
    else:
        lines.extend(f"- {item['title']} | {item['path']}" for item in plan["related_memory"])
    lines.append("")
    lines.append("## Proposed changes")
    if not plan.get("proposed_changes"):
        lines.append("- No explicit executable file changes prepared yet.")
    else:
        lines.extend(f"- {change['mode']} {change['path']}" for change in plan["proposed_changes"])
    lines.append("")
    return "\n".join(lines)


def create_team_plan(mission_id: str, root: Path = ROOT) -> dict[str, Any]:
    mission = get_mission(mission_id, root=root)
    related_memory = hybrid_recall(mission["description"], root=root, limit=6)
    plan = {
        "mission_id": mission["id"],
        "project_id": mission["project_id"],
        "project_name": mission["project_name"],
        "mission_description": mission["description"],
        "status": "planned",
        "created_at": now_iso(),
        "lanes": _derive_lanes(mission),
        "proposed_changes": list((mission.get("execution_directive") or {}).get("file_changes", [])),
        "related_memory": [
            {
                "title": item["title"],
                "path": item["path"],
                "score": item["score"],
            }
            for item in related_memory
        ],
    }
    json_path, md_path = _team_plan_paths(root, mission_id)
    write_json(json_path, plan)
    write_text(md_path, _render_markdown(plan))
    return plan


def get_team_plan(mission_id: str, root: Path = ROOT) -> dict[str, Any]:
    json_path, _ = _team_plan_paths(root, mission_id)
    if not json_path.exists():
        raise FileNotFoundError(f"Team plan not found: {mission_id}")
    return json.loads(json_path.read_text(encoding="utf-8"))


def list_team_plans(root: Path = ROOT, limit: int = 10) -> list[dict[str, Any]]:
    directory = root / "runtime" / "team_plans"
    directory.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        items.append(json.loads(path.read_text(encoding="utf-8")))
    return items
