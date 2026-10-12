from swarm.manager import tool_search_query


def test_tool_search_alias_uses_query_args():
    assert tool_search_query({"query": "  current champion  "}, "fallback task") == "current champion"
    assert tool_search_query({"q": "market resolution"}, "fallback task") == "market resolution"


def test_tool_search_alias_without_args_falls_back_to_task():
    assert tool_search_query({}, "  find the official current champion  ") == "find the official current champion"
    assert tool_search_query({"expression": "not a search"}, "fallback task") == "not a search"


def test_observed_tool_search_alias_name_is_supported():
    # The coordinator emitted this name in the J16 rerun; it must use the same web-search path.
    assert tool_search_query({"query": "current champion"}, "fallback") == "current champion"
