from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import yaml

from engine.memory_store import write_json
from engine.proposal_engine import get_proposal, save_proposal, update_proposal_status
from engine.rollback_engine import rollback_proposal
from engine.test_runner import run_tests
from engine.utils import ROOT, ensure_dir, now_iso

PATCHES_DIRNAME = "patches"
APPLIED_DIRNAME = "applied"
FAILED_DIRNAME = "failed"
BACKUPS_DIRNAME = "backups"


def _runtime_path(root: Path, name: str) -> Path:
    return root / "runtime" / name


def _load_risk_policy(root: Path = ROOT) -> dict[str, Any]:
    path = root / "policies" / "risk_policy.yaml"
    if not path.exists():
        path = ROOT / "policies" / "risk_policy.yaml"
    if not path.exists():
        return {"risk_levels": {}, "protected_paths": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"risk_levels": {}, "protected_paths": []}


def _normalize_rel_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    if not cleaned:
        raise ValueError("Empty file path is not allowed")
    if any(token in cleaned for token in ("*", "?", "[", "]")):
        raise ValueError(f"Glob patterns are not allowed in executable file paths: {path}")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _resolve_repo_path(root: Path, relative_path: str) -> Path:
    relative = _normalize_rel_path(relative_path)
    resolved = (root / relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in resolved.parents and resolved != root_resolved:
        raise PermissionError(f"Path escapes repository root: {relative_path}")
    return resolved


def _is_protected_path(relative_path: str, root: Path = ROOT) -> bool:
    relative = _normalize_rel_path(relative_path)
    policy = _load_risk_policy(root)
    normalized = relative.lower().rstrip("/")
    for protected in policy.get("protected_paths", []):
        candidate = str(protected).replace("\\", "/").lower().rstrip("/")
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


def _proposal_change_set(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return list(proposal.get("metadata", {}).get("file_changes") or [])


def _prepare_change(change: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    if "path" not in change:
        raise ValueError("Each file change must include a path")
    relative_path = _normalize_rel_path(str(change["path"]))
    if _is_protected_path(relative_path, root=root):
        raise PermissionError(f"Protected path cannot be modified: {relative_path}")

    mode = str(change.get("mode") or "replace").lower()
    if mode not in {"replace", "create", "delete"}:
        raise ValueError(f"Unsupported file change mode: {mode}")

    content = change.get("content")
    if mode != "delete" and not isinstance(content, str):
        raise ValueError(f"File change content must be a string for mode '{mode}'")

    absolute_path = _resolve_repo_path(root, relative_path)
    return {
        "path": relative_path,
        "absolute_path": absolute_path,
        "mode": mode,
        "content": content if isinstance(content, str) else "",
    }


def _ensure_runtime_dirs(root: Path = ROOT) -> None:
    ensure_dir(_runtime_path(root, PATCHES_DIRNAME))
    ensure_dir(_runtime_path(root, APPLIED_DIRNAME))
    ensure_dir(_runtime_path(root, FAILED_DIRNAME))
    ensure_dir(_runtime_path(root, BACKUPS_DIRNAME))


def _backup_changes(proposal_id: str, changes: list[dict[str, Any]], root: Path = ROOT) -> dict[str, Any]:
    _ensure_runtime_dirs(root)
    backup_root = _runtime_path(root, BACKUPS_DIRNAME) / proposal_id
    backup_files_root = backup_root / "files"
    ensure_dir(backup_files_root)

    manifest_entries = []
    for change in changes:
        target = change["absolute_path"]
        existed = target.exists()
        manifest_entry = {
            "path": change["path"],
            "mode": change["mode"],
            "existed": existed,
            "backup_path": None,
        }
        if existed:
            backup_path = backup_files_root / change["path"]
            ensure_dir(backup_path.parent)
            backup_path.write_bytes(target.read_bytes())
            manifest_entry["backup_path"] = str(backup_path.relative_to(backup_root))
        manifest_entries.append(manifest_entry)

    manifest = {
        "proposal_id": proposal_id,
        "created_at": now_iso(),
        "files": manifest_entries,
    }
    write_json(backup_root / "manifest.json", manifest)
    return {"backup_root": backup_root, "manifest": manifest}


def _generate_patch_artifact(proposal_id: str, changes: list[dict[str, Any]], root: Path = ROOT) -> Path:
    _ensure_runtime_dirs(root)
    lines: list[str] = []
    for change in changes:
        target = change["absolute_path"]
        before = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else ""
        after = "" if change["mode"] == "delete" else change["content"]
        diff = list(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{change['path']}",
                tofile=f"b/{change['path']}",
            )
        )
        if not diff:
            continue
        lines.extend(diff)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
    patch_path = _runtime_path(root, PATCHES_DIRNAME) / f"{proposal_id}.diff"
    patch_path.write_text("".join(lines), encoding="utf-8")
    return patch_path


def _apply_changes(changes: list[dict[str, Any]]) -> list[str]:
    applied_paths: list[str] = []
    for change in changes:
        target = change["absolute_path"]
        ensure_dir(target.parent)
        if change["mode"] == "delete":
            if target.exists():
                target.unlink()
        else:
            target.write_text(change["content"], encoding="utf-8")
        applied_paths.append(change["path"])
    return applied_paths


def apply_proposal_placeholder(proposal_id: str, root: Path = ROOT) -> dict:
    """Safe placeholder: records intent but does not patch source files yet."""
    proposal = update_proposal_status(proposal_id, "applied_placeholder", root=root)
    return {
        "applied": False,
        "proposal_id": proposal_id,
        "message": "Placeholder only: no source files were modified.",
        "proposal": proposal,
    }


def _run_required_tests(proposal: dict[str, Any]) -> dict[str, Any]:
    test_targets = proposal.get("tests_to_run") or ["tests"]
    return run_tests(test_targets)


def _safe_report(proposal_id: str, proposal: dict[str, Any], result: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    new_status = "executed_safe" if result["all_passed"] else "failed_safe"
    proposal["status"] = new_status
    proposal["executed_at"] = now_iso()
    proposal["execution_result"] = result
    proposal["execution_mode"] = "safe_check_only_no_source_modifications"
    save_proposal(proposal, root=root)

    report = {
        "proposal_id": proposal_id,
        "status": new_status,
        "executed_at": proposal["executed_at"],
        "all_passed": result["all_passed"],
        "mode": proposal["execution_mode"],
    }
    write_json(_runtime_path(root, APPLIED_DIRNAME if result["all_passed"] else FAILED_DIRNAME) / f"{proposal_id}.json", report)
    return report


def execute_proposal_safe(proposal_id: str, root: Path = ROOT) -> dict:
    """Execute approved proposals. Uses real guarded apply if a file change set exists; otherwise falls back to safe verification."""
    _ensure_runtime_dirs(root)
    proposal = get_proposal(proposal_id, root=root)
    if proposal.get("status") != "approved":
        raise PermissionError("Proposal must be approved before execution")

    changes = [_prepare_change(change, root=root) for change in _proposal_change_set(proposal)]
    if not changes:
        return _safe_report(proposal_id, proposal, _run_required_tests(proposal), root=root)

    risk_policy = _load_risk_policy(root)
    risk_rules = (risk_policy.get("risk_levels") or {}).get(proposal.get("risk", "medium"), {})
    if risk_rules.get("require_backup", True) is False:
        raise PermissionError("Execution requires backup support; policy disabled it unexpectedly")

    backup_info = _backup_changes(proposal_id, changes, root=root)
    patch_path = _generate_patch_artifact(proposal_id, changes, root=root)

    proposal["execution_mode"] = "guarded_real_apply"
    proposal["patch_artifact"] = str(patch_path.relative_to(root))
    proposal["backup_root"] = str(backup_info["backup_root"].relative_to(root))
    proposal["applied_files"] = [change["path"] for change in changes]
    proposal["apply_started_at"] = now_iso()
    save_proposal(proposal, root=root)

    try:
        _apply_changes(changes)
        result = _run_required_tests(proposal)
        proposal["execution_result"] = result
        proposal["executed_at"] = now_iso()
        proposal["all_passed"] = result["all_passed"]

        if not result["all_passed"]:
            rollback_result = rollback_proposal(proposal_id, root=root)
            proposal["rollback_result"] = rollback_result
            proposal["status"] = "rolled_back_failed_tests" if rollback_result.get("ok") else "failed_apply"
            save_proposal(proposal, root=root)
            report = {
                "proposal_id": proposal_id,
                "status": proposal["status"],
                "executed_at": proposal["executed_at"],
                "all_passed": False,
                "mode": proposal["execution_mode"],
                "rolled_back": rollback_result.get("ok", False),
                "patch_artifact": proposal["patch_artifact"],
                "applied_files": proposal["applied_files"],
            }
            write_json(_runtime_path(root, FAILED_DIRNAME) / f"{proposal_id}.json", report)
            return report

        proposal["status"] = "applied"
        proposal["applied_at"] = now_iso()
        save_proposal(proposal, root=root)
        report = {
            "proposal_id": proposal_id,
            "status": "applied",
            "executed_at": proposal["executed_at"],
            "all_passed": True,
            "mode": proposal["execution_mode"],
            "rolled_back": False,
            "patch_artifact": proposal["patch_artifact"],
            "applied_files": proposal["applied_files"],
        }
        write_json(_runtime_path(root, APPLIED_DIRNAME) / f"{proposal_id}.json", report)
        return report
    except Exception as exc:
        rollback_result = rollback_proposal(proposal_id, root=root)
        proposal["status"] = "rolled_back_apply_error" if rollback_result.get("ok") else "failed_apply"
        proposal["executed_at"] = now_iso()
        proposal["execution_error"] = str(exc)
        proposal["rollback_result"] = rollback_result
        save_proposal(proposal, root=root)
        report = {
            "proposal_id": proposal_id,
            "status": proposal["status"],
            "executed_at": proposal["executed_at"],
            "all_passed": False,
            "mode": proposal["execution_mode"],
            "rolled_back": rollback_result.get("ok", False),
            "error": str(exc),
            "patch_artifact": proposal.get("patch_artifact"),
            "applied_files": proposal.get("applied_files", []),
        }
        write_json(_runtime_path(root, FAILED_DIRNAME) / f"{proposal_id}.json", report)
        return report
