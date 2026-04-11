# Local Daily Driver Validation

Validated: 2026-04-12T00:47:07+07:00

## Summary
- Overall success: True
- Startup launcher path: C:\Users\kongs\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HAX-Mind-Telegram-Bot.cmd

## Validation steps
### startup_launcher_recovery
- Success: True
- Detail: validated current supervised state old_pid=20796 new_pid=20796

### tool_ingest_job
- Success: True
- Detail: Ingested 4 tools: - crawl4ai: Crawl4AI -> web_to_markdown_ingestion - reverse_engineer: Reverse-Engineer -> blueprint_analysis - docmd: docmd -> documentation_context - rtk: RTK -> token_compression

### nightly_job
- Success: True
- Detail: Nightly proposal created: prop_20260412_fa381752

### proposal_queue_cleanup
- Success: True
- Detail: archived_duplicates=0

### morning_job
- Success: True
- Detail: Morning Report - 2026-04-12T00:47:07+07:00

## Local Health Snapshot
```text
Local Health - 2026-04-12T00:47:07+07:00

Bot:
- Running: True
- PID file: True
- PID: 20796
- Supervisor PID file: True
- Supervisor PID: 8904
- Supervisor running: True
- Lifecycle log: True
- Supervisor log: True

Reports:
- Morning report exists: True
- Morning report mtime: 1775929627.2864177

Queue:
- Pending proposals: 0
- Known proposals: 19
- Archived duplicates: 14
- Missions: 7

Memory:
- tools=4 repos=2 notes=9 dreams=11 decisions=11 vectors=37 clusters=1 duplicates=54

Automation:
- Startup fallback exists: True
- Startup fallback path: C:\Users\kongs\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HAX-Mind-Telegram-Bot.cmd
```

