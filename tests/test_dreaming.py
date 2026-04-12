from engine.dream_tasks import create_task_from_dream
from engine.dreaming import explain_dream, latest_dream, list_dreams, memory_status, recall, remember_text, run_dream_cycle
from engine.memory_store import initialize_memory_dirs
from engine.github_ingestor import ingest_tool
from engine.project_manager import register_project
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


def test_explain_dream_and_create_task_from_latest_dream(tmp_path):
    register_project("HAXMind", str(tmp_path), root=tmp_path)
    dream = run_dream_cycle(root=tmp_path, trigger="test-dream-task")

    latest = latest_dream(root=tmp_path)
    listed = list_dreams(root=tmp_path, limit=1)
    explanation = explain_dream(latest, root=tmp_path)
    mission = create_task_from_dream(project_id="haxmind", root=tmp_path)

    assert latest["id"] == dream["id"]
    assert listed[0]["id"] == dream["id"]
    assert "generated memory-reflection note" in explanation
    assert mission["project_id"] == "haxmind"
    assert mission["source_dream_id"] == dream["id"]
    assert "Dream follow-up from" in mission["description"]
