from pathlib import Path

from engine.dreaming import remember_text
from engine.research_team import generate_team_brief
from engine.memory_store import initialize_memory_dirs


def test_generate_team_brief_uses_hybrid_memory(tmp_path):
    initialize_memory_dirs(tmp_path)
    remember_text("Use semantic recall and promoted decisions before planning team execution.", root=tmp_path)

    brief = generate_team_brief("semantic recall planning", root=tmp_path)

    assert brief["topic"] == "semantic recall planning"
    assert brief["memory_hits"]
    assert Path(brief["report_path"]).parts[:2] == ("runtime", "reports")
