# HAX-Mind v0.1.0 Release Notes

Released: 2026-04-12  
Scope: Local single-machine Windows production release

## Summary

HAX-Mind v0.1.0 is the first complete local-production release of the project.

This release turns HAX-Mind from a concept/prototype into a **usable Telegram-first AI operating system on Windows** with:

- project / task / proposal workflow
- memory dreaming and repo knowledge ingestion
- Phase 3 memory intelligence
- guarded real code apply with rollback
- local health / recovery / validation
- Phase 4 local production foundations

## Highlights

### 1. Telegram-first operator workflow

HAX-Mind can now:

- register projects
- create missions / tasks
- generate proposals
- approve / reject proposals
- execute guarded changes
- inspect health and reports from Telegram

### 2. Phase 3 memory intelligence

Delivered in this release:

- hybrid lexical + vector recall
- topic clustering
- promoted decisions
- duplicate-memory detection
- virtual team briefing

### 3. Guarded real apply

`/execute` now supports real file changes when proposals include explicit `metadata.file_changes`.

Safety features:

- protected-path enforcement
- backup before mutation
- diff artifact generation
- post-apply tests
- rollback on failure
- applied only after verification

### 4. Local production operations

Delivered in this release:

- bot supervisor
- recovery command
- local health snapshot
- local validation workflow
- production snapshot + dashboard
- alerts
- backup bundle
- restore workflow + restore drill
- incident runbook
- deployment strategy doc
- secret audit / rotation policy

## Operator commands added / stabilized

### Health / recovery

```powershell
.\run-health.cmd
.\run-recover.cmd
```

### Local validation

```powershell
.\run-validate-local.cmd
```

### Production operations

```powershell
.\run-production-status.cmd
.\run-alerts.cmd
.\run-secret-audit.cmd
.\run-backup.cmd
.\run-restore.cmd
.\run-restore-drill.cmd
```

## Important artifacts

- `runtime/reports/production_status.json`
- `runtime/reports/alerts.json`
- `runtime/reports/secret_status.json`
- `runtime/reports/restore_drill.json`
- `runtime/dashboard/index.html`
- `docs/local-daily-driver-validation.md`
- `docs/production-incident-runbook.md`
- `docs/production-deployment-strategy.md`
- `docs/secret-rotation-policy.md`

## Verification

Release verification:

```text
50 passed
```

Validated areas:

- full automated test suite
- local health snapshot
- recovery command
- local daily-driver validation
- production status generation
- alert evaluation
- secret audit
- backup bundle creation
- restore drill execution

## Known limits

This release is complete for the **local single-machine scope**, but not yet for broader deployment.

Still out of scope:

- external alert delivery
- always-on VPS / multi-host deployment
- live restore into a replacement production host
- large operator dashboard beyond the current local HTML status page

## Recommended next release themes

Candidates for v0.2.0:

1. VPS / always-on deployment strategy execution
2. external monitoring / alert delivery
3. live restore rehearsal on a replacement target
4. operator dashboard expansion
5. more automated proposal generation from normal task text
