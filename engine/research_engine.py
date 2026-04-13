from __future__ import annotations

import html
import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import parse, request, error

from engine.memory_store import append_raw_log, initialize_memory_dirs, write_json, write_text
from engine.openrouter_client import OpenRouterError, chat_completion, extract_message_text
from engine.mission_engine import create_mission
from engine.proposal_engine import create_proposal
from engine.utils import ROOT, now_iso


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
NEWS_API_EVERYTHING_URL = "https://newsapi.org/v2/everything"
NEWS_API_TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"
MAX_FETCH_PAGES = 3
RESEARCH_SESSIONS_DIR = ROOT / "runtime" / "research_sessions"

NEWS_CATEGORY_ALIASES = {
    "business": ("business", "finance", "financial", "ตลาดหุ้น", "เศรษฐกิจ"),
    "entertainment": ("entertainment", "movies", "movie", "music", "celebrity", "บันเทิง"),
    "general": ("general", "general news", "ข่าวทั่วไป"),
    "health": ("health", "healthcare", "medical", "medicine", "สาธารณสุข", "สุขภาพ"),
    "science": ("science", "research", "scientific", "วิทยาศาสตร์"),
    "sports": ("sports", "sport", "football", "soccer", "nba", "nfl", "กีฬา"),
    "technology": ("technology", "tech", "ai", "startup", "software", "เทคโนโลยี"),
}

NEWS_COUNTRY_ALIASES = {
    "us": ("us", "usa", "u.s.", "united states", "america"),
    "gb": ("uk", "u.k.", "britain", "great britain", "united kingdom", "england"),
    "th": ("thailand", "thai", "ประเทศไทย", "ไทย"),
    "jp": ("japan", "ญี่ปุ่น"),
    "sg": ("singapore", "สิงคโปร์"),
    "au": ("australia", "ออสเตรเลีย"),
    "ca": ("canada", "แคนาดา"),
    "de": ("germany", "เยอรมนี"),
    "fr": ("france", "ฝรั่งเศส"),
    "in": ("india", "อินเดีย"),
}

NEWS_HEADLINE_HINTS = (
    "headline",
    "headlines",
    "top headlines",
    "breaking",
    "breaking news",
    "latest news",
    "ข่าวล่าสุด",
    "ข่าวด่วน",
)

LOCAL_SUMMARY_STOPWORDS = {
    "a",
    "about",
    "after",
    "and",
    "are",
    "around",
    "been",
    "for",
    "from",
    "have",
    "into",
    "latest",
    "more",
    "news",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "this",
    "with",
    "world",
}


class ResearchError(RuntimeError):
    pass


def _brave_api_key() -> str:
    import os
    from engine.utils import read_env_file

    read_env_file()
    return os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()


def _news_api_key() -> str:
    import os
    from engine.utils import read_env_file

    read_env_file()
    return os.environ.get("NEWS_API", "").strip() or os.environ.get("NEWS_API_KEY", "").strip()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    return cleaned[:60] or "research"


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_alias(lowered_query: str, aliases: tuple[str, ...]) -> bool:
    return any(alias in lowered_query for alias in aliases)


def _extract_news_category(lowered_query: str) -> str | None:
    for category, aliases in NEWS_CATEGORY_ALIASES.items():
        if _contains_alias(lowered_query, aliases):
            return category
    return None


def _extract_news_country(lowered_query: str) -> str | None:
    for country, aliases in NEWS_COUNTRY_ALIASES.items():
        if _contains_alias(lowered_query, aliases):
            return country
    return None


def _clean_news_query(query: str) -> str:
    cleaned = query.lower()
    removable_phrases = [
        *NEWS_HEADLINE_HINTS,
        "news about",
        "news on",
        "search news for",
        "search web for",
        "world news",
        "ข่าว",
        "ค้นหา",
        "ค้นเว็บ",
        "หาข้อมูล",
    ]
    for aliases in NEWS_CATEGORY_ALIASES.values():
        removable_phrases.extend(aliases)
    for aliases in NEWS_COUNTRY_ALIASES.values():
        removable_phrases.extend(aliases)
    for phrase in sorted(set(removable_phrases), key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned)
    cleaned = re.sub(r"\b(in|for|from|about|on)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,:")
    return cleaned


def build_news_api_request(query: str, *, count: int = 5) -> dict[str, Any]:
    lowered = query.lower().strip()
    category = _extract_news_category(lowered)
    country = _extract_news_country(lowered)
    cleaned_query = _clean_news_query(query)
    wants_top_headlines = bool(category or country or any(hint in lowered for hint in NEWS_HEADLINE_HINTS))
    mode = "top_headlines" if wants_top_headlines else "everything"

    if mode == "top_headlines":
        params: dict[str, Any] = {"pageSize": count}
        if cleaned_query:
            params["q"] = cleaned_query
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        return {
            "endpoint": NEWS_API_TOP_HEADLINES_URL,
            "params": params,
            "mode": mode,
            "country": country,
            "category": category,
            "normalized_query": cleaned_query or query.strip(),
        }

    return {
        "endpoint": NEWS_API_EVERYTHING_URL,
        "params": {
            "q": cleaned_query or query.strip(),
            "pageSize": count,
            "sortBy": "publishedAt",
            "searchIn": "title,description,content",
        },
        "mode": mode,
        "country": country,
        "category": category,
        "normalized_query": cleaned_query or query.strip(),
    }


def _research_path(research_id: str, root: Path = ROOT) -> Path:
    return root / "memory" / "canonical" / "research" / f"{research_id}.json"


def _session_path(session_id: str, root: Path = ROOT) -> Path:
    return root / "runtime" / "research_sessions" / f"{session_id}.json"


def brave_web_search(query: str, *, count: int = 5, timeout: int = 30) -> dict[str, Any]:
    api_key = _brave_api_key()
    if not api_key:
        raise ResearchError("BRAVE_SEARCH_API_KEY is not configured.")
    params = parse.urlencode({"q": query, "count": count})
    req = request.Request(
        f"{BRAVE_SEARCH_URL}?{params}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "HAX-Mind/0.2 research-engine",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ResearchError(f"Brave Search HTTP {exc.code}: {body[:500]}") from exc
    except error.URLError as exc:
        raise ResearchError(f"Brave Search request failed: {exc.reason}") from exc


def news_api_search(query: str, *, count: int = 5, timeout: int = 30) -> dict[str, Any]:
    api_key = _news_api_key()
    if not api_key:
        raise ResearchError("NEWS_API is not configured.")
    news_request = build_news_api_request(query, count=count)
    params = parse.urlencode(news_request["params"])
    req = request.Request(
        f"{news_request['endpoint']}?{params}",
        headers={
            "Accept": "application/json",
            "X-Api-Key": api_key,
            "User-Agent": "HAX-Mind/0.2 research-engine",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            payload["_request"] = news_request
            return payload
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ResearchError(f"NewsAPI HTTP {exc.code}: {body[:500]}") from exc
    except error.URLError as exc:
        raise ResearchError(f"NewsAPI request failed: {exc.reason}") from exc


def _is_news_query(query: str) -> bool:
    lowered = query.lower()
    keywords = [
        "news",
        "latest news",
        "headlines",
        "breaking",
        "ข่าว",
        "ข่าวล่าสุด",
        "ข่าวด่วน",
        "ทั่วโลก",
        "world news",
    ]
    return any(keyword in lowered for keyword in keywords)


def fetch_page_text(url: str, *, timeout: int = 20) -> str:
    req = request.Request(url, headers={"User-Agent": "HAX-Mind/0.2 research-engine"})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return _strip_html(raw)


def _local_summary_themes(results: list[dict[str, Any]]) -> list[str]:
    tokens: list[str] = []
    for item in results[:5]:
        text = f"{item.get('title', '')} {item.get('description', '')}".lower()
        for token in re.findall(r"[a-z]{3,}", text):
            if token not in LOCAL_SUMMARY_STOPWORDS:
                tokens.append(token)
    counts = Counter(tokens)
    return [token for token, _ in counts.most_common(4)]


def _local_summarize_research(
    query: str,
    results: list[dict[str, Any]],
    fetched_pages: list[dict[str, Any]],
    *,
    fallback_reason: str,
) -> dict[str, Any]:
    source_count = len(results)
    if not results:
        return {
            "summary": f"No external results were found for '{query}'.",
            "key_points": [],
            "caveats": [fallback_reason, "No external sources were available to summarize."],
            "recommended_next_step": "Try a more specific query or broaden the timeframe.",
            "summary_provider": "local_fallback",
        }

    themes = _local_summary_themes(results)
    theme_text = f" Main themes: {', '.join(themes)}." if themes else ""
    key_points: list[str] = []
    for item in results[:3]:
        title = item.get("title", "").strip()
        description = item.get("description", "").strip()
        source_name = item.get("source_name", "").strip()
        detail = f"{title}"
        if source_name:
            detail = f"{detail} ({source_name})"
        if description:
            detail = f"{detail}: {description}"
        key_points.append(detail)

    caveats = [fallback_reason]
    if not fetched_pages:
        caveats.append("No page text could be fetched, so the summary is based on search snippets only.")
    elif len(fetched_pages) < min(source_count, MAX_FETCH_PAGES):
        caveats.append("Some source pages could not be fetched, so the summary may miss detail from those links.")

    return {
        "summary": f"Found {source_count} relevant source(s) for '{query}'.{theme_text}".strip(),
        "key_points": key_points,
        "caveats": caveats,
        "recommended_next_step": "Review the linked sources and decide whether to turn the findings into a task or proposal.",
        "summary_provider": "local_fallback",
    }


def _summarize_research(query: str, results: list[dict[str, Any]], fetched_pages: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "query": query,
        "results": [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            }
            for item in results
        ],
        "pages": [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            }
            for item in fetched_pages
        ],
    }
    try:
        response = chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarize research results. Return valid JSON with keys: "
                        '{"summary": string, "key_points": string[], "caveats": string[], "recommended_next_step": string}. '
                        "Be concise and evidence-aware."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.1,
        )
        text = extract_message_text(response)
        data = json.loads(text)
    except OpenRouterError as exc:
        return _local_summarize_research(query, results, fetched_pages, fallback_reason=f"OpenRouter unavailable: {exc}")
    except json.JSONDecodeError:
        return _local_summarize_research(
            query,
            results,
            fetched_pages,
            fallback_reason="OpenRouter returned invalid JSON, so HAX-Mind used local summarization instead.",
        )
    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_points": [str(item).strip() for item in data.get("key_points", []) if str(item).strip()],
        "caveats": [str(item).strip() for item in data.get("caveats", []) if str(item).strip()],
        "recommended_next_step": str(data.get("recommended_next_step", "")).strip(),
        "summary_provider": "openrouter",
    }


def run_research(query: str, *, root: Path = ROOT, count: int = 5) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ResearchError("Research query is required.")
    initialize_memory_dirs(root)
    provider = "brave_search"
    provider_mode = "web_search"
    if _is_news_query(query) and _news_api_key():
        provider = "newsapi"
        response = news_api_search(query, count=count)
        provider_mode = ((response.get("_request") or {}).get("mode")) or build_news_api_request(query, count=count)["mode"]
        raw_results = response.get("articles") or []
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", "") or item.get("content", ""),
                "age": item.get("publishedAt"),
                "language": None,
                "source_name": (item.get("source") or {}).get("name"),
            }
            for item in raw_results[:count]
        ]
    else:
        response = brave_web_search(query, count=count)
        raw_results = ((response.get("web") or {}).get("results") or [])[:count]
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "age": item.get("age"),
                "language": item.get("language"),
            }
            for item in raw_results
        ]
    fetched_pages = []
    for item in results[:MAX_FETCH_PAGES]:
        content = fetch_page_text(item["url"])
        if content:
            fetched_pages.append({"title": item["title"], "url": item["url"], "content": content})
    summary = _summarize_research(query, results, fetched_pages)

    research_id = f"research_{now_iso()[:10].replace('-', '')}_{uuid.uuid4().hex[:8]}"
    record = {
        "id": research_id,
        "type": "web_research",
        "query": query,
        "created_at": now_iso(),
        "provider": provider,
        "provider_mode": provider_mode,
        "results": results,
        "fetched_pages": [{"title": item["title"], "url": item["url"]} for item in fetched_pages],
        "summary": summary,
    }
    canonical_path = root / "memory" / "canonical" / "research" / f"{research_id}.json"
    report_path = root / "runtime" / "reports" / f"{research_id}.md"
    write_json(canonical_path, record)
    write_text(report_path, render_research_report(record))
    append_raw_log("research", f"Research completed for query: {query}", topic="research", importance="high", root=root)
    return record


def get_research(research_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    path = _research_path(research_id, root=root)
    if not path.exists():
        raise FileNotFoundError(f"Research record not found: {research_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_research(*, root: Path = ROOT, limit: int = 20) -> list[dict[str, Any]]:
    directory = root / "memory" / "canonical" / "research"
    directory.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("research_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return items


def latest_research(*, root: Path = ROOT) -> dict[str, Any] | None:
    items = list_research(root=root, limit=1)
    return items[0] if items else None


def create_task_from_research(*, project_id: str, research_id: str | None = None, root: Path = ROOT) -> dict[str, Any]:
    record = get_research(research_id, root=root) if research_id and research_id != "latest" else latest_research(root=root)
    if not record:
        raise FileNotFoundError("No research record exists yet.")
    summary = record["summary"]
    description = (
        f"Research follow-up from {record['id']} for query '{record['query']}'.\n"
        f"Summary: {summary.get('summary', '')}\n"
        "Key points:\n"
        + "\n".join(f"- {item}" for item in summary.get("key_points", [])[:4])
        + f"\nRecommended next step: {summary.get('recommended_next_step', 'Review the research sources and decide the next action.')}"
    )
    mission = create_mission(project_id, description, root=root)
    mission["source_research_id"] = record["id"]
    return mission


def create_proposal_from_research(*, research_id: str | None = None, root: Path = ROOT) -> dict[str, Any]:
    record = get_research(research_id, root=root) if research_id and research_id != "latest" else latest_research(root=root)
    if not record:
        raise FileNotFoundError("No research record exists yet.")
    summary = record["summary"]
    return create_proposal(
        title=f"Act on research: {record['query'][:80]}",
        component="research",
        problem=f"Research query needs a concrete follow-up: {record['query']}",
        root_cause="The operator requested external research and now needs a tracked follow-up action.",
        solution=summary.get("recommended_next_step") or "Review the research sources and create a concrete implementation or decision path.",
        expected_impact="Turns external research into a tracked proposal that can be reviewed and executed later.",
        risk="low",
        files_to_modify=[],
        tests_to_run=[],
        rollback_plan="Reject or archive the proposal if the research conclusion changes.",
        metadata={"research_id": record["id"], "sources": [item["url"] for item in record.get("results", [])[:5]]},
        root=root,
    )


def _save_session(record: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _session_path(record["id"], root=root).parent.mkdir(parents=True, exist_ok=True)
    _session_path(record["id"], root=root).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def get_research_session(session_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    path = _session_path(session_id, root=root)
    if not path.exists():
        raise FileNotFoundError(f"Research session not found: {session_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_research_sessions(*, root: Path = ROOT, limit: int = 20) -> list[dict[str, Any]]:
    directory = root / "runtime" / "research_sessions"
    directory.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("research_session_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return items


def latest_research_session(*, root: Path = ROOT) -> dict[str, Any] | None:
    items = list_research_sessions(root=root, limit=1)
    return items[0] if items else None


def start_research_session(query: str, *, root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    session = {
        "id": f"research_session_{now_iso()[:10].replace('-', '')}_{uuid.uuid4().hex[:8]}",
        "created_at": now_iso(),
        "status": "open",
        "step_count": 0,
        "history": [],
        "last_research_id": None,
    }
    _save_session(session, root=root)
    record = continue_research_session(session["id"], query, root=root)
    return get_research_session(session["id"], root=root), record


def continue_research_session(session_ref: str, query: str, *, root: Path = ROOT) -> dict[str, Any]:
    session = latest_research_session(root=root) if session_ref == "latest" else get_research_session(session_ref, root=root)
    if not session:
        raise FileNotFoundError("No research session exists yet.")
    record = run_research(query, root=root)
    session["step_count"] = int(session.get("step_count", 0)) + 1
    session["last_research_id"] = record["id"]
    session.setdefault("history", []).append({"step": session["step_count"], "query": query, "research_id": record["id"]})
    _save_session(session, root=root)
    return record


def close_research_session(session_ref: str, *, root: Path = ROOT) -> dict[str, Any]:
    session = latest_research_session(root=root) if session_ref == "latest" else get_research_session(session_ref, root=root)
    if not session:
        raise FileNotFoundError("No research session exists yet.")
    session["status"] = "closed"
    session["closed_at"] = now_iso()
    _save_session(session, root=root)
    return session


def render_research_session_detail(session: dict[str, Any]) -> str:
    lines = [
        f"Research session: {session['id']}",
        f"Status: {session.get('status', 'open')}",
        f"Step count: {session.get('step_count', 0)}",
        f"Created at: {session.get('created_at', '-')}",
        f"Last research: {session.get('last_research_id', '-')}",
    ]
    history = session.get("history", [])
    if history:
        lines.append("Recent queries:")
        for item in history[-3:]:
            lines.append(f"- [{item['step']}] {item['query'][:120]}")
    return "\n".join(lines)


def render_research_sessions_summary(*, root: Path = ROOT, limit: int = 10) -> str:
    sessions = list_research_sessions(root=root, limit=limit)
    if not sessions:
        return "No research sessions yet."
    return "\n".join(
        f"{session['id']} | steps={session.get('step_count', 0)} | status={session.get('status', 'open')}"
        for session in sessions
    )


def render_research_report(record: dict[str, Any]) -> str:
    key_points = [f"- {item}" for item in record["summary"].get("key_points", [])] or ["- No key points."]
    caveats = [f"- {item}" for item in record["summary"].get("caveats", [])] or ["- No caveats."]
    sources = [f"- {item['title']} — {item['url']}" for item in record.get("results", [])] or ["- No sources."]
    lines = [
        f"# Research: {record['query']}",
        "",
        f"- ID: {record['id']}",
        f"- Created: {record['created_at']}",
        f"- Provider: {record['provider']}",
        f"- Provider mode: {record.get('provider_mode', '-')}",
        f"- Summary provider: {record['summary'].get('summary_provider', '-')}",
        "",
        "## Summary",
        record["summary"].get("summary", "No summary."),
        "",
        "## Key points",
        *key_points,
        "",
        "## Caveats",
        *caveats,
        "",
        f"## Recommended next step\n- {record['summary'].get('recommended_next_step', 'None')}",
        "",
        "## Sources",
        *sources,
        "",
    ]
    return "\n".join(lines)


def render_research_reply(record: dict[str, Any]) -> str:
    sources = record.get("results", [])[:5]
    lines = [
        f"Research: {record['query']}",
        record["summary"].get("summary", "No summary."),
    ]
    if record["summary"].get("summary_provider") == "local_fallback":
        lines.append("Summary mode: local fallback")
    if record["summary"].get("key_points"):
        lines.append("Key points:")
        lines.extend(f"- {item}" for item in record["summary"]["key_points"][:4])
    if record["summary"].get("recommended_next_step"):
        lines.append(f"Next step: {record['summary']['recommended_next_step']}")
    if sources:
        lines.append("Sources:")
        lines.extend(f"- {item['title']} — {item['url']}" for item in sources)
    return "\n".join(lines)


def render_research_output(record: dict[str, Any]) -> str:
    return record["summary"].get("summary", "No summary.")


def render_research_artifact(record: dict[str, Any], *, root: Path = ROOT) -> str:
    report_path = root / "runtime" / "reports" / f"{record['id']}.md"
    return "\n".join(
        [
            f"Research artifact: {record['id']}",
            f"Canonical JSON: {str(_research_path(record['id'], root=root).relative_to(root))}",
            f"Report: {str(report_path.relative_to(root))}",
            f"Sources captured: {len(record.get('results', []))}",
            f"Summary provider: {record['summary'].get('summary_provider', '-')}",
        ]
    )


def approve_research_proposal(*, research_id: str | None = None, root: Path = ROOT) -> dict[str, Any]:
    from engine.proposal_engine import update_proposal_status

    proposal = create_proposal_from_research(research_id=research_id, root=root)
    return update_proposal_status(proposal["id"], "approved", root=root)
