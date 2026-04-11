# HAX-Mind Pending Tasks

Updated: 2026-04-12 01:30 Asia/Bangkok
Source of truth: `docs/cto-handoff-status.md` + latest `runtime/reports/morning_report.txt`

## NOW — highest priority

### 1) Post-Phase-4 operator usage
Current state: local Phase 4 productionization is complete for this machine. Remaining work is optional future expansion or ongoing operator use.

Action items:
1. keep using `run-health.cmd`, `run-production-status.cmd`, `run-backup.cmd`, and `run-restore-drill.cmd` as operator routines
2. keep alert checks clean (`run-alerts.cmd`)
3. rotate secrets per `docs/secret-rotation-policy.md`
4. update runbooks when operating patterns change

Definition of done:
- local production operation stays healthy and boring

### 2) Keep proposal queue clean
Current snapshot:
- currently **0 pending proposals**
- duplicate low-risk tool-memory proposals were archived and future identical pending proposals are now deduplicated automatically

Action items:
1. keep duplicate suppression in place for recurring low-risk proposals
2. archive/reject stale future pending items if they stop reflecting real work
3. keep proposal list clean so morning reports stay useful

Definition of done:
- no redundant pending proposals remain
- proposal queue reflects real work only

## NEXT — local operational follow-through

### 3) Optional future expansion beyond this machine
Current state: current scope is complete locally. These are optional next tracks, not blockers.

Action items:
1. move to always-on host / VPS if needed
2. add external monitoring / alert delivery
3. turn restore drill into a full live-restore rehearsal on a replacement target
4. evolve dashboard further if operator needs grow

Definition of done:
- HAX-Mind operates beyond a single workstation

### 4) Observe real operator usage over time on this machine
Current state: local validation evidence exists in `docs/local-daily-driver-validation.md` and `runtime/reports/local_daily_driver_validation.json`. Remaining work is normal user operation over time.

Action items:
1. repeat the validated workflow from actual Telegram chat usage
2. run `run-validate-local.cmd` after meaningful local usage or recovery events
3. observe `/report` and `/morning` across normal daily use
4. capture any UX friction in Telegram command responses

Definition of done:
- validation evidence remains stable across normal operator use

### 5) Optional real reboot/logon confirmation on this machine
Current state: startup launcher simulation, forced-stop recovery, scheduled jobs, and recovery command are all validated. Remaining proof is a true reboot/logon observation.

Action items:
1. reboot or sign out/sign in once
2. confirm bot restarts via Startup fallback
3. run `run-health.cmd`
4. append evidence if behavior changes

Definition of done:
- actual reboot/logon behavior matches the validated simulation

## LATER — productization

### 6) Documentation publishing
Action items:
1. use `docmd` to publish local docs
2. generate `llms.txt` / `llms-full.txt`
3. keep CTO handoff + pending tasks aligned with live state

## ACTIVE BACKLOG ITEMS

### Runtime tasks still present
- `task_20260411_4b791d` — planned — smoke: verify Telegram task to proposal to safe execution flow
- `task_20260411_32c9f2` — planned — memory improvement flow test
- `task_20260411_12657e` — planned — Telegram/HAX-Mind memory-related historical task

### Memory / intelligence follow-ups
These are not blockers, but should be watched as data volume grows:
- tune duplicate-detection thresholds
- prune stale or noisy memories
- normalize Windows/Thai text encoding in report outputs
- review whether file-backed vector memory remains fast enough at larger scale

## BLOCKERS / CONSTRAINTS

### Hard technical constraint
- true autonomous execution still depends on generating explicit file-change payloads from normal task planning

### Operational constraint
- local bot autostart currently uses a Startup-folder fallback because bot scheduled-task registration was denied on this machine

### Product constraint
- dashboard should not be built before monitoring/logging/ops basics exist

## CURRENT VERIFIED STATUS

As of latest verification:
- tests: `50 passed`
- pending proposals: `0`
- memory snapshot:
  - tools = 4
  - repos = 2
  - notes = 9
  - dreams = 11
  - decisions = 11
  - vectors = 37
  - clusters = 1
  - duplicate candidates = 54
- PicoClaw:
  - status = `worker_connected`
  - readiness = `9/9`
  - active workers = `1`

## Suggested execution order
1. Normal operator use on this machine
2. Optional future expansion beyond this machine
3. Optional real reboot/logon confirmation
