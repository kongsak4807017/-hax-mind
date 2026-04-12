# HAX-Mind

[![Local Production](https://img.shields.io/badge/local%20production-ready-2ea043)](docs/cto-handoff-status.md)
[![Tests](https://img.shields.io/badge/tests-50%20passed-2ea043)](docs/cto-handoff-status.md)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4)](#local-always-on-status-on-this-machine)
[![Python](https://img.shields.io/badge/python-3.12-blue)](requirements.txt)
[![Telegram](https://img.shields.io/badge/control-Telegram-26A5E4)](#telegram-commands)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#ready-for-github)

HAX-Mind is a **local AI operating system for Windows** that uses **Telegram as the command center**, **Codex/OMX-style workflows as the brain**, and a **file-first memory system** as the durable knowledge layer.

It is designed to:

- accept work through Telegram
- track projects, tasks, and proposals
- analyze repositories into reusable memory
- run guarded code changes with backup + rollback
- maintain local operational health, recovery, backup, and restore workflows

---

## Current project status

HAX-Mind is **complete for the current single-machine local-production scope**.

Completed milestone areas:

- local Telegram command center
- task / proposal / approval workflow
- repository analysis + memory dreaming
- hybrid recall + vector memory + clustering + decisions
- guarded real apply with backup / diff / rollback
- local health checks + recovery
- local daily-driver validation
- local productionization foundations:
  - status snapshots
  - operator dashboard
  - alerts
  - backup bundles
  - restore drill
  - incident runbook
  - secret audit / rotation policy

Latest verified test state:

```text
50 passed
```

---

## Architecture overview

```text
Telegram
  -> Bot command center
  -> Project / mission queue
  -> Proposal / approval loop
  -> Guarded execution
  -> Memory + dreaming
  -> Phase 3 intelligence
       -> hybrid recall
       -> vector index
       -> topic clusters
       -> promoted decisions
       -> duplicate detection
       -> virtual team brief
  -> Local health / production ops
       -> supervisor
       -> recovery
       -> alerts
       -> backup
       -> restore drill
       -> dashboard
```

---

## What HAX-Mind can do now

### 1. Telegram-driven work management

- register projects
- create tasks / missions
- generate proposals
- approve / reject proposals
- execute guarded changes
- inspect status and reports
- optionally route plain-language requests through OpenRouter into the same task / proposal / execute workflow

### 2. File-first memory system

- manual memory capture
- repo knowledge ingestion
- memory dreaming
- recall across tools, repos, notes, dreams, and decisions

### 3. Guarded real apply

`/execute` supports real file changes when the approved proposal contains explicit `metadata.file_changes`.

Safety guarantees:

- protected path enforcement from `policies/risk_policy.yaml`
- backups before mutation
- diff artifact generation
- post-apply tests
- automatic rollback on failed tests
- proposal marked `applied` only after verification

### 4. Local production operations

- bot supervisor
- recovery command
- health snapshot
- production status snapshot
- alerts
- backup bundle
- restore drill
- local dashboard

---

## Repository layout

```text
bot/        Telegram bot and command handling
docs/       CTO handoff, runbooks, policies, validation notes
engine/     Core HAX-Mind logic
jobs/       Nightly / morning / ingestion jobs
memory/     Durable file-based memory stores
policies/   Risk and safety policies
runtime/    Reports, logs, proposals, backups, restore drills, dashboard
scripts/    PowerShell automation for local operations
tests/      Verification suite
workspace/  Registered local projects
```

---

## Quick start

### Easiest setup on this machine

If you want a guided setup flow inspired by Hermes-style onboarding, run:

```powershell
.\setup-haxmind.cmd
```

It will let you choose a setup mode:

- **Quick local setup** — create/use `.venv`, install requirements, create `.env` from template, run tests
- **Telegram bot setup** — quick setup + secret audit + easy bot launch path
- **Local production setup** — quick setup + secret audit + scheduled tasks + background startup path
- **Repair / re-check** — reinstall deps, run tests, and refresh health output

The setup wizard also now supports:

- a **detailed start-mode menu**
  - visible in this setup window
  - visible in a new terminal window
  - background / supervised
  - don't start now
- optional **OpenRouter configuration**
  - asks for API key
  - asks for model
  - writes `OPENROUTER_*` values into `.env` or `.env.txt`
  - defaults to `openrouter/free` for a free-router starting point

### 1. Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests
```

### 2. Configure secrets

Copy `.env.example` to `.env` and set your values manually.

Supported local env files:

- `.env`
- `.env.txt`

The agent should never print or rewrite your secret values.

### 3. Start the bot

```powershell
.\run-bot.cmd
```

If you want the local production supervision path:

```powershell
.\run-recover.cmd
```

If you want a **single-click launcher** on this machine, use:

```powershell
.\run-all.bat
```

What `run-all.bat` does:

- stops any old hidden bot/supervisor instance first
- runs the local health check
- generates a production status snapshot
- opens the local dashboard if it already exists
- launches the Telegram bot in a **visible terminal window** and keeps that window open while the bot is running

If you want the hidden/background recovery path instead, keep using:

```powershell
.\run-recover.cmd
```

### 4. Check health

```powershell
.\run-health.cmd
```

---

## Telegram commands

### Core commands

```text
/start
/whoami
/auth
/status
/restart
/health
/project add <name> <path_or_repo>
/project list
/task <project_id> <work description>
/tasks
/taskstatus <task_id>
/taskdone <task_id>
/propose <task_id>
/approve <proposal_id>
/reject <proposal_id>
/execute <proposal_id>
/rollback <proposal_id>
/report
/morning
/nightly now
/cli tools
/cli jobs
/cli status <job_id>
/cli open <codex|omx|gemini|kimi> <prompt>
/cli run <codex|omx|gemini|kimi> <prompt>
/cli improve
```

### Natural-language orchestration

If `OPENROUTER_API_KEY` is configured, you can also talk to the bot in plain language, for example:

```text
create a task for haxmind to append README.md with a short deployment note
make a proposal for task_20260412_abcd12
approve proposal prop_20260412_abcd1234
execute proposal prop_20260412_abcd1234
show me project status
analyze repo microsoft/TypeScript
```

The OpenRouter router maps these requests onto the existing guarded HAX-Mind engine actions.

### Local CLI delegation from Telegram

HAX-Mind can now delegate work to allowlisted local CLIs on this machine:

- `codex`
- `omx`
- `gemini`
- `kimi`

Use:

```text
/cli tools
/cli open codex inspect the current workspace and suggest next steps
/cli run gemini summarize the current repo status
/cli jobs
/cli status <job_id>
/cli improve
```

This gives Telegram-triggered local CLI delegation without exposing arbitrary shell execution.

Dreams are memory-reflection artifacts, not scheduled tasks. If you want to turn the latest dream into real work, create a task from it:

```text
/dream task <project_id>
```

For risky natural-language execution requests, HAX-Mind now uses a confirmation gate:

```text
execute proposal prop_20260412_abcd1234
```

The bot will ask for confirmation first. Reply:

```text
YES
```

to continue, or:

```text
NO
```

to cancel.

### Memory + intelligence

```text
/memory
/remember <text>
/recall <query>
/dream now
/dream latest
/dream explain [dream_id|latest]
/dream task <project_id> [dream_id|latest]
/phase3 now
/clusters
/decisions
/team <topic>
/team plan <task_id>
/team list
/team status <task_id>
/analyze repo <url_or_owner/repo>
```

### PicoClaw local control plane

```text
/picoclaw status
/picoclaw plan
/picoclaw jobs
/picoclaw queue <approved_proposal_id>
```

---

## Structured task syntax for guarded real apply

To create tasks that can become executable guarded proposals automatically, use structured task descriptions:

```text
append <path> :: <content>
replace <path> :: <content>
create <path> :: <content>
delete <path>
```

Example:

```text
/task haxmind append README.md :: Added a new note
```

This lets the mission/proposal pipeline prepare `metadata.file_changes` so `/execute` can perform a real guarded apply.

Example proposal metadata:

```json
{
  "file_changes": [
    {
      "path": "docs/example.md",
      "mode": "replace",
      "content": "# New content\n"
    }
  ]
}
```

---

## Local operations

### Health / recovery

```powershell
.\run-health.cmd
.\run-recover.cmd
```

### Daily-driver validation

```powershell
.\run-validate-local.cmd
```

Validation evidence:

- `docs/local-daily-driver-validation.md`
- `runtime/reports/local_daily_driver_validation.json`

### Production-style status / dashboard

```powershell
.\run-production-status.cmd
```

Artifacts:

- `runtime/reports/production_status.json`
- `runtime/reports/history/production_status_*.json`
- `runtime/dashboard/index.html`

### Alerts

```powershell
.\run-alerts.cmd
```

Artifact:

- `runtime/reports/alerts.json`

### Secret audit

```powershell
.\run-secret-audit.cmd
```

Artifact:

- `runtime/reports/secret_status.json`

### Backups / restore

```powershell
.\run-backup.cmd
.\run-restore.cmd
.\run-restore-drill.cmd
```

Artifacts:

- `runtime/backups/haxmind_backup_*.zip`
- `runtime/reports/restore_drill.json`
- `runtime/restore_drills/restore_*/`

---

## Scheduled tasks on this machine

Registered local tasks:

- `HAX-Mind-Tool-Ingest`
- `HAX-Mind-Nightly`
- `HAX-Mind-Morning`
- `HAX-Mind-Production-Status`
- `HAX-Mind-Alerts`

Because Telegram bot scheduled-task registration is denied on this machine, bot autostart uses a **Startup-folder fallback**:

```text
C:\Users\kongs\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HAX-Mind-Telegram-Bot.cmd
```

Check task status:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\get-scheduled-tasks-status.ps1
```

Re-register tasks:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register-scheduled-tasks.ps1
```

---

## Tool knowledge sources

The initial curated tools are defined in:

- `engine/tool_registry.py`
- `planner/tools_manifest.yaml`

| Tool | Role |
| --- | --- |
| crawl4ai | Web-to-Markdown / memory ingestion |
| Reverse-Engineer | Repo / site blueprint analysis |
| docmd | Documentation / `llms.txt` generation |
| rtk | Token reduction for logs / command output |

---

## Key documents

- `docs/cto-handoff-status.md`
- `docs/pending-tasks.md`
- `docs/local-daily-driver-validation.md`
- `docs/production-incident-runbook.md`
- `docs/production-deployment-strategy.md`
- `docs/secret-rotation-policy.md`

---

## Safety rules

- Do not edit `.env` automatically
- Do not delete memory stores
- Do not disable tests or rollback
- Keep risky changes behind explicit proposals and approval
- Prefer guarded apply over ad-hoc mutation

---

## Current scope vs future scope

### Complete now

- single-machine local production use on Windows
- Telegram-first operator workflow
- local health / recovery / backup / restore drill

### Optional future expansion

- always-on VPS / external host
- external monitoring / alert delivery
- full live restore rehearsal on a replacement target
- larger operator dashboard
- broader multi-machine worker deployment

---

## Ready for GitHub

This repository is now documented as a real, working local AI operations system with:

- verified test coverage
- operational scripts
- runbooks
- production-like local foundations

If you push this to GitHub, the recommended first docs for readers are:

1. `README.md`
2. `docs/cto-handoff-status.md`
3. `docs/production-incident-runbook.md`
