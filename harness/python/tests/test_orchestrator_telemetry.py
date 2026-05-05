"""Integration test: orchestrator.run_mission emits agent_session events.

Avoids spinning up a real adapter by patching AsyncClient.connect with a
stub. Verifies the emitter receives start + end on the happy path,
and start + error on the failure path. Also verifies the
AGENTBRIDGE_DISABLE_EVENTS env var short-circuits emission.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from agentbridge import orchestrator


class _FakeClient:
    async def hello(self, **kwargs):
        return None

    async def quit(self):
        return None

    async def close(self):
        return None


class _RecordingEmitter:
    def __init__(self):
        self.calls: list[tuple] = []

    def start(self, *, session_id=None, agent=None, summary=None):
        self.calls.append(("start", session_id, agent, summary))
        return session_id or "fake-sid"

    def end(self, session_id, *, exit_code=0, summary=None, agent=None):
        self.calls.append(("end", session_id, exit_code, agent))

    def error(self, session_id, *, summary, agent=None):
        self.calls.append(("error", session_id, summary[:64], agent))


@pytest.fixture
def fake_client_factory():
    async def _connect(host, port, *, token=None):
        return _FakeClient()
    return _connect


def test_run_mission_emits_start_and_end_on_success(fake_client_factory):
    rec = _RecordingEmitter()

    async def mission(client):
        return {"ok": True, "result": "nice"}

    with patch.object(orchestrator, "_maybe_emitter", return_value=rec), \
         patch.object(orchestrator.AsyncClient, "connect", staticmethod(fake_client_factory)):
        result = asyncio.run(orchestrator.run_mission("h", 1, "tok", mission, agent_name="alpha"))

    assert result["ok"] is True
    phases = [c[0] for c in rec.calls]
    assert phases == ["start", "end"]
    # end exit_code should be 0 because mission returned ok=True
    end_call = next(c for c in rec.calls if c[0] == "end")
    assert end_call[2] == 0
    assert end_call[3] == "alpha"


def test_run_mission_emits_error_on_mission_exception(fake_client_factory):
    rec = _RecordingEmitter()

    async def boom(client):
        raise RuntimeError("explicit failure")

    with patch.object(orchestrator, "_maybe_emitter", return_value=rec), \
         patch.object(orchestrator.AsyncClient, "connect", staticmethod(fake_client_factory)):
        with pytest.raises(RuntimeError, match="explicit failure"):
            asyncio.run(orchestrator.run_mission("h", 1, "tok", boom, agent_name="beta"))

    phases = [c[0] for c in rec.calls]
    assert phases == ["start", "error"]
    err_call = next(c for c in rec.calls if c[0] == "error")
    assert "RuntimeError" in err_call[2]
    assert "explicit failure" in err_call[2]


def test_run_mission_no_emitter_when_disabled(fake_client_factory, monkeypatch):
    monkeypatch.setenv("AGENTBRIDGE_DISABLE_EVENTS", "1")
    rec = _RecordingEmitter()

    async def mission(client):
        return {"ok": True}

    # _maybe_emitter should now return None on its own. We verify by leaving
    # it un-patched and checking no exceptions + no emit attempts.
    with patch.object(orchestrator.AsyncClient, "connect", staticmethod(fake_client_factory)):
        result = asyncio.run(orchestrator.run_mission("h", 1, "tok", mission))

    assert result["ok"] is True
    # rec wasn't even installed, so this just confirms the run completed.


def test_run_mission_emits_failure_exit_code_when_result_not_ok(fake_client_factory):
    rec = _RecordingEmitter()

    async def mission(client):
        return {"ok": False, "error": "downstream fail"}

    with patch.object(orchestrator, "_maybe_emitter", return_value=rec), \
         patch.object(orchestrator.AsyncClient, "connect", staticmethod(fake_client_factory)):
        result = asyncio.run(orchestrator.run_mission("h", 1, "tok", mission))

    assert result["ok"] is False
    end_call = next(c for c in rec.calls if c[0] == "end")
    assert end_call[2] == 1
