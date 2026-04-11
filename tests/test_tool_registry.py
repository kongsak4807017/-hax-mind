from engine.tool_registry import get_tool, iter_tools, tool_cards


def test_tool_registry_contains_owner_repos():
    repos = {tool.repo for tool in iter_tools()}
    assert "kongsak4807017/crawl4ai" in repos
    assert "kongsak4807017/Reverse-Engineer" in repos
    assert "kongsak4807017/docmd" in repos
    assert "kongsak4807017/rtk" in repos


def test_get_tool_alias():
    assert get_tool("Reverse-Engineer").id == "reverse_engineer"
    assert get_tool("rtk").role == "token_compression"


def test_tool_cards_are_serializable():
    cards = tool_cards()
    assert len(cards) == 4
    assert all("memory_use" in card for card in cards)
