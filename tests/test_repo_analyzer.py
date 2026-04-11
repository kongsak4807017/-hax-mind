from engine.repo_analyzer import GitHubRepoRef, _infer_stack, parse_github_repo_url, render_repo_analysis


def test_parse_github_repo_url():
    assert parse_github_repo_url("https://github.com/kongsak4807017/crawl4ai").full_name == "kongsak4807017/crawl4ai"
    assert parse_github_repo_url("kongsak4807017/rtk.git") == GitHubRepoRef("kongsak4807017", "rtk")


def test_infer_stack_from_paths_and_readme():
    stack = _infer_stack(["package.json", "src/index.ts", "docs/index.md"], "Generates llms.txt")
    assert "nodejs" in stack
    assert "docs" in stack


def test_render_repo_analysis():
    text = render_repo_analysis(
        {
            "repo": "owner/repo",
            "url": "https://github.com/owner/repo",
            "default_branch": "main",
            "file_count": 2,
            "inferred_stack": ["python"],
            "description": "demo",
            "top_directories": {"[root]": 1, "src": 1},
            "extension_counts": {".py": 1, ".md": 1},
            "important_files": ["README.md"],
        }
    )
    assert "Repo Analysis: owner/repo" in text
    assert "python" in text
