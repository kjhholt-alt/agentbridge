"""AgentBridge orchestrator -- run N parallel adapter instances.

Phase 4 stub. Spawns multiple adapter subprocesses on different ports,
runs missions against each in parallel, collects results.

Used by `agentbridge sweep` and `agentbridge ci` CLI subcommands.

Telemetry: every ``run_mission`` emits agent_session start/end/error
events into events-ndjson v1's ``agent_session`` stream when the
optional ``events_ndjson`` library is installed. Disable with
``AGENTBRIDGE_DISABLE_EVENTS=1``. Configure log path with
``AGENTBRIDGE_EVENTS_LOG``.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from .client import AsyncClient


def _maybe_emitter():
    """Return an AgentSessionEmitter singleton, or None if telemetry disabled."""
    if os.environ.get("AGENTBRIDGE_DISABLE_EVENTS"):
        return None
    try:
        # Repo lays observability/ as a sibling of harness/python/, not in
        # the import path. Resolve it lazily and cache the result.
        from importlib import util
        repo_root = Path(__file__).resolve().parents[3]
        target = repo_root / "observability" / "agent_session_emitter.py"
        if not target.exists():
            return None
        spec = util.spec_from_file_location("agentbridge_obs_emitter", target)
        if spec is None or spec.loader is None:
            return None
        if "agentbridge_obs_emitter" in sys.modules:
            mod = sys.modules["agentbridge_obs_emitter"]
        else:
            mod = util.module_from_spec(spec)
            sys.modules["agentbridge_obs_emitter"] = mod
            spec.loader.exec_module(mod)
        return mod.default_emitter()
    except Exception:
        return None


@dataclass
class Instance:
    port: int
    proc: subprocess.Popen
    log_path: Path


def spawn(launch_argv: list[str], port: int, log_dir: Path) -> Instance:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"instance_{port}.log"
    env = os.environ.copy()
    env["AGENTBRIDGE"] = "1"
    env["AGENTBRIDGE_PORT"] = str(port)
    f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(launch_argv, env=env, stdout=f, stderr=subprocess.STDOUT)
    return Instance(port=port, proc=proc, log_path=log_path)


def teardown(inst: Instance) -> None:
    try:
        inst.proc.terminate()
        inst.proc.wait(timeout=4)
    except Exception:
        try: inst.proc.kill()
        except Exception: pass


async def run_mission(host: str, port: int, token: str,
                      mission: Callable[[AsyncClient], Awaitable[dict]],
                      capabilities: list[str] | None = None,
                      *,
                      agent_name: str = "orchestrator-mission",
                      session_id: Optional[str] = None) -> dict:
    emitter = _maybe_emitter()
    sid: Optional[str] = None
    if emitter is not None:
        sid = emitter.start(session_id=session_id, agent=agent_name)
    client = await AsyncClient.connect(host, port, token=token)
    try:
        await client.hello(agent_name=agent_name,
                           capabilities=capabilities or [])
        result = await mission(client)
    except Exception as exc:
        if emitter is not None and sid is not None:
            emitter.error(sid, summary=f"{type(exc).__name__}: {exc}", agent=agent_name)
        raise
    finally:
        await client.quit()
        await client.close()
    if emitter is not None and sid is not None:
        exit_code = 0 if (isinstance(result, dict) and result.get("ok", True)) else 1
        emitter.end(sid, exit_code=exit_code, agent=agent_name)
    return result


async def run_parallel(host: str, ports: list[int], token: str,
                       mission_factory: Callable[[int], Callable[[AsyncClient], Awaitable[dict]]],
                       capabilities: list[str] | None = None,
                       per_mission_timeout: float = 60.0) -> list[dict]:
    """Run one mission per port concurrently. mission_factory returns a
    coroutine factory parameterized by port index.
    """
    coros = []
    for i, p in enumerate(ports):
        coro = run_mission(host, p, token, mission_factory(i), capabilities=capabilities)
        coros.append(asyncio.wait_for(coro, timeout=per_mission_timeout))
    results = await asyncio.gather(*coros, return_exceptions=True)
    out: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            out.append({"ok": False, "error": repr(r)})
        else:
            out.append(r)
    return out
