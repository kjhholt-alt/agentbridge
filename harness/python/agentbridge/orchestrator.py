"""AgentBridge orchestrator -- run N parallel adapter instances.

Phase 4 stub. Spawns multiple adapter subprocesses on different ports,
runs missions against each in parallel, collects results.

Used by `agentbridge sweep` and `agentbridge ci` CLI subcommands.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .client import AsyncClient


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
                      capabilities: list[str] | None = None) -> dict:
    client = await AsyncClient.connect(host, port, token=token)
    try:
        await client.hello(agent_name="orchestrator-mission",
                           capabilities=capabilities or [])
        result = await mission(client)
    finally:
        await client.quit()
        await client.close()
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
