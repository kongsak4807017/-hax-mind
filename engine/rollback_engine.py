from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from engine.utils import ROOT

BACKUP_DIR = ROOT / "runtime" / "backups"


def _backup_root(proposal_id: str, root: Path = ROOT) -> Path:
    return root / "runtime" / "backups" / proposal_id


def _restore_legacy_backup(backup_root: Path, root: Path) -> dict:
    restored = 0
    for file in backup_root.rglob("*"):
        if file.is_file():
            rel = file.relative_to(backup_root)
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                os.remove(dst)
            shutil.copy2(file, dst)
            restored += 1
    return {"ok": True, "message": f"Restored {restored} files", "restored_files": restored, "deleted_files": 0}


def rollback_proposal(proposal_id: str, root: Path = ROOT) -> dict:
    backup_root = _backup_root(proposal_id, root=root)
    if not backup_root.exists():
        return {"ok": False, "message": "Backup not found", "restored_files": 0, "deleted_files": 0}

    manifest_path = backup_root / "manifest.json"
    if not manifest_path.exists():
        return _restore_legacy_backup(backup_root, root=root)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored = 0
    deleted = 0
    backup_files_root = backup_root / "files"
    for item in manifest.get("files", []):
        relative_path = item["path"]
        destination = (root / relative_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        if item.get("existed"):
            backup_relative = item.get("backup_path")
            if not backup_relative:
                continue
            backup_source = backup_root / backup_relative
            if destination.exists():
                os.remove(destination)
            shutil.copy2(backup_source, destination)
            restored += 1
        else:
            if destination.exists():
                if destination.is_file():
                    destination.unlink()
                deleted += 1

    return {
        "ok": True,
        "message": f"Rollback complete: restored {restored} files and removed {deleted} newly created files",
        "restored_files": restored,
        "deleted_files": deleted,
        "manifest_path": str(manifest_path.relative_to(root)),
        "backup_root": str(backup_files_root.relative_to(root)),
    }
