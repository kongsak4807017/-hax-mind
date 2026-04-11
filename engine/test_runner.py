from __future__ import annotations

import subprocess
import sys


def run_tests(test_targets: list[str]) -> dict:
    results = []
    all_passed = True
    for target in test_targets:
        cmd = [sys.executable, "-m", "pytest", target]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        passed = proc.returncode == 0
        all_passed = all_passed and passed
        results.append(
            {
                "target": target,
                "passed": passed,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            }
        )
    return {"all_passed": all_passed, "results": results}
