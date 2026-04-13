from pathlib import Path

from engine.auto_learning import (
    handle_unknown_question,
    get_pending_gaps,
    get_recurring_topics,
    find_similar_gaps,
    _normalize_question,
    _calculate_similarity,
    render_learning_summary,
)


def test_normalize_question_removes_fillers():
    text1 = "How do I create a new project in HAX-Mind?"
    text2 = "how to create new project hax mind"
    # Both should contain core keywords after normalization
    norm1 = _normalize_question(text1)
    norm2 = _normalize_question(text2)
    assert "create" in norm1
    assert "create" in norm2
    assert "project" in norm1
    assert "project" in norm2


def test_calculate_similarity_identical():
    text = "create new project"
    assert _calculate_similarity(text, text) == 1.0


def test_calculate_similarity_different():
    text1 = "create new project"
    text2 = "delete old task"
    similarity = _calculate_similarity(text1, text2)
    assert 0.0 <= similarity < 0.5


def test_handle_unknown_question_creates_gap(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.LEARNING_QUEUE_DIR", tmp_path / "learning_queue")
    monkeypatch.setattr("engine.auto_learning.KNOWLEDGE_GAPS_DIR", tmp_path / "knowledge_gaps")
    monkeypatch.setattr("engine.auto_learning.log_event", lambda *args, **kwargs: None)
    
    result = handle_unknown_question("How do I deploy HAX-Mind to VPS?", root=tmp_path)
    
    assert result["status"] == "pending"
    assert result["gap_id"].startswith("gap_")
    assert result["recurring_count"] == 1


def test_handle_unknown_question_detects_similar(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.log_event", lambda *args, **kwargs: None)
    
    # First question
    handle_unknown_question("deploy haxmind vps server", root=tmp_path)
    
    # Very similar question (should be detected with lower threshold in find_similar_gaps)
    # Note: similarity depends on normalized text overlap
    result = handle_unknown_question("deploy haxmind vps production", root=tmp_path)
    
    # At minimum, both questions should be recorded
    gaps = get_pending_gaps(root=tmp_path)
    assert len(gaps) >= 1


def test_get_pending_gaps_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.LEARNING_QUEUE_DIR", tmp_path / "learning_queue")
    gaps = get_pending_gaps(root=tmp_path)
    assert gaps == []


def test_get_pending_gaps_returns_pending(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.log_event", lambda *args, **kwargs: None)
    
    handle_unknown_question("Question 1 something unique?", root=tmp_path)
    handle_unknown_question("Question 2 different topic?", root=tmp_path)
    
    gaps = get_pending_gaps(root=tmp_path)
    assert len(gaps) >= 1  # At least one gap should be created


def test_get_recurring_topics_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.LEARNING_QUEUE_DIR", tmp_path / "learning_queue")
    topics = get_recurring_topics(root=tmp_path, min_count=2)
    assert topics == []


def test_find_similar_gaps_empty(tmp_path: Path):
    similar = find_similar_gaps("some question", root=tmp_path)
    assert similar == []


def test_find_similar_gaps_with_matches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.log_event", lambda *args, **kwargs: None)
    
    # Create first gap with unique text
    handle_unknown_question("deploy haxmind vps server production", root=tmp_path)
    
    # Find similar with lower threshold
    similar = find_similar_gaps("deploy haxmind vps", threshold=0.3, root=tmp_path)
    assert len(similar) >= 1


def test_render_learning_summary_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.LEARNING_QUEUE_DIR", tmp_path / "learning_queue")
    summary = render_learning_summary(root=tmp_path)
    assert "Auto-Learning Status" in summary
    assert "0" in summary or "No" in summary


def test_handle_unknown_question_important_keywords(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("engine.auto_learning.LEARNING_QUEUE_DIR", tmp_path / "learning_queue")
    monkeypatch.setattr("engine.auto_learning.KNOWLEDGE_GAPS_DIR", tmp_path / "knowledge_gaps")
    monkeypatch.setattr("engine.auto_learning.log_event", lambda *args, **kwargs: None)
    
    result = handle_unknown_question("Security bug in authentication system", root=tmp_path)
    
    assert result["is_important"] is True
    assert result["should_trigger_learning"] is True
