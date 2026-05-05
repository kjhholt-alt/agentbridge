"""AgentBridge client.

Synchronous TCP newline-JSON client. The async variant is `AsyncClient`
(below). Both use the same wire format defined in spec/AGENTBRIDGE_SPEC.md.

Usage:

    from agentbridge import Client
    with Client.connect("127.0.0.1", 7777, token=open(token_path).read().strip()) as bridge:
        bridge.hello(agent_name="my-agent",
                     capabilities=["step", "set_seed", "snapshot_hash"])
        state = bridge.state()
        bridge.action("move_forward", value=True)
        events = bridge.events()
        bridge.quit()
"""

from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "1.0.0"


class BridgeError(Exception):
    """Adapter returned an error response."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"code={code} msg={message}")
        self.code = code
        self.message = message


@dataclass
class HelloResponse:
    session_id: str
    server_caps: list[str]
    max_event_buffer: int
    schema_url: str
    engine: str
    engine_version: str


class Client:
    """Synchronous client. Use the `connect` classmethod or the `with` form."""

    def __init__(self, sock: socket.socket, token: str = "") -> None:
        self.sock = sock
        self.token = token
        self.buffer = b""
        self.session_id: str = ""
        self.server_caps: list[str] = []
        self.granted_caps: list[str] = []

    @classmethod
    def connect(cls, host: str, port: int, token: str = "",
                timeout: float = 10.0) -> "Client":
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
        return cls(sock, token=token)

    @classmethod
    def connect_with_token_file(cls, host: str, port: int,
                                 token_file: Path, timeout: float = 10.0) -> "Client":
        token = token_file.read_text(encoding="utf-8").strip().splitlines()[0]
        return cls.connect(host, port, token=token, timeout=timeout)

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _send(self, obj: dict) -> dict:
        line = (json.dumps(obj) + "\n").encode("utf-8")
        self.sock.sendall(line)
        return self._read_response()

    def _read_response(self) -> dict:
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(8192)
            if not chunk:
                raise ConnectionError("bridge closed")
            self.buffer += chunk
        nl = self.buffer.index(b"\n")
        line = self.buffer[:nl]
        self.buffer = self.buffer[nl + 1 :]
        return json.loads(line.decode("utf-8"))

    def _checked(self, response: dict) -> dict:
        if response.get("ok") is False:
            raise BridgeError(int(response.get("code", 0)), str(response.get("error", "")))
        return response

    def hello(self, agent_name: str = "client",
              capabilities: list[str] | None = None) -> HelloResponse:
        msg: dict = {
            "cmd": "hello",
            "protocol": PROTOCOL_VERSION,
            "agent_name": agent_name,
            "token": self.token,
        }
        if capabilities:
            msg["capabilities"] = capabilities
        r = self._checked(self._send(msg))
        self.session_id = r.get("session_id", "")
        self.server_caps = list(r.get("server_caps", []))
        self.granted_caps = [c for c in (capabilities or []) if c in self.server_caps]
        return HelloResponse(
            session_id=self.session_id,
            server_caps=self.server_caps,
            max_event_buffer=int(r.get("max_event_buffer", 0)),
            schema_url=str(r.get("schema_url", "")),
            engine=str(r.get("engine", "")),
            engine_version=str(r.get("engine_version", "")),
        )

    def ping(self) -> bool:
        return bool(self._send({"cmd": "ping"}).get("pong", False))

    def state(self) -> dict:
        r = self._checked(self._send({"cmd": "state"}))
        return r.get("state", {})

    def action(self, name: str, value: Any = None) -> dict:
        msg: dict = {"cmd": "action", "name": name}
        if value is not None:
            msg["value"] = value
        return self._checked(self._send(msg))

    def events(self) -> list[dict]:
        r = self._checked(self._send({"cmd": "events"}))
        return list(r.get("events", []))

    def reset(self) -> None:
        self._checked(self._send({"cmd": "reset"}))

    def quit(self) -> None:
        try:
            self._send({"cmd": "quit"})
        except (ConnectionError, OSError):
            pass

    def capabilities(self) -> list[str]:
        r = self._checked(self._send({"cmd": "capabilities"}))
        return list(r.get("capabilities", []))

    def subscribe(self, types: list[str]) -> None:
        self._checked(self._send({"cmd": "subscribe", "types": types}))

    def unsubscribe(self, types: list[str]) -> None:
        self._checked(self._send({"cmd": "unsubscribe", "types": types}))

    def set_seed(self, seed: int) -> None:
        self._checked(self._send({"cmd": "set_seed", "seed": int(seed)}))

    def step(self, frames: int) -> None:
        self._checked(self._send({"cmd": "step", "frames": int(frames)}))

    def set_timescale(self, scale: float) -> None:
        self._checked(self._send({"cmd": "set_timescale", "scale": float(scale)}))

    def snapshot_hash(self) -> str:
        r = self._checked(self._send({"cmd": "snapshot_hash"}))
        return str(r.get("hash", ""))

    def bind_action(self, name: str, input_action: str, kind: str) -> None:
        self._checked(self._send({
            "cmd": "bind_action",
            "name": name,
            "input_action": input_action,
            "kind": kind,
        }))

    def metrics(self) -> dict:
        r = self._checked(self._send({"cmd": "metrics"}))
        return dict(r.get("metrics", {}))


# ---------- Async variant (Phase 4 stub; used by the orchestrator) ----------

class AsyncClient:
    """Async TCP client built on asyncio.streams. Same protocol surface as Client."""

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter, token: str = "") -> None:
        self.reader = reader
        self.writer = writer
        self.token = token
        self.session_id: str = ""
        self.server_caps: list[str] = []

    @classmethod
    async def connect(cls, host: str, port: int, token: str = "") -> "AsyncClient":
        reader, writer = await asyncio.open_connection(host, port)
        return cls(reader, writer, token=token)

    async def _send(self, obj: dict) -> dict:
        line = (json.dumps(obj) + "\n").encode("utf-8")
        self.writer.write(line)
        await self.writer.drain()
        raw = await self.reader.readline()
        if not raw:
            raise ConnectionError("bridge closed")
        return json.loads(raw.decode("utf-8"))

    async def hello(self, agent_name: str = "client",
                    capabilities: list[str] | None = None) -> HelloResponse:
        msg: dict = {"cmd": "hello", "protocol": PROTOCOL_VERSION,
                     "agent_name": agent_name, "token": self.token}
        if capabilities:
            msg["capabilities"] = capabilities
        r = await self._send(msg)
        if r.get("ok") is False:
            raise BridgeError(int(r.get("code", 0)), str(r.get("error", "")))
        self.session_id = r.get("session_id", "")
        self.server_caps = list(r.get("server_caps", []))
        return HelloResponse(
            session_id=self.session_id,
            server_caps=self.server_caps,
            max_event_buffer=int(r.get("max_event_buffer", 0)),
            schema_url=str(r.get("schema_url", "")),
            engine=str(r.get("engine", "")),
            engine_version=str(r.get("engine_version", "")),
        )

    async def state(self) -> dict:
        r = await self._send({"cmd": "state"})
        return r.get("state", {})

    async def action(self, name: str, value: Any = None) -> dict:
        msg: dict = {"cmd": "action", "name": name}
        if value is not None:
            msg["value"] = value
        return await self._send(msg)

    async def events(self) -> list[dict]:
        r = await self._send({"cmd": "events"})
        return list(r.get("events", []))

    async def quit(self) -> None:
        try:
            await self._send({"cmd": "quit"})
        except Exception:
            pass

    async def close(self) -> None:
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
