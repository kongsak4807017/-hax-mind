"""
Rollback Policy Verification for PicoClaw Phase 2
Ensures rollback mechanisms are working before enabling remote write operations
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.utils import ROOT, ensure_dir, now_iso
from engine.proposal_engine import get_proposal

ROLLBACK_VERIFICATION_DIR = ROOT / "state" / "rollback_verifications"
ROLLBACK_VERIFICATION_LOG = ROOT / "runtime" / "logs" / "rollback_tests.log"


@dataclass
class RollbackVerificationResult:
    """Result of a rollback verification test"""
    test_id: str
    timestamp: str
    passed: bool
    component: str
    description: str
    details: dict[str, Any]
    error_message: str | None = None


def ensure_rollback_dirs() -> None:
    """Ensure rollback verification directories exist"""
    ensure_dir(ROLLBACK_VERIFICATION_DIR)
    ensure_dir(ROLLBACK_VERIFICATION_LOG.parent)


def log_verification(message: str) -> None:
    """Log verification activity"""
    ensure_rollback_dirs()
    timestamp = datetime.now().isoformat()
    with open(ROLLBACK_VERIFICATION_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def verify_backup_directory_access() -> RollbackVerificationResult:
    """Verify backup directory is accessible and writable"""
    test_id = f"backup_dir_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir = ROOT / "runtime" / "backups"
    
    try:
        ensure_dir(backup_dir)
        test_file = backup_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        
        log_verification(f"✓ Backup directory access verified: {backup_dir}")
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=True,
            component="backup_directory",
            description="Backup directory is accessible and writable",
            details={"path": str(backup_dir)},
        )
    except Exception as e:
        log_verification(f"✗ Backup directory access failed: {e}")
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=False,
            component="backup_directory",
            description="Backup directory verification failed",
            details={"path": str(backup_dir)},
            error_message=str(e),
        )


def verify_backup_creation() -> RollbackVerificationResult:
    """Verify that file backups can be created"""
    test_id = f"backup_create_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_root = ROOT / "runtime" / "backups" / test_id
    test_file_rel = "tests/test_rollback_verify.txt"
    test_file = ROOT / test_file_rel
    
    try:
        # Create test file
        test_file.write_text("original content", encoding="utf-8")
        
        # Create backup
        ensure_dir(backup_root / test_file_rel)
        shutil.copy2(test_file, backup_root / test_file_rel)
        
        # Verify backup exists
        backup_file = backup_root / test_file_rel
        if not backup_file.exists():
            raise RuntimeError("Backup file was not created")
        
        # Cleanup
        shutil.rmtree(backup_root)
        test_file.unlink()
        
        log_verification("✓ Backup creation verified")
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=True,
            component="backup_creation",
            description="File backup creation works correctly",
            details={"test_file": test_file_rel},
        )
    except Exception as e:
        log_verification(f"✗ Backup creation failed: {e}")
        # Cleanup on failure
        if backup_root.exists():
            shutil.rmtree(backup_root, ignore_errors=True)
        if test_file.exists():
            test_file.unlink()
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=False,
            component="backup_creation",
            description="Backup creation failed",
            details={},
            error_message=str(e),
        )


def verify_restore_from_backup() -> RollbackVerificationResult:
    """Verify that files can be restored from backup"""
    test_id = f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_root = ROOT / "runtime" / "backups" / test_id
    test_file_rel = "tests/test_rollback_verify.txt"
    test_file = ROOT / test_file_rel
    original_content = "original content"
    modified_content = "modified content"
    
    try:
        # Create and backup original
        test_file.write_text(original_content, encoding="utf-8")
        backup_target = backup_root / test_file_rel
        ensure_dir(backup_target.parent)
        shutil.copy2(test_file, backup_target)
        
        # Modify file
        test_file.write_text(modified_content, encoding="utf-8")
        
        # Restore from backup
        import os
        for file in backup_root.rglob("*"):
            if file.is_file():
                rel_path = file.relative_to(backup_root)
                dst = ROOT / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                # Windows: must remove existing file first
                if dst.exists():
                    os.remove(dst)
                shutil.copy2(file, dst)
        
        # Verify restoration
        restored_content = test_file.read_text(encoding="utf-8")
        if restored_content != original_content:
            raise RuntimeError(f"Restored content mismatch: {restored_content}")
        
        # Cleanup
        shutil.rmtree(backup_root)
        test_file.unlink()
        
        log_verification("✓ Restore from backup verified")
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=True,
            component="restore_from_backup",
            description="File restoration from backup works correctly",
            details={"test_file": test_file_rel},
        )
    except Exception as e:
        log_verification(f"✗ Restore from backup failed: {e}")
        # Cleanup on failure
        if backup_root.exists():
            shutil.rmtree(backup_root, ignore_errors=True)
        if test_file.exists():
            test_file.unlink()
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=False,
            component="restore_from_backup",
            description="Restore from backup failed",
            details={},
            error_message=str(e),
        )


def verify_proposal_backup(proposal_id: str | None = None) -> RollbackVerificationResult:
    """Verify that a proposal's files can be backed up"""
    test_id = f"proposal_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    try:
        # Find a proposal to test with
        if proposal_id:
            proposal = get_proposal(proposal_id)
        else:
            # Find any proposal
            proposals_dir = ROOT / "runtime" / "proposals"
            if proposals_dir.exists():
                proposal_files = list(proposals_dir.glob("*.json"))
                if proposal_files:
                    with open(proposal_files[0], "r", encoding="utf-8") as f:
                        proposal = json.load(f)
                else:
                    # No proposals exist, create a mock test
                    log_verification("ℹ No proposals found, skipping proposal backup test")
                    return RollbackVerificationResult(
                        test_id=test_id,
                        timestamp=now_iso(),
                        passed=True,
                        component="proposal_backup",
                        description="No proposals to test - skipped",
                        details={"reason": "no_proposals"},
                    )
            else:
                raise RuntimeError("Proposals directory does not exist")
        
        files_to_modify = proposal.get("files_to_modify", [])
        
        if not files_to_modify:
            log_verification("ℹ Proposal has no files to modify, skipping")
            return RollbackVerificationResult(
                test_id=test_id,
                timestamp=now_iso(),
                passed=True,
                component="proposal_backup",
                description="Proposal has no files to modify - skipped",
                details={"proposal_id": proposal.get("id")},
            )
        
        # Try to backup each file
        backup_root = ROOT / "runtime" / "backups" / test_id
        backed_up = []
        failed = []
        
        for file_path in files_to_modify:
            src = ROOT / file_path
            if src.exists() and src.is_file():
                dst = backup_root / file_path
                ensure_dir(dst.parent)
                shutil.copy2(src, dst)
                backed_up.append(file_path)
            else:
                failed.append(file_path)
        
        # Cleanup
        if backup_root.exists():
            shutil.rmtree(backup_root)
        
        if failed and not backed_up:
            raise RuntimeError(f"Could not backup any files: {failed}")
        
        log_verification(f"✓ Proposal backup verified ({len(backed_up)} files)")
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=True,
            component="proposal_backup",
            description=f"Proposal backup verified ({len(backed_up)} files)",
            details={
                "proposal_id": proposal.get("id"),
                "backed_up": backed_up,
                "failed": failed,
            },
        )
    except Exception as e:
        log_verification(f"✗ Proposal backup failed: {e}")
        return RollbackVerificationResult(
            test_id=test_id,
            timestamp=now_iso(),
            passed=False,
            component="proposal_backup",
            description="Proposal backup failed",
            details={},
            error_message=str(e),
        )


def run_all_rollback_verifications(
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """
    Run all rollback verification tests
    
    Args:
        proposal_id: Optional specific proposal to test
    
    Returns:
        Summary of all verification results
    """
    ensure_rollback_dirs()
    
    log_verification("=" * 50)
    log_verification("Starting Rollback Policy Verification")
    log_verification("=" * 50)
    
    tests = [
        verify_backup_directory_access(),
        verify_backup_creation(),
        verify_restore_from_backup(),
        verify_proposal_backup(proposal_id),
    ]
    
    passed = sum(1 for t in tests if t.passed)
    failed = len(tests) - passed
    all_passed = failed == 0
    
    # Save verification report
    report = {
        "timestamp": now_iso(),
        "all_passed": all_passed,
        "passed_count": passed,
        "failed_count": failed,
        "total_tests": len(tests),
        "tests": [asdict(t) for t in tests],
    }
    
    report_file = ROLLBACK_VERIFICATION_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    log_verification("=" * 50)
    log_verification(f"Verification Complete: {passed}/{len(tests)} passed")
    log_verification("=" * 50)
    
    return report


def get_latest_verification_report() -> dict[str, Any] | None:
    """Get the most recent verification report"""
    if not ROLLBACK_VERIFICATION_DIR.exists():
        return None
    
    reports = sorted(ROLLBACK_VERIFICATION_DIR.glob("report_*.json"), reverse=True)
    if not reports:
        return None
    
    with open(reports[0], "r", encoding="utf-8") as f:
        return json.load(f)


def is_rollback_policy_verified() -> bool:
    """Check if rollback policy has been verified"""
    report = get_latest_verification_report()
    if report is None:
        return False
    return report.get("all_passed", False)


def get_rollback_status() -> dict[str, Any]:
    """Get current rollback verification status"""
    report = get_latest_verification_report()
    
    if report is None:
        return {
            "verified": False,
            "last_verification": None,
            "message": "No verification has been run",
        }
    
    return {
        "verified": report.get("all_passed", False),
        "last_verification": report.get("timestamp"),
        "passed_tests": report.get("passed_count", 0),
        "total_tests": report.get("total_tests", 0),
        "message": "Rollback policy verified" if report.get("all_passed") else "Some tests failed",
    }
