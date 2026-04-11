# HAX-Mind Secret Rotation Policy

Updated: 2026-04-12 01:20 Asia/Bangkok

## Scope

This policy covers local and future production use of:
- `TELEGRAM_BOT_TOKEN`
- `PICOCLAW_SHARED_SECRET`
- `PICOCLAW_WORKER_SECRET`

## Current rule

Secrets remain user-managed and must not be printed by the agent.

## Rotation cadence

Recommended baseline:
- Telegram bot token: every 90 days or immediately after suspected exposure
- PicoClaw shared/worker secrets: every 90 days or immediately after suspected exposure

## Operational steps

1. rotate the secret in the upstream system first
2. update the local `.env` or `.env.txt`
3. run:

```powershell
.\run-secret-audit.cmd
.\run-recover.cmd
.\run-health.cmd
```

4. verify bot/worker still authenticate correctly
5. generate a production snapshot:

```powershell
.\run-production-status.cmd
```

## Audit artifact

Current secret presence audit:
- `runtime/reports/secret_status.json`

Use:

```powershell
.\run-secret-audit.cmd
```

## Incident rule

If a secret is suspected exposed:
1. rotate immediately
2. restart affected services
3. generate production snapshot
4. record the event in operator notes / incident log
