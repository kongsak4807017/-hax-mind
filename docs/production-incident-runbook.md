# HAX-Mind Production Incident Runbook

Updated: 2026-04-12 00:50 Asia/Bangkok

## Scope

This runbook is for local/production-style operation of HAX-Mind.

## Fast checks

### 1. Health snapshot

```powershell
.\run-health.cmd
```

### 2. Production snapshot + dashboard

```powershell
.\run-production-status.cmd
```

Artifacts:
- `runtime/reports/production_status.json`
- `runtime/reports/history/production_status_*.json`
- `runtime/dashboard/index.html`

### 3. Bot recovery

```powershell
.\run-recover.cmd
```

### 4. Backup bundle

```powershell
.\run-backup.cmd
```

Artifact:
- `runtime/backups/haxmind_backup_*.zip`

### 5. Restore latest backup into a restore target

```powershell
.\run-restore.cmd
```

### 6. Full restore drill

```powershell
.\run-restore-drill.cmd
```

Artifacts:
- `runtime/reports/restore_drill.json`
- `runtime/restore_drills/restore_*/`

## Common incidents

### Bot is down
1. Run `.\run-health.cmd`
2. If `Running: False`, run `.\run-recover.cmd`
3. Re-run `.\run-health.cmd`
4. Check:
   - `runtime/logs/telegram_bot_supervisor.log`
   - `runtime/logs/telegram_bot.lifecycle.log`
   - `runtime/logs/telegram_bot_recovery.log`

### Morning/nightly jobs did not run
1. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\get-scheduled-tasks-status.ps1
```

2. Confirm:
   - `HAX-Mind-Tool-Ingest`
   - `HAX-Mind-Nightly`
   - `HAX-Mind-Morning`

3. Run manually if needed:

```powershell
cmd /c run-ingest-tools.cmd
cmd /c run-nightly.cmd
cmd /c run-morning.cmd
```

### Queue/proposals look wrong
1. Run `.\run-health.cmd`
2. Review `runtime/proposals/*.json`
3. Duplicate low-risk pending proposals can be archived by rerunning:

```powershell
.\run-validate-local.cmd
```

### Need a backup before risky changes
1. Run `.\run-backup.cmd`
2. Confirm zip exists under `runtime/backups/`
3. Record the backup filename in the operator notes

### Need to validate restore readiness
1. Run `.\run-restore-drill.cmd`
2. Confirm `runtime/reports/restore_drill.json` says `"success": true`
3. Inspect the extracted restore target under `runtime/restore_drills/`

## Operational policy

- Prefer local health + recovery first
- Keep proposal queue at zero or near-zero pending unless actively working
- Run backup before risky maintenance
- Generate a production status snapshot before and after major changes

## Productionization next steps

- move from workstation-only operation to always-on host
- add external monitoring/alerting
- move from restore drill to full restore procedure for a live replacement target
- add operator dashboard polish
