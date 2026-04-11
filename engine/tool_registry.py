from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    repo: str
    url: str
    default_branch: str
    raw_readme_url: str
    role: str
    memory_use: str
    integration_phase: int
    install_hint: str
    safety_note: str


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        id="crawl4ai",
        name="Crawl4AI",
        repo="kongsak4807017/crawl4ai",
        url="https://github.com/kongsak4807017/crawl4ai",
        default_branch="main",
        raw_readme_url="https://raw.githubusercontent.com/kongsak4807017/crawl4ai/main/README.md",
        role="web_to_markdown_ingestion",
        memory_use="Turn web pages and documentation into clean, LLM-ready Markdown for HAX-Mind memory and future RAG.",
        integration_phase=2,
        install_hint="pip install -U crawl4ai && crawl4ai-setup",
        safety_note="Use domain/page limits and avoid crawling private or credentialed pages without explicit approval.",
    ),
    ToolSpec(
        id="reverse_engineer",
        name="Reverse-Engineer",
        repo="kongsak4807017/Reverse-Engineer",
        url="https://github.com/kongsak4807017/Reverse-Engineer",
        default_branch="main",
        raw_readme_url="https://raw.githubusercontent.com/kongsak4807017/Reverse-Engineer/main/README.md",
        role="blueprint_analysis",
        memory_use="Analyze GitHub repos, local paths, and live websites into technical blueprints for rebuild or extension work.",
        integration_phase=2,
        install_hint="npm install && npm start, or npx blueprompt where applicable",
        safety_note="Treat generated blueprints as hypotheses until verified against files and tests.",
    ),
    ToolSpec(
        id="docmd",
        name="docmd",
        repo="kongsak4807017/docmd",
        url="https://github.com/kongsak4807017/docmd",
        default_branch="main",
        raw_readme_url="https://raw.githubusercontent.com/kongsak4807017/docmd/main/README.md",
        role="documentation_context",
        memory_use="Generate documentation sites and AI context files such as llms.txt from Markdown knowledge.",
        integration_phase=2,
        install_hint="npx @docmd/core dev -z or npx @docmd/core build -z",
        safety_note="Generated static docs are safe; do not publish externally until reviewed.",
    ),
    ToolSpec(
        id="rtk",
        name="RTK",
        repo="kongsak4807017/rtk",
        url="https://github.com/kongsak4807017/rtk",
        default_branch="master",
        raw_readme_url="https://raw.githubusercontent.com/kongsak4807017/rtk/master/README.md",
        role="token_compression",
        memory_use="Compress command, git, test, log, and shell output before it enters AI context.",
        integration_phase=1,
        install_hint="Download Windows prebuilt or cargo install --git https://github.com/rtk-ai/rtk, then rtk init -g --codex",
        safety_note="Do not enable global command rewriting until basic HAX-Mind tests pass.",
    ),
)


def iter_tools() -> Iterable[ToolSpec]:
    return iter(TOOL_SPECS)


def get_tool(tool_id: str) -> ToolSpec:
    normalized = tool_id.strip().lower().replace("-", "_")
    aliases = {
        "reverse_engineer": "reverse_engineer",
        "reverseengineer": "reverse_engineer",
        "crawl4ai": "crawl4ai",
        "docmd": "docmd",
        "rtk": "rtk",
    }
    normalized = aliases.get(normalized, normalized)
    for tool in TOOL_SPECS:
        if tool.id == normalized:
            return tool
    raise KeyError(f"Unknown tool: {tool_id}")


def tool_cards() -> list[dict]:
    return [asdict(tool) for tool in TOOL_SPECS]
