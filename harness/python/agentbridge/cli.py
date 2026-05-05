"""AgentBridge CLI -- `agentbridge <subcommand>`.

Subcommands:
    run     -- run a single mission against a launched or running adapter
    replay  -- verify a recorded session by replaying it against a fresh adapter
    sweep   -- parametric sweep (stub for Phase 5+)
    ci      -- run a regression suite from yaml (stub for Phase 5+)
    self-check -- run protocol.py self-check
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from . import protocol
from .client import Client
from .replay import verify, DivergenceReport


def cmd_run(args: argparse.Namespace) -> int:
    proc = None
    if args.launch:
        env = os.environ.copy()
        env["AGENTBRIDGE"] = "1"
        env["AGENTBRIDGE_PORT"] = str(args.port)
        argv = shlex.split(args.launch, posix=False)
        argv = [a.strip('"') for a in argv]
        proc = subprocess.Popen(argv, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(args.boot_wait)
    token = ""
    if args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip().splitlines()[0]
    elif args.token:
        token = args.token
    try:
        with Client.connect(args.host, args.port, token=token) as bridge:
            hello = bridge.hello(agent_name=args.agent_name,
                                  capabilities=args.cap or [])
            print(f"[run] connected: engine={hello.engine} {hello.engine_version}, "
                  f"session={hello.session_id}, caps={hello.server_caps}")
            if args.mission:
                # Delegate to playtest_agent.py if available; else execute
                # the simple no-op mission (user can extend).
                print("[run] mission mode requires the LLM agent, see "
                      "agents/playtester/playtest_agent.py")
            elif args.script:
                steps = json.loads(Path(args.script).read_text())
                for step in steps:
                    name = step.get("action") or step.get("name")
                    value = step.get("value")
                    bridge.action(name, value)
                    time.sleep(float(step.get("duration", 0.1)))
            else:
                print("[run] supply --mission or --script (or just --hello)")
                bridge.quit()
                return 0
            bridge.quit()
    finally:
        if proc is not None:
            try: proc.terminate(); proc.wait(timeout=4)
            except Exception:
                try: proc.kill()
                except Exception: pass
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    token = ""
    if args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip().splitlines()[0]
    elif args.token:
        token = args.token
    report: DivergenceReport = verify(
        args.host, args.port, token, Path(args.path),
        capabilities=args.cap or ["set_seed", "snapshot_hash", "step"],
    )
    print(f"[replay] matches={report.matches} diverged={report.diverged}")
    if report.diverged:
        print(f"[replay] first divergence at index {report.first_divergence_at}")
        print(f"  expected: {report.expected[report.first_divergence_at]}")
        print(f"  actual:   {report.actual[report.first_divergence_at]}")
        return 1
    if report.matches == 0:
        print("[replay] no comparable hashes found in the recording")
        return 2
    print("[replay] DETERMINISTIC")
    return 0


def cmd_self_check(_args: argparse.Namespace) -> int:
    return protocol.main(["--self-check"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agentbridge")
    subs = p.add_subparsers(dest="cmd", required=True)

    pr = subs.add_parser("run", help="run a single mission/script")
    pr.add_argument("--host", default="127.0.0.1")
    pr.add_argument("--port", type=int, default=7777)
    pr.add_argument("--token")
    pr.add_argument("--token-file")
    pr.add_argument("--launch", help="optional adapter launch command")
    pr.add_argument("--boot-wait", type=float, default=4.0)
    pr.add_argument("--agent-name", default="cli")
    pr.add_argument("--cap", action="append", help="capability to negotiate; repeatable")
    pr.add_argument("--mission", help="natural-language mission (LLM agent)")
    pr.add_argument("--script", help="path to a JSON action script")
    pr.set_defaults(func=cmd_run)

    pp = subs.add_parser("replay", help="verify a recorded session is deterministic")
    pp.add_argument("path", help="path to the adapter's ndjson recording")
    pp.add_argument("--host", default="127.0.0.1")
    pp.add_argument("--port", type=int, default=7777)
    pp.add_argument("--token")
    pp.add_argument("--token-file")
    pp.add_argument("--cap", action="append")
    pp.set_defaults(func=cmd_replay)

    pc = subs.add_parser("self-check", help="validate schemas + run fixtures")
    pc.set_defaults(func=cmd_self_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
