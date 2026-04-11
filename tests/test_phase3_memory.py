from pathlib import Path

from engine.dreaming import remember_text, run_dream_cycle
from engine.memory_store import initialize_memory_dirs
from engine.memory_intelligence import list_decisions, run_phase3_cycle
from engine.research_team import generate_team_brief


def test_phase3_cycle_builds_local_vector_memory_and_decisions(tmp_path):
    initialize_memory_dirs(tmp_path)
    remember_text("Use crawl4ai for web ingestion and markdown knowledge capture", root=tmp_path)
    remember_text("Use crawl4ai for web ingestion and markdown knowledge capture", root=tmp_path)
    run_dream_cycle(root=tmp_path, trigger="phase3-a")
    run_dream_cycle(root=tmp_path, trigger="phase3-b")

    summary = run_phase3_cycle(root=tmp_path)

    assert summary["vector_documents"] >= 4
    assert summary["topic_clusters"] >= 1
    assert summary["decisions"] >= 1
    assert summary["duplicate_candidates"] >= 1
    assert list_decisions(root=tmp_path)


def test_team_brief_writes_report_from_phase3_memory(tmp_path):
    initialize_memory_dirs(tmp_path)
    remember_text("RTK should compress pytest output before memory ingestion", root=tmp_path)
    remember_text("RTK should compress pytest output before memory ingestion", root=tmp_path)
    run_dream_cycle(root=tmp_path, trigger="team-a")
    run_dream_cycle(root=tmp_path, trigger="team-b")
    run_phase3_cycle(root=tmp_path)

    brief = generate_team_brief("compress pytest output tokens", root=tmp_path)

    assert brief["memory_hits"]
    assert Path(tmp_path / brief["report_path"]).exists()
    assert "## Analyst" in brief["memo"]
    assert "## Critic" in brief["memo"]
