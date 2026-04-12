# HAX-Mind v0.2.1 Draft Release Notes

Drafted: 2026-04-13  
Based on commit: `3b66ae8`  
Scope: Telegram-driven local CLI session orchestration

## Summary

This release evolves HAX-Mind from basic Telegram-triggered local CLI launches into a **tracked multi-step CLI session operator**.

The main outcome is that Kimi, Gemini, Codex, and OMX can now be driven from Telegram as structured sessions instead of one-shot prompts only.

## Highlights

### 1. Multi-step CLI sessions

HAX-Mind now supports session-oriented local CLI control from Telegram:

- start a tracked session
- continue the same session across multiple turns
- inspect the latest session and latest job proof
- close a session explicitly

Supported tools:

- Kimi
- Gemini
- Codex
- OMX

### 2. Per-tool profiles

The CLI bridge now exposes tool-specific profiles instead of treating all CLIs the same.

#### Kimi

- `default`
- `thinking`
- `yolo`

#### Gemini

- `default`
- `plan`
- `yolo`

#### Codex

- `review`
- `default`
- `yolo`

#### OMX

- `review`
- `default`
- `yolo`

### 3. Review / approval model for write-capable sessions

Codex and OMX now support a safer staged flow:

1. start in `review`
2. inspect result
3. explicitly approve
4. continue in a write-capable profile

This avoids treating all local CLI sessions as implicitly safe for mutation.

### 4. Better proof and inspection from Telegram

The Telegram `/cli` surface now includes:

```text
/cli latest
/cli jobs
/cli sessions
/cli session <id|latest>
/cli status <job_id>
/cli mode <session_id|latest> <profile>
/cli approve <session_id|latest>
/cli diff
/cli close <session_id|latest>
```

These make it easier to see:

- what was opened
- what ran last
- which session is active
- whether approval was granted
- whether a recent Codex/OMX step produced a diff

### 5. Easier Telegram UX

Short-form commands now work more naturally, for example:

```text
/cli kimi ช่วยวางแผนงาน hax-mind
/cli gemini plan สรุป repo นี้
/cli codex review inspect current repo safely
/cli omx review inspect current repo safely
```

## Operator examples

### Kimi

```text
/cli start kimi thinking วางแผนงาน hax-mind ใน workspace
/cli continue latest แตกเป็น 3 step ถัดไป
/cli session latest
/cli close latest
```

### Gemini

```text
/cli start gemini plan สรุปสิ่งที่ควรทำต่อใน repo นี้
/cli continue latest เปรียบเทียบ 3 ทางเลือก
/cli session latest
/cli close latest
```

### Codex

```text
/cli start codex review inspect the repo and suggest the safest next code changes
/cli approve latest
/cli continue latest implement the approved step
/cli diff
/cli session latest
/cli close latest
```

### OMX

```text
/cli start omx review inspect the repo and suggest the safest orchestration next step
/cli approve latest
/cli continue latest implement the next safe step
/cli diff
/cli session latest
/cli close latest
```

## Files changed in this release

Primary implementation files:

- `engine/cli_bridge.py`
- `engine/orchestrator.py`
- `bot/telegram_bot.py`
- `README.md`

Primary test coverage:

- `tests/test_cli_bridge.py`
- `tests/test_orchestrator.py`

## Verification

Verified in local development:

```text
81 passed
```

Additional verification performed:

- `python -m compileall bot engine tests`
- live Kimi session start/continue/close
- live Gemini session start
- live Codex review -> approve -> continue
- live OMX review -> approve -> continue

## Known limits

- Thai natural-language routing still has edge cases depending on terminal and encoding path
- `/cli artifact latest` and `/cli output latest` are still pending as separate convenience commands
- session semantics are strongest for Kimi/Gemini/Codex/OMX; other local CLIs remain out of scope
- arbitrary shell execution is intentionally not exposed through Telegram

## Recommended next follow-up

1. add `/cli artifact latest`
2. add `/cli output latest`
3. harden Thai natural-language routing for CLI/session requests
4. improve artifact review summaries for Codex/OMX write-capable flows
