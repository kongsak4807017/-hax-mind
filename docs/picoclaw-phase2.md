# PicoClaw Phase 2 Plan

Status: `worker_connected`

## Role

Termux/worker gateway for remote execution, scheduling, and always-on relay

## Readiness
- local_telegram_bot: True
- memory_dreaming_v1: True
- task_queue: True
- proposal_gate: True
- safe_executor: True
- termux_worker_installed: True
- worker_auth_secret_configured: True
- heartbeat_endpoint: True
- remote_job_queue: True

## Control plane

- Last heartbeat: 2026-04-11T15:34:33+07:00
- Last worker: termux-smoke-test
- Queue pending: 0
- Queue claimed: 0
- Queue completed: 1
- Queue failed: 0

## Next steps
1. Keep the Windows Telegram bot as the source-of-truth command center.
2. Install PicoClaw/worker on Termux only after local task/proposal loop stays stable.
3. Add a shared worker auth secret outside git.
4. Add heartbeat + job queue before allowing remote execution.
5. Keep remote worker read-only until rollback and logs are proven.

## Worker secret

Add this to `.env` or `.env.txt` on the Windows brain and on the worker manually:

```text
PICOCLAW_SHARED_SECRET=generate_a_long_random_shared_secret
PICOCLAW_WORKER_ID=termux-main
```

## Runtime paths

- `runtime/picoclaw/heartbeats/`
- `runtime/picoclaw/jobs/`
- `runtime/picoclaw/results/`
- `runtime/picoclaw/logs/`

## Local validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests
$env:PICOCLAW_SHARED_SECRET='YOUR_SECRET'
.\.venv\Scripts\python.exe jobs\picoclaw_worker.py heartbeat --worker-id termux-smoke --platform termux
.\.venv\Scripts\python.exe jobs\picoclaw_worker.py cycle --worker-id termux-smoke --platform termux
```

## Termux install sketch

```bash
pkg update && pkg upgrade -y
pkg install git nodejs python -y
git clone https://github.com/sipeed/picoclaw.git
cd picoclaw
./picoclaw-linux-arm64
# then run the HAX-Mind worker heartbeat / queue commands
```

Do not enable remote code execution until heartbeat, auth, logs, rollback, and safe-mode policy are verified.
