from __future__ import annotations

import json
from pathlib import Path

from engine.dreaming import memory_status
from engine.picoclaw_manager import picoclaw_status
from engine.proposal_engine import list_proposals
from engine.utils import ROOT, now_iso


def _read_latest_json(directory: Path, limit: int) -> list[dict]:
    if not directory.exists():
        return []
    records = []
    for path in sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            records.append(json.loads(path.read_text(encoding='utf-8')))
        except json.JSONDecodeError:
            continue
    return records


def _tool_lines(root: Path) -> list[str]:
    tool_dir = root / 'memory' / 'canonical' / 'tools'
    if not tool_dir.exists():
        return ['- Tool memory: no canonical tools ingested yet.']
    records = []
    for path in sorted(tool_dir.glob('*.json')):
        try:
            records.append(json.loads(path.read_text(encoding='utf-8')))
        except json.JSONDecodeError:
            continue
    if not records:
        return ['- Tool memory: no canonical tools ingested yet.']
    return [f"- {item['name']}: {item['role']} ({len(item.get('capabilities', []))} capabilities)" for item in records]


def generate_morning_report(root: Path = ROOT) -> str:
    report_dir = root / 'runtime' / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    proposals = list_proposals(limit=50, root=root)
    pending = [proposal for proposal in proposals if proposal.get('status') == 'pending']
    status = memory_status(root)
    projects = _read_latest_json(root / 'workspace' / 'projects', 5)
    missions = _read_latest_json(root / 'runtime' / 'missions', 5)
    latest_proposals = proposals[:5]
    picoclaw = picoclaw_status(root)
    picoclaw_ready = picoclaw['readiness']
    picoclaw_done = sum(1 for value in picoclaw_ready.values() if value)
    picoclaw_total = len(picoclaw_ready)
    project_lines = [f"- {p['id']}: {p['path_or_repo']}" for p in projects] if projects else ['- No projects registered.']
    mission_lines = [f"- {m['id']} | {m['project_name']} | {m['status']} | {m['description'][:100]}" for m in missions] if missions else ['- No tasks created.']
    proposal_lines = [f"- {p['id']} | {p['risk']} | {p['status']} | {p['title'][:100]}" for p in latest_proposals] if latest_proposals else ['- No proposals.']

    lines = [
        f"Morning Report - {now_iso()}",
        '',
        f"Pending proposals: {len(pending)}",
        f"Known proposals: {len(proposals)}",
        (
            "Memory status: "
            f"tools={status['tools']}, repos={status['repos']}, notes={status['notes']}, dreams={status['dreams']}, "
            f"decisions={status.get('decisions', 0)}, raw_logs={status['raw_logs']}, "
            f"vectors={status.get('vector_documents', 0)}, clusters={status.get('topic_clusters', 0)}, duplicates={status.get('duplicate_candidates', 0)}"
        ),
        '',
        'Tool memory:',
        *_tool_lines(root),
        '',
        'Latest projects:',
        *project_lines,
        '',
        'Latest tasks:',
        *mission_lines,
        '',
        'Latest proposals:',
        *proposal_lines,
        '',
        'PicoClaw Phase 2:',
        f"- Status: {picoclaw['status']} (Phase {picoclaw['phase']})",
        f"- Readiness: {picoclaw_done}/{picoclaw_total}",
        f"- Worker auth secret configured: {picoclaw_ready['worker_auth_secret_configured']}",
        f"- Active workers: {picoclaw.get('active_workers', 0)}",
        f"- Last heartbeat: {picoclaw.get('last_heartbeat_at') or 'none yet'}",
        f"- Remote queue: queued={picoclaw.get('queued_jobs', 0)}",
        '',
        'Recommended next action:',
        '- Use /task <project_id> <work>, then /propose <task_id>, /approve <proposal_id>, /execute <proposal_id>.',
        '- Use /phase3 now, /clusters, /decisions, or /team <topic> to exploit Phase 3 memory intelligence.',
    ]
    text = '\n'.join(lines) + '\n'
    (report_dir / 'morning_report.txt').write_text(text, encoding='utf-8')
    return text
