"""AgentBridge MCP server.

Exposes harness verbs as MCP tools so Claude Code (or any MCP client)
can drive any agentbridge-enabled game directly without invoking the
CLI.

Tools:
  agentbridge_status         -> check liveness against host:port
  agentbridge_run_mission    -> run a scripted mission
  agentbridge_replay         -> verify a recorded session

Stdio transport. Register in ~/.claude.json mcpServers:

  "agentbridge": {
    "command": "python",
    "args": ["-m", "agentbridge_mcp_server.server"]
  }
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Phase 6 deliberately implements MCP via the lightweight stdio
# JSON-RPC protocol (no external mcp-python lib dependency) so this
# works across Python 3.11+/3.13/3.14 without version pinning.

# Spec: MCP messages are JSON-RPC 2.0 framed by Content-Length headers.
# We support the minimal subset: initialize, tools/list, tools/call.

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agentbridge", "version": "0.1.0"}

TOOLS: list[dict] = [
    {
        "name": "agentbridge_status",
        "description": "Ping a running adapter to check liveness. Returns "
                        "{ok, engine, engine_version, server_caps}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "default": "127.0.0.1"},
                "port": {"type": "integer", "default": 7777},
                "token_file": {"type": "string"},
            },
            "required": ["token_file"],
        },
    },
    {
        "name": "agentbridge_run_mission",
        "description": "Run a scripted mission against a running adapter and "
                        "return the final state + drained events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "default": "127.0.0.1"},
                "port": {"type": "integer", "default": 7777},
                "token_file": {"type": "string"},
                "script": {
                    "type": "array",
                    "description": "List of {action, value, duration} steps",
                    "items": {"type": "object"},
                },
            },
            "required": ["token_file", "script"],
        },
    },
    {
        "name": "agentbridge_replay",
        "description": "Verify that a recorded session reproduces deterministically. "
                        "Returns matches/diverged/first_divergence_at.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "default": "127.0.0.1"},
                "port": {"type": "integer", "default": 7777},
                "token_file": {"type": "string"},
                "ndjson_path": {"type": "string"},
            },
            "required": ["token_file", "ndjson_path"],
        },
    },
]


# Add the harness package to sys.path so we can import agentbridge.*
HARNESS_DIR = Path(__file__).resolve().parents[2] / "harness" / "python"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from agentbridge import Client, verify  # noqa: E402


def _read_token(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8").strip().splitlines()[0]


def call_tool(name: str, args: dict) -> dict:
    if name == "agentbridge_status":
        token = _read_token(args["token_file"])
        host = args.get("host", "127.0.0.1")
        port = int(args.get("port", 7777))
        with Client.connect(host, port, token=token) as c:
            h = c.hello(agent_name="mcp-status", capabilities=[])
            c.quit()
        return {"ok": True, "engine": h.engine, "engine_version": h.engine_version,
                "server_caps": h.server_caps, "session_id": h.session_id}
    if name == "agentbridge_run_mission":
        import time
        token = _read_token(args["token_file"])
        host = args.get("host", "127.0.0.1")
        port = int(args.get("port", 7777))
        script = args.get("script", [])
        with Client.connect(host, port, token=token) as c:
            c.hello(agent_name="mcp-mission", capabilities=[])
            for step in script:
                action = step.get("action") or step.get("name")
                value = step.get("value")
                c.action(action, value)
                d = float(step.get("duration", 0.05))
                if d > 0:
                    time.sleep(min(d, 5.0))
            final_state = c.state()
            events = c.events()
            c.quit()
        return {"ok": True, "final_state": final_state, "events": events}
    if name == "agentbridge_replay":
        token = _read_token(args["token_file"])
        host = args.get("host", "127.0.0.1")
        port = int(args.get("port", 7777))
        path = Path(args["ndjson_path"])
        report = verify(host, port, token, path)
        return {"ok": report.deterministic, "matches": report.matches,
                "diverged": report.diverged,
                "first_divergence_at": report.first_divergence_at}
    return {"ok": False, "error": f"unknown tool {name}"}


# ---------------- JSON-RPC stdio loop ----------------

def _read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line_s = line.decode("utf-8").strip()
        if line_s == "":
            break
        if ":" in line_s:
            k, v = line_s.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    cl = int(headers.get("content-length", "0"))
    if cl <= 0:
        return None
    body = sys.stdin.buffer.read(cl)
    return json.loads(body.decode("utf-8"))


def _write_message(msg: dict) -> None:
    body = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _handle(msg: dict) -> dict | None:
    method = msg.get("method", "")
    msg_id = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            result = call_tool(name, args)
            return {"jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text",
                                            "text": json.dumps(result)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32000, "message": repr(e)}}
    if method.startswith("notifications/"):
        return None
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"unknown method {method}"}}


def main() -> int:
    while True:
        msg = _read_message()
        if msg is None:
            return 0
        resp = _handle(msg)
        if resp is not None:
            _write_message(resp)


if __name__ == "__main__":
    sys.exit(main())
