from __future__ import annotations

import json
import re
from pathlib import Path

from engine.memory_store import initialize_memory_dirs, write_json
from engine.utils import ROOT, now_iso


PROJECTS_DIR = ROOT / "workspace" / "projects"


def _safe_project_id(value: str) -> str:
    value = value.strip().lower()
    return re.sub(r"[^a-z0-9_]+", "_", value).strip("_")[:60] or "project"


def register_project(name: str, path_or_repo: str, root: Path = ROOT) -> dict:
    initialize_memory_dirs(root)
    project_id = _safe_project_id(name)
    project = {
        "id": project_id,
        "name": name.strip(),
        "path_or_repo": path_or_repo.strip(),
        "created_at": now_iso(),
        "status": "active",
    }
    write_json(root / "workspace" / "projects" / f"{project_id}.json", project)
    return project


def list_projects(root: Path = ROOT) -> list[dict]:
    directory = root / "workspace" / "projects"
    directory.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        projects.append(json.loads(path.read_text(encoding="utf-8")))
    return projects


def get_project(project_id: str, root: Path = ROOT) -> dict:
    normalized = _safe_project_id(project_id)
    path = root / "workspace" / "projects" / f"{normalized}.json"
    if not path.exists():
        raise FileNotFoundError(f"Project not found: {project_id}")
    return json.loads(path.read_text(encoding="utf-8"))
