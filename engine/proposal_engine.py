from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from engine.memory_store import write_json
from engine.utils import ROOT, now_iso

PROPOSALS_DIR = ROOT / "runtime" / "proposals"


def _proposal_path(proposal_id: str, root: Path = ROOT) -> Path:
    return root / "runtime" / "proposals" / f"{proposal_id}.json"


def save_proposal(proposal: dict, root: Path = ROOT) -> dict:
    write_json(_proposal_path(proposal["id"], root=root), proposal)
    return proposal


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


def proposal_fingerprint(
    *,
    title: str,
    component: str,
    problem: str,
    root_cause: str,
    solution: str,
    expected_impact: str,
    risk: str,
    files_to_modify: list[str],
    tests_to_run: list[str],
    rollback_plan: str,
    metadata: dict | None,
) -> str:
    payload = {
        "title": title.strip(),
        "component": component.strip(),
        "problem": problem.strip(),
        "root_cause": root_cause.strip(),
        "solution": solution.strip(),
        "expected_impact": expected_impact.strip(),
        "risk": risk.strip(),
        "files_to_modify": list(files_to_modify),
        "tests_to_run": list(tests_to_run),
        "rollback_plan": rollback_plan.strip(),
        "metadata": _canonicalize(metadata or {}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_duplicate_pending_proposal(fingerprint: str, root: Path = ROOT) -> dict | None:
    for proposal in list_proposals(limit=500, root=root):
        if proposal.get("status") != "pending":
            continue
        if proposal.get("fingerprint") == fingerprint:
            return proposal
    return None


def create_proposal(
    title: str,
    component: str,
    problem: str,
    root_cause: str,
    solution: str,
    expected_impact: str,
    risk: str,
    files_to_modify: list[str],
    tests_to_run: list[str],
    rollback_plan: str,
    metadata: dict | None = None,
    root: Path = ROOT,
) -> dict:
    import uuid

    fingerprint = proposal_fingerprint(
        title=title,
        component=component,
        problem=problem,
        root_cause=root_cause,
        solution=solution,
        expected_impact=expected_impact,
        risk=risk,
        files_to_modify=files_to_modify,
        tests_to_run=tests_to_run,
        rollback_plan=rollback_plan,
        metadata=metadata,
    )
    duplicate = find_duplicate_pending_proposal(fingerprint, root=root)
    if duplicate:
        duplicate.setdefault("metadata", {})
        duplicate["metadata"]["dedupe_hits"] = int(duplicate["metadata"].get("dedupe_hits", 0)) + 1
        duplicate["metadata"]["last_dedupe_at"] = now_iso()
        save_proposal(duplicate, root=root)
        return duplicate

    proposal = {
        "id": f"prop_{now_iso()[:10].replace('-', '')}_{uuid.uuid4().hex[:8]}",
        "created_at": now_iso(),
        "title": title,
        "component": component,
        "problem": problem,
        "root_cause": root_cause,
        "solution": solution,
        "expected_impact": expected_impact,
        "risk": risk,
        "files_to_modify": files_to_modify,
        "tests_to_run": tests_to_run,
        "rollback_plan": rollback_plan,
        "status": "pending",
        "metadata": metadata or {},
        "fingerprint": fingerprint,
    }
    return save_proposal(proposal, root=root)


def get_proposal(proposal_id: str, root: Path = ROOT) -> dict:
    path = _proposal_path(proposal_id, root=root)
    if not path.exists():
        raise FileNotFoundError(proposal_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_proposals(limit: int = 20, root: Path = ROOT) -> list[dict]:
    proposal_dir = root / "runtime" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    proposals = []
    for path in sorted(proposal_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        proposals.append(json.loads(path.read_text(encoding="utf-8")))
    return proposals


def update_proposal_status(proposal_id: str, status: str, root: Path = ROOT) -> dict:
    proposal = get_proposal(proposal_id, root=root)
    proposal["status"] = status
    proposal["updated_at"] = now_iso()
    return save_proposal(proposal, root=root)


def archive_duplicate_pending_proposals(root: Path = ROOT) -> dict[str, Any]:
    pending = [proposal for proposal in list_proposals(limit=1000, root=root) if proposal.get("status") == "pending"]
    by_fingerprint: dict[str, list[dict]] = {}
    for proposal in pending:
        fingerprint = proposal.get("fingerprint")
        if not fingerprint:
            fingerprint = proposal_fingerprint(
                title=proposal["title"],
                component=proposal["component"],
                problem=proposal["problem"],
                root_cause=proposal["root_cause"],
                solution=proposal["solution"],
                expected_impact=proposal["expected_impact"],
                risk=proposal["risk"],
                files_to_modify=proposal.get("files_to_modify", []),
                tests_to_run=proposal.get("tests_to_run", []),
                rollback_plan=proposal.get("rollback_plan", ""),
                metadata=proposal.get("metadata", {}),
            )
            proposal["fingerprint"] = fingerprint
            save_proposal(proposal, root=root)
        by_fingerprint.setdefault(fingerprint, []).append(proposal)

    kept = []
    archived = []
    for proposals in by_fingerprint.values():
        proposals.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        canonical = proposals[0]
        kept.append(canonical["id"])
        for duplicate in proposals[1:]:
            duplicate["status"] = "archived_duplicate"
            duplicate["updated_at"] = now_iso()
            duplicate.setdefault("metadata", {})
            duplicate["metadata"]["archived_as_duplicate_of"] = canonical["id"]
            save_proposal(duplicate, root=root)
            archived.append(duplicate["id"])

    return {"kept": kept, "archived": archived, "archived_count": len(archived)}
