"""agent_session_emitter -- emit events-ndjson agent_session events.

This is the agentbridge side of the unified telemetry pipeline. Every
mission run by the orchestrator emits a "start" / "end" / "error" event
into an NDJSON stream conforming to events-ndjson v1's `agent_session`
schema. The emitted file can then be consumed by the same dashboards
that watch outreach, cost, and gate_audit streams.

Design rules:
 - **events-ndjson is an OPTIONAL dependency.** If the library isn't
   installed, every emitter call is a silent no-op (returns None). This
   keeps the agentbridge harness usable in minimal environments.
 - **No per-step events from here.** The orchestrator only sees
   start/end of a mission. If you want tool_use / message events you
   wire those at the adapter layer (TODO).
 - **Path is configurable.** ``AGENTBRIDGE_EVENTS_LOG`` env var, or
   constructor argument, or default ``~/.agentbridge/events.ndjson``.

Usage::

    em = AgentSessionEmitter(source="agentbridge")
    sid = em.start(agent="repro-runner")
    try:
        ...
        em.end(sid, exit_code=0)
    except Exception as exc:
        em.error(sid, summary=str(exc))
        raise
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional


def _default_log_path() -> Path:
    env = os.environ.get("AGENTBRIDGE_EVENTS_LOG")
    if env:
        return Path(env)
    return Path.home() / ".agentbridge" / "events.ndjson"


class AgentSessionEmitter:
    """Emit ``agent_session`` events to an NDJSON file.

    If the ``events_ndjson`` package isn't installed, the emitter
    becomes a no-op: every method returns ``None`` and never raises.
    Test the active state with :attr:`available`.
    """

    STREAM = "agent_session"

    def __init__(
        self,
        *,
        source: str = "agentbridge",
        path: Optional[Path] = None,
        validate_payload: bool = True,
    ) -> None:
        self.source = source
        self.path = Path(path) if path is not None else _default_log_path()
        self._validate_payload = validate_payload
        self._writer: Any = None
        self._sessions: dict[str, float] = {}
        self._init_writer()

    # ----------------------------------------------------------------- internal

    def _init_writer(self) -> None:
        try:
            from events_ndjson import Writer  # type: ignore[import-untyped]
        except ImportError:
            self._writer = None
            return
        try:
            self._writer = Writer(
                stream=self.STREAM,
                source=self.source,
                path=self.path,
                validate_payload=self._validate_payload,
            )
        except Exception:
            # Schema not registered, file unwritable, etc. Stay silent --
            # telemetry should never break the mission run.
            self._writer = None

    @property
    def available(self) -> bool:
        """True iff a real events_ndjson Writer is wired up."""
        return self._writer is not None

    def _emit(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        if self._writer is None:
            return None
        try:
            return self._writer.append(event_type=payload["phase"], payload=payload)
        except Exception:
            # Same rule: telemetry never breaks the run. Swallow.
            return None

    # ----------------------------------------------------------------- public

    def start(
        self,
        *,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> str:
        """Emit a "start" phase event, return the session_id (created if absent)."""
        sid = session_id or uuid.uuid4().hex[:32]
        self._sessions[sid] = time.monotonic()
        payload: dict[str, Any] = {"session_id": sid, "phase": "start"}
        if agent:
            payload["agent"] = agent
        if summary:
            payload["summary"] = summary
        self._emit(payload)
        return sid

    def end(
        self,
        session_id: str,
        *,
        exit_code: int = 0,
        summary: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        started = self._sessions.pop(session_id, None)
        duration_ms = int((time.monotonic() - started) * 1000) if started is not None else 0
        payload: dict[str, Any] = {
            "session_id": session_id,
            "phase": "end",
            "duration_ms": duration_ms,
            "exit_code": exit_code,
        }
        if summary:
            payload["summary"] = summary
        if agent:
            payload["agent"] = agent
        return self._emit(payload)

    def error(
        self,
        session_id: str,
        *,
        summary: str,
        agent: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        started = self._sessions.pop(session_id, None)
        duration_ms = int((time.monotonic() - started) * 1000) if started is not None else 0
        payload: dict[str, Any] = {
            "session_id": session_id,
            "phase": "error",
            "duration_ms": duration_ms,
            "summary": summary[:1024],
        }
        if agent:
            payload["agent"] = agent
        return self._emit(payload)

    @contextmanager
    def session(self, *, agent: Optional[str] = None, summary: Optional[str] = None) -> Iterator[str]:
        """Context manager wrapping start/end/error around a block."""
        sid = self.start(agent=agent, summary=summary)
        try:
            yield sid
        except Exception as exc:
            self.error(sid, summary=f"{type(exc).__name__}: {exc}", agent=agent)
            raise
        else:
            self.end(sid, exit_code=0, agent=agent)


_default_emitter: Optional[AgentSessionEmitter] = None


def default_emitter() -> AgentSessionEmitter:
    """Return a process-wide singleton emitter pointed at the default log path."""
    global _default_emitter
    if _default_emitter is None:
        _default_emitter = AgentSessionEmitter()
    return _default_emitter


def reset_default_emitter() -> None:
    """Test helper: drop the singleton so the next call re-reads env vars."""
    global _default_emitter
    _default_emitter = None
