from __future__ import annotations

from engine.proposal_engine import create_proposal


def analyze_system_signals() -> dict:
    return {
        "top_problem": "tool knowledge is not yet promoted into canonical memory",
        "component": "memory/tools",
        "evidence": [
            "Initial HAX-Mind plan needs a way to digest external tools into memory.",
            "Owner provided crawl4ai, Reverse-Engineer, docmd, and rtk repositories as tool sources.",
        ],
    }


def generate_improvement_proposal() -> dict:
    signals = analyze_system_signals()
    return create_proposal(
        title="Promote external tool repos into canonical memory",
        component=signals["component"],
        problem=signals["top_problem"],
        root_cause="Phase 1 memory started with raw logs but no durable tool registry or repo ingestion job.",
        solution="Run jobs/ingest_tool_repos.py and review memory/canonical/tools plus memory/topic_summaries/tools.md.",
        expected_impact="HAX-Mind can choose crawl, reverse engineering, docs, and token-compression tools from memory.",
        risk="low",
        files_to_modify=[
            "engine/tool_registry.py",
            "engine/github_ingestor.py",
            "memory/canonical/tools/*.json",
            "memory/topic_summaries/tools.md",
        ],
        tests_to_run=[
            "tests/test_tool_registry.py",
            "tests/test_github_ingestor.py",
        ],
        rollback_plan="Delete generated canonical tool records and restore the previous registry from version control or backup.",
    )
