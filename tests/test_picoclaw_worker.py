from jobs.picoclaw_worker import build_parser


def test_picoclaw_worker_parser_heartbeat():
    parser = build_parser()
    args = parser.parse_args(["heartbeat", "--worker-id", "termux-main", "--capability", "read_only_repo"])

    assert args.command == "heartbeat"
    assert args.worker_id == "termux-main"
    assert args.capability == ["read_only_repo"]


def test_picoclaw_worker_parser_complete():
    parser = build_parser()
    args = parser.parse_args(
        [
            "complete",
            "--worker-id",
            "termux-main",
            "--job-id",
            "pjob_123",
            "--status",
            "completed",
            "--summary",
            "all good",
        ]
    )

    assert args.command == "complete"
    assert args.worker_id == "termux-main"
    assert args.job_id == "pjob_123"
    assert args.status == "completed"
    assert args.summary == "all good"
