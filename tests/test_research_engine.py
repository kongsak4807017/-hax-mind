from pathlib import Path

from engine.openrouter_client import OpenRouterError
from engine.project_manager import register_project
from engine.research_engine import _is_news_query, build_news_api_request
from engine.research_engine import (
    approve_research_proposal,
    close_research_session,
    create_proposal_from_research,
    create_task_from_research,
    latest_research,
    latest_research_session,
    render_research_artifact,
    render_research_output,
    render_research_reply,
    render_research_session_detail,
    render_research_sessions_summary,
    run_research,
    start_research_session,
    continue_research_session,
)


def test_run_research_saves_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.research_engine.brave_web_search",
        lambda query, count=5: {
            "web": {
                "results": [
                    {"title": "Example One", "url": "https://example.com/1", "description": "First result"},
                    {"title": "Example Two", "url": "https://example.com/2", "description": "Second result"},
                ]
            }
        },
    )
    monkeypatch.setattr("engine.research_engine.fetch_page_text", lambda url: f"Content from {url}")
    monkeypatch.setattr(
        "engine.research_engine._summarize_research",
        lambda query, results, fetched_pages: {
            "summary": "This is a summary.",
            "key_points": ["Point A", "Point B"],
            "caveats": ["Caveat"],
            "recommended_next_step": "Investigate further.",
        },
    )

    record = run_research("test query", root=tmp_path)

    assert record["query"] == "test query"
    assert len(record["results"]) == 2
    assert (tmp_path / "memory" / "canonical" / "research" / f"{record['id']}.json").exists()
    assert "Sources:" in render_research_reply(record)
    assert render_research_output(record) == "This is a summary."
    assert "Research artifact:" in render_research_artifact(record, root=tmp_path)


def test_news_queries_use_newsapi(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("engine.research_engine._news_api_key", lambda: "news-key")
    monkeypatch.setattr("engine.research_engine._brave_api_key", lambda: "")
    monkeypatch.setattr(
        "engine.research_engine.news_api_search",
        lambda query, count=5: {
            "articles": [
                {
                    "title": "Global Story",
                    "url": "https://example.com/news",
                    "description": "News body",
                    "publishedAt": "2026-04-13T00:00:00Z",
                    "source": {"name": "Example News"},
                }
            ]
        },
    )
    monkeypatch.setattr("engine.research_engine.fetch_page_text", lambda url: "Fetched news content")
    monkeypatch.setattr(
        "engine.research_engine._summarize_research",
        lambda query, results, fetched_pages: {
            "summary": "News summary.",
            "key_points": ["News point"],
            "caveats": [],
            "recommended_next_step": "Track updates.",
        },
    )

    record = run_research("latest news about AI", root=tmp_path)

    assert _is_news_query("latest news about AI") is True
    assert record["provider"] == "newsapi"
    assert record["provider_mode"] == "top_headlines"
    assert record["results"][0]["source_name"] == "Example News"


def test_build_news_api_request_supports_country_and_category_modes() -> None:
    request_data = build_news_api_request("top technology headlines in thailand", count=7)

    assert request_data["mode"] == "top_headlines"
    assert request_data["params"]["country"] == "th"
    assert request_data["params"]["category"] == "technology"
    assert request_data["params"]["pageSize"] == 7


def test_run_research_falls_back_without_openrouter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.research_engine.brave_web_search",
        lambda query, count=5: {
            "web": {
                "results": [
                    {"title": "Example One", "url": "https://example.com/1", "description": "First result"},
                    {"title": "Example Two", "url": "https://example.com/2", "description": "Second result"},
                ]
            }
        },
    )
    monkeypatch.setattr("engine.research_engine.fetch_page_text", lambda url: "")
    monkeypatch.setattr(
        "engine.research_engine.chat_completion",
        lambda **kwargs: (_ for _ in ()).throw(OpenRouterError("OPENROUTER_API_KEY is not configured.")),
    )

    record = run_research("search web for agentic coding tools", root=tmp_path)

    assert record["summary"]["summary_provider"] == "local_fallback"
    assert "OpenRouter unavailable" in record["summary"]["caveats"][0]
    assert record["summary"]["summary"]


def test_research_latest_task_proposal_and_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.research_engine.brave_web_search",
        lambda query, count=5: {
            "web": {
                "results": [
                    {"title": "Example One", "url": "https://example.com/1", "description": "First result"},
                ]
            }
        },
    )
    monkeypatch.setattr("engine.research_engine.fetch_page_text", lambda url: f"Content from {url}")
    monkeypatch.setattr(
        "engine.research_engine._summarize_research",
        lambda query, results, fetched_pages: {
            "summary": "This is a summary.",
            "key_points": ["Point A"],
            "caveats": [],
            "recommended_next_step": "Turn this into a task.",
        },
    )

    register_project("HAXMind", str(tmp_path), root=tmp_path)
    session, first = start_research_session("first query", root=tmp_path)
    second = continue_research_session(session["id"], "second query", root=tmp_path)
    latest = latest_research(root=tmp_path)
    mission = create_task_from_research(project_id="haxmind", root=tmp_path)
    proposal = create_proposal_from_research(root=tmp_path)
    approved = approve_research_proposal(root=tmp_path)
    session_state = latest_research_session(root=tmp_path)
    closed = close_research_session(session["id"], root=tmp_path)

    assert first["query"] == "first query"
    assert second["query"] == "second query"
    assert latest["id"] == second["id"]
    assert mission["source_research_id"] == latest["id"]
    assert proposal["metadata"]["research_id"] == latest["id"]
    assert approved["status"] == "approved"
    assert "Research session:" in render_research_session_detail(session_state)
    assert session["id"] in render_research_sessions_summary(root=tmp_path)
    assert closed["status"] == "closed"
