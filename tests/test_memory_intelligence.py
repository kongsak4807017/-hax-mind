from engine.dreaming import remember_text
from engine.github_ingestor import ingest_tool
from engine.memory_intelligence import (
    cluster_topics,
    detect_duplicate_memories,
    hybrid_recall,
    list_decisions,
    promote_decisions,
    run_phase3_cycle,
    vector_search,
)
from engine.memory_store import initialize_memory_dirs
from engine.tool_registry import get_tool


def test_vector_search_and_hybrid_recall_find_best_memory(tmp_path):
    initialize_memory_dirs(tmp_path)
    ingest_tool(
        get_tool("rtk"),
        readme_text="# RTK\n\nCompress git status, pytest, shell, and log output to reduce token usage.",
        root=tmp_path,
    )
    ingest_tool(
        get_tool("crawl4ai"),
        readme_text="# Crawl4AI\n\nTurn web pages into markdown for ingestion and retrieval.",
        root=tmp_path,
    )
    remember_text("Use token compression before reading large pytest logs.", root=tmp_path)

    vector_results = vector_search("compress pytest output tokens", root=tmp_path)
    hybrid_results = hybrid_recall("compress pytest output tokens", root=tmp_path)

    assert vector_results
    assert vector_results[0]["title"] == "RTK"
    assert hybrid_results
    assert hybrid_results[0]["title"] == "RTK"


def test_phase3_cycle_creates_clusters_decisions_and_duplicate_report(tmp_path):
    initialize_memory_dirs(tmp_path)
    remember_text("Mission decisions should be promoted from repeated planning notes alpha", root=tmp_path)
    remember_text("Mission decisions should be promoted from repeated planning notes beta", root=tmp_path)
    remember_text("Mission planning notes need a decision record for repeated approvals", root=tmp_path)

    clusters = cluster_topics(tmp_path, threshold=0.18, min_cluster_size=2)
    decisions = promote_decisions(tmp_path, threshold=0.18, min_evidence=2)
    duplicates = detect_duplicate_memories(tmp_path, threshold=0.72)
    summary = run_phase3_cycle(tmp_path)

    assert clusters["cluster_count"] >= 1
    assert decisions
    assert list_decisions(tmp_path)
    assert summary["vector_documents"] >= 3
    assert summary["topic_clusters"] >= 1
    assert summary["decisions"] >= 1
    assert isinstance(duplicates, list)
