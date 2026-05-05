"""AgentBridge replay -- record + verify deterministic re-runs.

A replay is the NDJSON log of every command + response + event from a
session, written by the adapter when the `replay` capability is
negotiated. This module reads those logs, replays them against a
fresh adapter session (with set_seed + step), and asserts the
snapshot_hash sequence matches.

Two operations:

    record(session_log_path, output_path)
    -> just copies the adapter-side log to a stable path

    verify(host, port, token, session_log_path, capabilities=...)
    -> replays the recorded inputs against a fresh adapter and
       compares snapshot_hash sequences. Returns DivergenceReport.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .client import Client


@dataclass
class DivergenceReport:
    matches: int = 0
    diverged: int = 0
    expected: list[str] = field(default_factory=list)
    actual: list[str] = field(default_factory=list)
    first_divergence_at: int | None = None

    @property
    def deterministic(self) -> bool:
        return self.diverged == 0 and self.matches > 0


def record(adapter_log_path: Path, output_path: Path) -> Path:
    """Copy the adapter's session ndjson to a stable filename."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(adapter_log_path, output_path)
    return output_path


def verify(host: str, port: int, token: str,
           recorded_path: Path,
           capabilities: list[str] | None = None) -> DivergenceReport:
    """Replay a recorded session against a fresh adapter and compare hashes.

    The recorded file is in the adapter's ndjson format:
        {"dir": "in|out|event", "t": ..., "frame": ..., "line": {...}}

    We extract the agent's INPUT lines (dir=in) in order, send them to
    the fresh adapter, and after every line that touches state we
    compute snapshot_hash and compare to the recorded `out` snapshot
    hashes (collected when dir=out and line has "hash").
    """
    cmds: list[dict] = []
    expected_hashes: list[str] = []
    with recorded_path.open("r", encoding="utf-8") as f:
        for raw in f:
            entry = json.loads(raw)
            if entry.get("dir") == "in":
                cmds.append(entry["line"])
            elif entry.get("dir") == "out":
                line = entry.get("line", {})
                h = line.get("hash")
                if h:
                    expected_hashes.append(h)

    caps = capabilities or ["set_seed", "snapshot_hash", "step"]
    report = DivergenceReport()
    actual_hashes: list[str] = []

    with Client.connect(host, port, token=token) as bridge:
        bridge.hello(agent_name="replay-verify", capabilities=caps)
        for cmd in cmds:
            c = cmd.get("cmd", "")
            if c in {"hello", "quit"}:
                continue
            if c == "snapshot_hash":
                h = bridge.snapshot_hash()
                actual_hashes.append(h)
                continue
            if c == "set_seed":
                bridge.set_seed(int(cmd.get("seed", 0)))
                continue
            if c == "step":
                bridge.step(int(cmd.get("frames", 1)))
                continue
            if c == "action":
                try:
                    bridge.action(str(cmd.get("name", "")), cmd.get("value"))
                except Exception:
                    pass
                continue
        try:
            bridge.quit()
        except Exception:
            pass

    n = min(len(expected_hashes), len(actual_hashes))
    for i in range(n):
        if expected_hashes[i] == actual_hashes[i]:
            report.matches += 1
        else:
            report.diverged += 1
            if report.first_divergence_at is None:
                report.first_divergence_at = i
    report.expected = expected_hashes
    report.actual = actual_hashes
    return report
