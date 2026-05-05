"""Smoke tests for the MCP server (uses introspection + DRYRUN tools)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

import server  # noqa: E402


def test_tools_list_has_three_tools():
    assert len(server.TOOLS) == 3
    names = [t["name"] for t in server.TOOLS]
    assert "agentbridge_status" in names
    assert "agentbridge_run_mission" in names
    assert "agentbridge_replay" in names


def test_tools_have_input_schemas():
    for t in server.TOOLS:
        assert "inputSchema" in t
        assert t["inputSchema"]["type"] == "object"


def test_handle_initialize():
    resp = server._handle({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}
    })
    assert resp is not None
    assert resp["result"]["serverInfo"]["name"] == "agentbridge"


def test_handle_tools_list():
    resp = server._handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
    })
    assert resp["result"]["tools"][0]["name"] == "agentbridge_status"


def test_handle_unknown_method():
    resp = server._handle({
        "jsonrpc": "2.0", "id": 3, "method": "totally/made/up", "params": {}
    })
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_call_tool_unknown_name_returns_error():
    res = server.call_tool("not_a_real_tool", {})
    assert res["ok"] is False
