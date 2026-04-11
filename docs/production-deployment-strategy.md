# HAX-Mind Production Deployment Strategy

Updated: 2026-04-12 01:20 Asia/Bangkok

## Decision

For the current owner workflow, the **primary strategy** is:

1. keep HAX-Mind usable as a local Windows daily driver
2. preserve production artifacts locally
3. only move to VPS/always-on hosting after operator habits and incident handling are stable

## Deployment tracks

### Track A — Local workstation production

Use when:
- the owner primarily works on this Windows machine
- Telegram is the command center
- the current goal is reliability, not internet-facing multi-user service

Current implemented foundations:
- bot supervisor
- Startup fallback launcher
- scheduled jobs for ingest/nightly/morning/production-status
- health snapshot
- production snapshot/dashboard
- backup bundle
- restore drill
- incident runbook

### Track B — Always-on single-host production

Use when:
- the owner wants unattended operation beyond one logged-in session
- daily workflows are already stable locally

Suggested host choices:
- Windows mini PC / always-on workstation
- Windows VPS if Telegram-first workflow must remain Windows-native
- Linux VPS only after translating current Windows startup/scheduler assumptions

## Recommendation

### Near-term recommendation
- stay on **Track A**
- keep validating real operator usage
- keep generating backups and restore drills

### Next upgrade recommendation
- move to **Track B** only after:
  - local operator workflow is boring/stable
  - restore drill stays green
  - alerting/health snapshots are reviewed regularly

## Production checklist before moving hosts

- [x] bot supervision exists
- [x] local health check exists
- [x] production dashboard exists
- [x] backup bundle exists
- [x] restore drill exists
- [x] incident runbook exists
- [ ] live restore procedure rehearsed against a replacement target
- [ ] secret rotation policy operationalized
- [ ] operator reviews alerts regularly
