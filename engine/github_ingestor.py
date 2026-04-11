from __future__ import annotations

import re
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from engine.memory_store import append_raw_log, initialize_memory_dirs, write_json, write_text
from engine.tool_registry import ToolSpec, iter_tools
from engine.utils import ROOT, now_iso

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def fetch_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "HAX-Mind/0.1 tool-memory-ingestor"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_headings(markdown: str, limit: int = 20) -> list[str]:
    headings = []
    for match in _HEADING_RE.finditer(markdown):
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        title = title.replace("`", "")
        if title and title not in headings:
            headings.append(title)
        if len(headings) >= limit:
            break
    return headings


def first_nonempty_line(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip(" #\t")
        if line and not line.startswith("!") and len(line) > 3:
            return line[:180]
    return fallback


def infer_capabilities(tool: ToolSpec, markdown: str) -> list[str]:
    text = markdown.lower()
    capabilities: list[str] = []
    keyword_map = {
        "markdown": "Markdown extraction / generation",
        "crawler": "Web crawling",
        "scraper": "Web scraping",
        "blueprint": "Technical blueprint generation",
        "github": "GitHub repository analysis",
        "local path": "Local codebase analysis",
        "playwright": "Browser automation",
        "llms.txt": "AI context file generation",
        "static html": "Static documentation build",
        "token": "Token reduction",
        "git status": "Compact git command output",
        "pytest": "Compact test output",
        "search": "Search / retrieval support",
    }
    for keyword, capability in keyword_map.items():
        if keyword in text and capability not in capabilities:
            capabilities.append(capability)
    if not capabilities:
        capabilities.append(tool.role.replace("_", " ").title())
    return capabilities[:8]


def summarize_tool_readme(tool: ToolSpec, markdown: str) -> dict:
    return {
        "tool_id": tool.id,
        "name": tool.name,
        "repo": tool.repo,
        "url": tool.url,
        "role": tool.role,
        "memory_use": tool.memory_use,
        "integration_phase": tool.integration_phase,
        "install_hint": tool.install_hint,
        "safety_note": tool.safety_note,
        "readme_title": first_nonempty_line(markdown, tool.name),
        "headings": extract_headings(markdown),
        "capabilities": infer_capabilities(tool, markdown),
        "source_bytes": len(markdown.encode("utf-8")),
        "ingested_at": now_iso(),
    }


def render_topic_summary(records: Iterable[dict]) -> str:
    lines = ["# Tool Memory Summary", "", f"Updated: {now_iso()}", ""]
    for record in records:
        lines.extend(
            [
                f"## {record['name']}",
                f"- Repo: {record['url']}",
                f"- Role: {record['role']}",
                f"- Memory use: {record['memory_use']}",
                f"- Capabilities: {', '.join(record['capabilities'])}",
                f"- Safety: {record['safety_note']}",
                "",
            ]
        )
    return "\n".join(lines)


def ingest_tool(tool: ToolSpec, readme_text: str | None = None, fetched_url: str | None = None, root: Path = ROOT) -> dict:
    initialize_memory_dirs(root)
    readme = readme_text if readme_text is not None else fetch_text(tool.raw_readme_url)
    source_url = fetched_url or tool.raw_readme_url
    raw_path = root / "memory" / "raw_sources" / "tool_repos" / f"{tool.id}_README.md"
    canonical_path = root / "memory" / "canonical" / "tools" / f"{tool.id}.json"

    write_text(raw_path, readme)
    record = summarize_tool_readme(tool, readme)
    record["source_url"] = source_url
    record["raw_snapshot"] = str(raw_path.relative_to(root))
    write_json(canonical_path, record)
    append_raw_log("tool_ingested", f"Ingested {tool.name} from {source_url}", topic="tools", importance="high", root=root)
    return record


def ingest_all_tools(root: Path = ROOT) -> list[dict]:
    records = [ingest_tool(tool, root=root) for tool in iter_tools()]
    summary = render_topic_summary(records)
    write_text(root / "memory" / "topic_summaries" / "tools.md", summary)
    state_path = root / "state" / "system_state.json"
    if state_path.exists():
        import json

        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {"system_name": "HAX-Mind", "version": "0.1.0", "mode": "safe"}
    state["last_tool_ingestion"] = now_iso()
    write_json(state_path, state)
    return records


def tool_specs_as_records() -> list[dict]:
    return [asdict(tool) for tool in iter_tools()]
