from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.morning_report import generate_morning_report
from engine.picoclaw_manager import claim_remote_job, complete_remote_job, get_remote_job, list_remote_jobs, record_worker_heartbeat


def _secret(value: str | None) -> str | None:
    return value or os.environ.get("PICOCLAW_SHARED_SECRET") or os.environ.get("PICOCLAW_WORKER_SECRET")


def run_worker_cycle(worker_id: str, platform: str = "termux", root: Path = Path.cwd()) -> dict:
    secret = _secret(None)
    if not secret:
        raise RuntimeError("PICOCLAW_SHARED_SECRET or PICOCLAW_WORKER_SECRET is required")

    heartbeat = record_worker_heartbeat(
        worker_id,
        secret,
        platform=platform,
        capabilities=["read_only_repo"],
        root=root,
    )
    job = claim_remote_job(worker_id, secret, root=root)
    if not job:
        return {"worker_id": worker_id, "heartbeat": heartbeat, "job": None}

    job_type = job.get("job_type") or job.get("job_kind")
    if job_type == "morning_report":
        generate_morning_report(root=root)

    complete_remote_job(
        job["id"],
        worker_id,
        secret,
        {"job_type": job_type, "handled": True},
        status="completed",
        root=root,
    )
    saved_job = get_remote_job(job["id"], root=root)
    return {"worker_id": worker_id, "heartbeat": heartbeat, "job": saved_job}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PicoClaw Phase 2 worker bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    heartbeat = subparsers.add_parser("heartbeat", help="Record a worker heartbeat")
    heartbeat.add_argument("--worker-id", required=True)
    heartbeat.add_argument("--platform", default="termux")
    heartbeat.add_argument("--capability", action="append", default=[])
    heartbeat.add_argument("--secret")

    claim = subparsers.add_parser("claim", help="Claim the next pending remote job")
    claim.add_argument("--worker-id", required=True)
    claim.add_argument("--secret")

    complete = subparsers.add_parser("complete", help="Complete a claimed remote job")
    complete.add_argument("--worker-id", required=True)
    complete.add_argument("--job-id", required=True)
    complete.add_argument("--status", choices=["completed", "failed"], required=True)
    complete.add_argument("--summary", required=True)
    complete.add_argument("--secret")

    list_jobs = subparsers.add_parser("list", help="List remote jobs")
    list_jobs.add_argument("--status")

    cycle = subparsers.add_parser("cycle", help="Run one worker heartbeat + claim + complete cycle")
    cycle.add_argument("--worker-id", required=True)
    cycle.add_argument("--platform", default="termux")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "heartbeat":
        payload = record_worker_heartbeat(
            args.worker_id,
            _secret(args.secret),
            platform=args.platform,
            capabilities=args.capability,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if args.command == "claim":
        payload = claim_remote_job(args.worker_id, _secret(args.secret))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if args.command == "complete":
        payload = complete_remote_job(
            args.job_id,
            args.worker_id,
            _secret(args.secret),
            status=args.status,
            summary=args.summary,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if args.command == "list":
        payload = list_remote_jobs(status=args.status)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if args.command == "cycle":
        payload = run_worker_cycle(worker_id=args.worker_id, platform=args.platform)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
