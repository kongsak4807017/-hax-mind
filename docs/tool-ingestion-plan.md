# Tool ingestion plan

HAX-Mind uses external repositories as tool knowledge. The first implementation does **not** vendor their full source. It stores repo metadata and README-derived canonical records so the agent can reason about which tool to use for a mission.

## Pipeline

1. Read tool definitions from `engine/tool_registry.py`.
2. Fetch each README from GitHub raw URLs.
3. Store raw README snapshots under `memory/raw_sources/tool_repos/`.
4. Extract headings and heuristic capability summaries.
5. Write canonical tool cards under `memory/canonical/tools/`.
6. Write a topic summary to `memory/topic_summaries/tools.md`.
7. Include the tool digest in morning reports.

## Tool roles

- `crawl4ai`: web-to-markdown and browser-backed extraction for memory/RAG.
- `Reverse-Engineer`: repo/local/live website analysis into technical blueprints.
- `docmd`: documentation publishing and AI context generation.
- `rtk`: compact command output to reduce token noise.

## Deferred integration

- Install and execute each tool only after the Phase 1 memory and test gates pass.
- Keep crawlers bounded by allowlists, page limits, and runtime limits.
- Treat repository analysis outputs as proposals until verified.
