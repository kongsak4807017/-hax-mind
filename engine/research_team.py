from __future__ import annotations

import json
from pathlib import Path

from engine.memory_intelligence import hybrid_recall
from engine.utils import ROOT, ensure_dir, now_iso


def _latest_decisions(root: Path = ROOT, limit: int = 5) -> list[dict]:
    decision_dir = root / "memory" / "canonical" / "decisions"
    if not decision_dir.exists():
        return []
    items: list[dict] = []
    for path in sorted(decision_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return items


def list_decisions(root: Path = ROOT, limit: int = 10) -> list[dict]:
    return _latest_decisions(root=root, limit=limit)


def generate_team_brief(topic: str, root: Path = ROOT) -> dict:
    topic = topic.strip()
    if not topic:
        raise ValueError("Topic is required")

    memory_hits = hybrid_recall(topic, root=root, limit=6)
    decisions = _latest_decisions(root, limit=4)

    analyst_lines = [
        f"- {item['title']} ({item['type']}) @ {item['path']}"
        for item in memory_hits[:3]
    ] or ["- No strong matching memory yet."]
    builder_lines = [
        f"- Reuse knowledge from {item['title']} with matched terms: {', '.join(item.get('matched_terms', [])[:4]) or 'n/a'}"
        for item in memory_hits[:3]
    ] or ["- Gather more memory before building."]
    critic_lines = [
        f"- Check ambiguity in {item['title']} because hybrid_score={item.get('score', 0)} and lexical_score={item.get('lexical_score', 0)}"
        for item in memory_hits[:2]
    ] or ["- No evidence means higher execution risk."]
    operator_lines = [
        f"- {item['summary']}"
        for item in decisions[:3]
    ] or ["- Run /dream now to promote more repeated guidance into decisions."]

    memo = "\n".join(
        [
            f"# HAX-Mind Team Brief: {topic}",
            "",
            f"Generated: {now_iso()}",
            "",
            "## Analyst",
            *analyst_lines,
            "",
            "## Builder",
            *builder_lines,
            "",
            "## Critic",
            *critic_lines,
            "",
            "## Operator",
            *operator_lines,
            "",
        ]
    )

    report_dir = root / "runtime" / "reports"
    ensure_dir(report_dir)
    report_path = report_dir / f"team_brief_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}.md"
    report_path.write_text(memo + "\n", encoding="utf-8")
    return {
        "topic": topic,
        "generated_at": now_iso(),
        "report_path": str(report_path.relative_to(root)),
        "memory_hits": memory_hits,
        "decisions": decisions,
        "memo": memo,
    }
