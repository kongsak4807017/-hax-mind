import json

from engine.github_ingestor import extract_headings, ingest_tool, summarize_tool_readme
from engine.tool_registry import get_tool


def test_extract_headings():
    assert extract_headings("# Title\n\n## Features\n\n### Install") == ["Title", "Features", "Install"]


def test_summarize_tool_readme_detects_capabilities():
    tool = get_tool("crawl4ai")
    record = summarize_tool_readme(tool, "# Crawl4AI\n\nWeb crawler that generates Markdown for scraper workflows.")
    assert record["tool_id"] == "crawl4ai"
    assert "Markdown extraction / generation" in record["capabilities"]
    assert "Web crawling" in record["capabilities"]


def test_ingest_tool_writes_canonical_record(tmp_path):
    tool = get_tool("docmd")
    record = ingest_tool(
        tool,
        readme_text="# docmd\n\nGenerates static HTML and llms.txt for documentation search.",
        fetched_url="test://docmd",
        root=tmp_path,
    )
    canonical = tmp_path / "memory" / "canonical" / "tools" / "docmd.json"
    raw = tmp_path / "memory" / "raw_sources" / "tool_repos" / "docmd_README.md"
    assert canonical.exists()
    assert raw.exists()
    payload = json.loads(canonical.read_text(encoding="utf-8"))
    assert payload["tool_id"] == record["tool_id"] == "docmd"
    assert payload["source_url"] == "test://docmd"
