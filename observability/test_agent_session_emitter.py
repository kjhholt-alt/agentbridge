"""Tests for the agent_session emitter (cycle 4 -- agentbridge telemetry)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_emitter_module():
    here = Path(__file__).resolve().parent
    src = here / "agent_session_emitter.py"
    spec = importlib.util.spec_from_file_location("agent_session_emitter_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _has_events_ndjson() -> bool:
    try:
        import events_ndjson  # noqa: F401
        return True
    except ImportError:
        return False


# --- no-op behaviour when events_ndjson absent -------------------------------

class TestNoopWithoutEventsNdjson:
    def test_emitter_constructible_without_lib(self, tmp_path, monkeypatch):
        # Force-import-fail by hiding the module if present.
        if "events_ndjson" in sys.modules:
            monkeypatch.setitem(sys.modules, "events_ndjson", None)
        # Re-import emitter so its `from events_ndjson import Writer` re-runs.
        mod = _load_emitter_module()
        em = mod.AgentSessionEmitter(path=tmp_path / "evt.ndjson")
        # When the lib import fails, available is False and methods return None.
        if not em.available:
            sid = em.start(agent="x")
            assert isinstance(sid, str) and len(sid) > 0
            assert em.end(sid, exit_code=0) is None


# --- real emission when events_ndjson present --------------------------------

@pytest.mark.skipif(not _has_events_ndjson(), reason="events_ndjson not installed")
class TestRealEmission:
    def test_start_end_roundtrip(self, tmp_path):
        mod = _load_emitter_module()
        log = tmp_path / "session.ndjson"
        em = mod.AgentSessionEmitter(path=log, source="test-agentbridge")
        assert em.available is True
        sid = em.start(agent="alpha")
        end_env = em.end(sid, exit_code=0, agent="alpha")
        assert end_env is not None
        assert end_env["payload"]["session_id"] == sid
        assert end_env["payload"]["phase"] == "end"
        assert end_env["payload"]["exit_code"] == 0
        # Two lines on disk: start + end.
        lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert [l["payload"]["phase"] for l in lines] == ["start", "end"]

    def test_error_phase_caps_summary(self, tmp_path):
        mod = _load_emitter_module()
        log = tmp_path / "err.ndjson"
        em = mod.AgentSessionEmitter(path=log, source="test-agentbridge")
        sid = em.start(agent="beta")
        oversize = "x" * 5000
        env = em.error(sid, summary=oversize, agent="beta")
        assert env is not None
        assert env["payload"]["phase"] == "error"
        assert len(env["payload"]["summary"]) == 1024

    def test_session_context_manager_happy_path(self, tmp_path):
        mod = _load_emitter_module()
        log = tmp_path / "ctx.ndjson"
        em = mod.AgentSessionEmitter(path=log, source="test-agentbridge")
        with em.session(agent="gamma") as sid:
            assert isinstance(sid, str)
        phases = [json.loads(l)["payload"]["phase"] for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert phases == ["start", "end"]

    def test_session_context_manager_error_path(self, tmp_path):
        mod = _load_emitter_module()
        log = tmp_path / "ctx_err.ndjson"
        em = mod.AgentSessionEmitter(path=log, source="test-agentbridge")
        with pytest.raises(RuntimeError):
            with em.session(agent="delta"):
                raise RuntimeError("boom")
        phases = [json.loads(l)["payload"]["phase"] for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert phases == ["start", "error"]

    def test_default_emitter_singleton(self, tmp_path, monkeypatch):
        mod = _load_emitter_module()
        monkeypatch.setenv("AGENTBRIDGE_EVENTS_LOG", str(tmp_path / "default.ndjson"))
        mod.reset_default_emitter()
        em1 = mod.default_emitter()
        em2 = mod.default_emitter()
        assert em1 is em2


# --- env var overrides ------------------------------------------------------

class TestPathResolution:
    def test_env_var_overrides_default(self, tmp_path, monkeypatch):
        mod = _load_emitter_module()
        target = tmp_path / "custom" / "session.ndjson"
        monkeypatch.setenv("AGENTBRIDGE_EVENTS_LOG", str(target))
        mod.reset_default_emitter()
        em = mod.default_emitter()
        assert em.path == target

    def test_constructor_path_wins_over_env(self, tmp_path, monkeypatch):
        mod = _load_emitter_module()
        monkeypatch.setenv("AGENTBRIDGE_EVENTS_LOG", str(tmp_path / "env.ndjson"))
        explicit = tmp_path / "explicit.ndjson"
        em = mod.AgentSessionEmitter(path=explicit)
        assert em.path == explicit
