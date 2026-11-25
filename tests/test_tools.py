from mcp_server.server import coverage_checker_tool, script_linter_tool


def test_coverage_tool_returns_contract() -> None:
    requirements = [{"id": "R1", "text": "works", "source_chunk_id": "c1"}]
    cases = [{"id": "T1", "req_ids": ["R1"], "title": "works", "expected_result": "ok", "type": "positive"}]
    assert coverage_checker_tool(requirements, cases)["score"] == 1


def test_linter_rejects_invalid_python() -> None:
    assert script_linter_tool("def broken(:")["valid"] is False
