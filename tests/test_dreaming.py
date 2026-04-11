from engine.dreaming import memory_status, recall, remember_text, run_dream_cycle
from engine.memory_store import initialize_memory_dirs
from engine.github_ingestor import ingest_tool
from engine.tool_registry import get_tool


def test_remember_recall_and_dream(tmp_path):
    initialize_memory_dirs(tmp_path)
    note = remember_text("Use crawl4ai to digest web pages into HAX memory", root=tmp_path)
    assert note["type"] == "manual_note"

    results = recall("crawl4ai", root=tmp_path)
    assert results
    assert results[0]["title"] == note["id"]

    dream = run_dream_cycle(root=tmp_path, trigger="test")
    assert dream["type"] == "dream_cycle_v1"
    assert dream["light_sleep"]["note_count"] == 1
    assert (tmp_path / "memory" / "dreams.md").exists()

    status = memory_status(tmp_path)
    assert status["notes"] == 1
    assert status["dreams"] == 1


def test_dream_includes_tool_records(tmp_path):
    tool = get_tool("rtk")
    ingest_tool(tool, readme_text="# RTK\n\nToken reduction for git status and pytest output.", root=tmp_path)
    dream = run_dream_cycle(root=tmp_path, trigger="test-tool")
    assert dream["light_sleep"]["tool_count"] == 1
    assert "rtk" in dream["deep_sleep"]["tools"]


def test_recall_builds_semantic_index_and_ranks_best_match(tmp_path):
    initialize_memory_dirs(tmp_path)
    ingest_tool(
        get_tool("rtk"),
        readme_text="# RTK\n\nCompress git status, pytest, shell, and log output to reduce token usage.",
        root=tmp_path,
    )
    ingest_tool(
        get_tool("crawl4ai"),
        readme_text="# Crawl4AI\n\nTurn web pages into markdown for ingestion and knowledge capture.",
        root=tmp_path,
    )
    remember_text("Project registry tracks tasks and proposal approvals.", root=tmp_path)

    results = recall("compress git pytest output tokens", root=tmp_path)

    assert results
    assert results[0]["title"] == "RTK"
    assert "pytest" in results[0]["matched_terms"]

    status = memory_status(tmp_path)
    assert status["indexed_documents"] >= 3
    assert status["indexed_terms"] > 0
