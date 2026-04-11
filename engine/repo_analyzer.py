from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from engine.memory_store import append_raw_log, write_json, write_text
from engine.dreaming import run_dream_cycle
from engine.utils import ROOT, now_iso


@dataclass(frozen=True)
class GitHubRepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def safe_id(self) -> str:
        return f"{self.owner}__{self.name}".replace("-", "_")


def parse_github_repo_url(value: str) -> GitHubRepoRef:
    value = value.strip()
    if re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        owner, name = value.split("/", 1)
        return GitHubRepoRef(owner=owner, name=name.removesuffix(".git"))

    parsed = urlparse(value)
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only github.com repository URLs are supported in Phase 1")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include owner and repository name")
    return GitHubRepoRef(owner=parts[0], name=parts[1].removesuffix(".git"))


def _fetch_json(url: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "HAX-Mind/0.1 repo-analyzer",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _fetch_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "HAX-Mind/0.1 repo-analyzer"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _path_ext(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return suffix or "[no_ext]"


def _top_dir(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "[root]"


def _infer_stack(paths: list[str], readme: str) -> list[str]:
    joined = "\n".join(paths).lower() + "\n" + readme.lower()
    signals = {
        "python": ["requirements.txt", "pyproject.toml", ".py", "pytest"],
        "nodejs": ["package.json", ".js", ".ts", "npm", "node"],
        "rust": ["cargo.toml", ".rs", "cargo"],
        "docker": ["dockerfile", "docker-compose"],
        "docs": ["docs/", "mkdocs", "docusaurus", "llms.txt", "markdown"],
        "web": ["vite", "next", "react", "public/", ".html", ".css"],
        "playwright": ["playwright"],
    }
    found = []
    for name, needles in signals.items():
        if any(needle in joined for needle in needles):
            found.append(name)
    return found


def analyze_github_repo(repo_url: str, root: Path = ROOT) -> dict:
    ref = parse_github_repo_url(repo_url)
    repo_meta = _fetch_json(f"https://api.github.com/repos/{ref.full_name}")
    default_branch = repo_meta.get("default_branch") or "main"
    tree = _fetch_json(f"https://api.github.com/repos/{ref.full_name}/git/trees/{default_branch}?recursive=1")
    tree_items = tree.get("tree", [])
    paths = [item["path"] for item in tree_items if item.get("type") == "blob" and "path" in item]

    readme = ""
    readme_url = f"https://raw.githubusercontent.com/{ref.full_name}/{default_branch}/README.md"
    try:
        readme = _fetch_text(readme_url)
    except Exception:
        readme = ""

    ext_counts = Counter(_path_ext(path) for path in paths)
    top_dirs = Counter(_top_dir(path) for path in paths)
    important_files = [
        path
        for path in paths
        if Path(path).name.lower()
        in {
            "readme.md",
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            "cargo.toml",
            "dockerfile",
            "docker-compose.yml",
            "tsconfig.json",
            "pytest.ini",
        }
    ][:50]

    record = {
        "repo": ref.full_name,
        "url": f"https://github.com/{ref.full_name}",
        "default_branch": default_branch,
        "description": repo_meta.get("description"),
        "visibility": repo_meta.get("visibility"),
        "archived": repo_meta.get("archived"),
        "stars": repo_meta.get("stargazers_count"),
        "forks": repo_meta.get("forks_count"),
        "file_count": len(paths),
        "top_directories": dict(top_dirs.most_common(20)),
        "extension_counts": dict(ext_counts.most_common(20)),
        "important_files": important_files,
        "inferred_stack": _infer_stack(paths, readme),
        "readme_excerpt": readme[:1200],
        "analyzed_at": now_iso(),
        "source": "github_api_read_only",
    }

    canonical_path = root / "memory" / "canonical" / "repo_knowledge" / f"{ref.safe_id}.json"
    summary_path = root / "runtime" / "reports" / f"repo_analysis_{ref.safe_id}.md"
    write_json(canonical_path, record)
    write_text(summary_path, render_repo_analysis(record))
    append_raw_log("repo_analyzed", f"Analyzed {ref.full_name} into {canonical_path.relative_to(root)}", topic="repo_analysis", importance="high", root=root)
    return record


def analyze_github_repo_and_dream(repo_url: str, root: Path = ROOT) -> tuple[dict, dict]:
    record = analyze_github_repo(repo_url, root=root)
    dream = run_dream_cycle(root=root, trigger=f"analyze_repo:{record['repo']}")
    return record, dream


def render_repo_analysis(record: dict) -> str:
    lines = [
        f"# Repo Analysis: {record['repo']}",
        "",
        f"- URL: {record['url']}",
        f"- Default branch: {record['default_branch']}",
        f"- File count: {record['file_count']}",
        f"- Inferred stack: {', '.join(record['inferred_stack']) or 'unknown'}",
        f"- Description: {record.get('description') or 'No description'}",
        "",
        "## Top directories",
    ]
    lines.extend(f"- {name}: {count}" for name, count in record["top_directories"].items())
    lines.extend(["", "## Extension counts"])
    lines.extend(f"- {name}: {count}" for name, count in record["extension_counts"].items())
    lines.extend(["", "## Important files"])
    lines.extend(f"- {path}" for path in record["important_files"] or ["No standard manifest files found"])
    return "\n".join(lines) + "\n"
