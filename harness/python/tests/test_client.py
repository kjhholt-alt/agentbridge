"""Tests for agentbridge.client -- sync + async client behavior.

These tests mostly exercise the parsing + envelope shapes without
needing a real adapter. Live-adapter integration is covered by the
conformance suite.
"""

from __future__ import annotations

import json
import socket
import threading

import pytest

from agentbridge import Client, BridgeError


class FakeAdapter:
    """A minimal fake adapter that replies to one request per connection."""

    def __init__(self, response: dict) -> None:
        self.response = response
        self.received: list[dict] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            client, _ = self._sock.accept()
        except OSError:
            return
        try:
            buf = b""
            while b"\n" not in buf:
                chunk = client.recv(4096)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n", 1)[0]
            if line:
                self.received.append(json.loads(line.decode()))
            out = (json.dumps(self.response) + "\n").encode()
            client.sendall(out)
        finally:
            client.close()

    def close(self) -> None:
        try: self._sock.close()
        except OSError: pass


def test_ping_returns_pong():
    fa = FakeAdapter({"ok": True, "pong": True})
    try:
        with Client.connect("127.0.0.1", fa.port, token="x") as c:
            assert c.ping() is True
        assert fa.received[0]["cmd"] == "ping"
    finally:
        fa.close()


def test_state_returns_state_dict():
    payload = {"player": {"position": [1.0, 2.0, 3.0]}, "time": {}}
    fa = FakeAdapter({"ok": True, "state": payload})
    try:
        with Client.connect("127.0.0.1", fa.port, token="x") as c:
            st = c.state()
            assert st == payload
    finally:
        fa.close()


def test_error_response_raises_bridgeerror():
    fa = FakeAdapter({"ok": False, "error": "auth", "code": 1002})
    try:
        with Client.connect("127.0.0.1", fa.port, token="x") as c:
            with pytest.raises(BridgeError) as exc:
                c.state()
            assert exc.value.code == 1002
    finally:
        fa.close()


def test_action_with_value_serializes_correctly():
    fa = FakeAdapter({"ok": True})
    try:
        with Client.connect("127.0.0.1", fa.port, token="x") as c:
            c.action("move_forward", value=True)
        assert fa.received[0] == {"cmd": "action", "name": "move_forward", "value": True}
    finally:
        fa.close()


def test_hello_records_session_and_caps():
    fa = FakeAdapter({
        "ok": True,
        "session_id": "s1",
        "server_caps": ["step", "snapshot_hash"],
        "max_event_buffer": 256,
        "schema_url": "x",
        "engine": "godot",
        "engine_version": "4.6.2",
    })
    try:
        with Client.connect("127.0.0.1", fa.port, token="x") as c:
            r = c.hello(agent_name="t", capabilities=["step"])
            assert r.session_id == "s1"
            assert "step" in r.server_caps
            assert c.session_id == "s1"
    finally:
        fa.close()
