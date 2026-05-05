"""AgentBridge conformance suite.

Black-box test runner. Boots a target adapter (subprocess), connects
via TCP, runs every conformance scenario, reports pass/fail with diffs,
emits a markdown report.

Usage:

    python conformance_suite.py \
        --launch 'godot --path /path/to/example --headless res://main.tscn' \
        --token-file /path/to/userdata/agentbridge.token \
        --port 7777 \
        --report conformance-godot-0.1.0.md

This file is the single source of truth for what "compliant" means.
Engines pass the suite by passing every scenario.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_SEC = 10.0


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


class Bridge:
    """Minimal TCP newline-JSON client for conformance tests."""

    def __init__(self, host: str, port: int, timeout: float = DEFAULT_TIMEOUT_SEC) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buffer = b""

    def send(self, obj: dict) -> dict:
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

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    """Wait for the adapter to be ready WITHOUT consuming a session.

    A naive connect-and-close burns a real client slot in adapters that
    treat every accepted connection as a session. Use a non-connecting
    probe via socket.connect_ex with a fresh socket each retry.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            err = s.connect_ex((host, port))
            if err == 0:
                # Fully shutdown so the adapter sees a clean disconnect
                # before we run real scenarios.
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                s.close()
                # Give the adapter a frame to clean up the dummy session.
                time.sleep(0.5)
                return True
        except OSError:
            pass
        finally:
            try: s.close()
            except OSError: pass
        time.sleep(0.4)
    return False


def read_token(token_file: Path | None) -> str:
    if token_file is None:
        return ""
    if not token_file.exists():
        return ""
    return token_file.read_text(encoding="utf-8").strip().splitlines()[0]


def scenarios() -> list[tuple[str, str]]:
    """All scenarios as (name, function-name). Functions are below."""
    return [
        ("handshake_required",         "scn_handshake_required"),
        ("auth_failure",               "scn_auth_failure"),
        ("hello_negotiates_caps",      "scn_hello_negotiates_caps"),
        ("ping_after_hello",           "scn_ping_after_hello"),
        ("state_has_base_keys",        "scn_state_has_base_keys"),
        ("action_unknown_returns_2001","scn_action_unknown"),
        ("sticky_press_release",       "scn_sticky_press_release"),
        ("oneshot_pulse",              "scn_oneshot_pulse"),
        ("look_delta_returns_ok",      "scn_look_delta"),
        ("events_drain",               "scn_events_drain"),
        ("subscribe_unsubscribe",      "scn_subscribe_unsubscribe"),
        ("set_seed_when_negotiated",   "scn_set_seed"),
        ("snapshot_hash_format",       "scn_snapshot_hash_format"),
        ("metrics_returned",           "scn_metrics"),
        ("capabilities_echo",          "scn_capabilities_echo"),
        ("quit_clean_disconnect",      "scn_quit_clean_disconnect"),
    ]


def _hello(b: Bridge, token: str, caps: list[str] | None = None) -> dict:
    msg = {"cmd": "hello", "protocol": "1.0.0", "agent_name": "conformance", "token": token}
    if caps:
        msg["capabilities"] = caps
    return b.send(msg)


def scn_handshake_required(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        r = b.send({"cmd": "ping"})
        if r.get("ok") is False and r.get("code") == 1001:
            return Result("handshake_required", True, "")
        return Result("handshake_required", False, f"expected ok=false code=1001, got {r}")
    finally:
        b.close()


def scn_auth_failure(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        r = _hello(b, token="this-is-a-bogus-token")
        if r.get("ok") is False and r.get("code") == 1002:
            return Result("auth_failure", True, "")
        return Result("auth_failure", False, f"expected code 1002, got {r}")
    finally:
        b.close()


def scn_hello_negotiates_caps(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        r = _hello(b, token, caps=["step", "set_seed", "snapshot_hash"])
        if not r.get("ok"):
            return Result("hello_negotiates_caps", False, f"hello failed: {r}")
        if "session_id" not in r or "server_caps" not in r:
            return Result("hello_negotiates_caps", False, f"missing fields: {r}")
        return Result("hello_negotiates_caps", True,
                      f"caps={r.get('server_caps')[:5]}...")
    finally:
        b.close()


def scn_ping_after_hello(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        r = b.send({"cmd": "ping"})
        if r.get("ok") and r.get("pong") is True:
            return Result("ping_after_hello", True, "")
        return Result("ping_after_hello", False, str(r))
    finally:
        b.close()


def scn_state_has_base_keys(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        r = b.send({"cmd": "state"})
        st = r.get("state", {})
        missing = [k for k in ("player", "time") if k not in st]
        if missing:
            return Result("state_has_base_keys", False, f"missing: {missing}")
        if "position" not in st["player"]:
            return Result("state_has_base_keys", False, "player missing position")
        return Result("state_has_base_keys", True, f"keys={list(st.keys())}")
    finally:
        b.close()


def scn_action_unknown(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        r = b.send({"cmd": "action", "name": "totally_made_up_action"})
        if r.get("ok") is False and r.get("code") == 2001:
            return Result("action_unknown_returns_2001", True, "")
        return Result("action_unknown_returns_2001", False, str(r))
    finally:
        b.close()


def scn_sticky_press_release(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        on = b.send({"cmd": "action", "name": "move_forward", "value": True})
        off = b.send({"cmd": "action", "name": "move_forward", "value": False})
        if on.get("ok") and off.get("ok"):
            return Result("sticky_press_release", True, "")
        return Result("sticky_press_release", False, f"on={on} off={off}")
    finally:
        b.close()


def scn_oneshot_pulse(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        r = b.send({"cmd": "action", "name": "attack"})
        if r.get("ok"):
            return Result("oneshot_pulse", True, "")
        return Result("oneshot_pulse", False, str(r))
    finally:
        b.close()


def scn_look_delta(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        r = b.send({"cmd": "action", "name": "look_yaw_delta", "value": 0.05})
        if r.get("ok"):
            return Result("look_delta_returns_ok", True, "")
        return Result("look_delta_returns_ok", False, str(r))
    finally:
        b.close()


def scn_events_drain(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        r = b.send({"cmd": "events"})
        if not r.get("ok"):
            return Result("events_drain", False, str(r))
        events = r.get("events", [])
        return Result("events_drain", True, f"events={len(events)}")
    finally:
        b.close()


def scn_subscribe_unsubscribe(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token, caps=["events.subscribe"])
        s = b.send({"cmd": "subscribe", "types": ["director_event"]})
        u = b.send({"cmd": "unsubscribe", "types": ["director_event"]})
        if s.get("ok") and u.get("ok"):
            return Result("subscribe_unsubscribe", True, "")
        return Result("subscribe_unsubscribe", False, f"s={s} u={u}")
    finally:
        b.close()


def scn_set_seed(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        h = _hello(b, token, caps=["set_seed"])
        if "set_seed" not in h.get("server_caps", []):
            return Result("set_seed_when_negotiated", True, "adapter does not advertise set_seed; skip")
        r = b.send({"cmd": "set_seed", "seed": 42})
        if r.get("ok") and r.get("seed") == 42:
            return Result("set_seed_when_negotiated", True, "")
        return Result("set_seed_when_negotiated", False, str(r))
    finally:
        b.close()


def scn_snapshot_hash_format(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        h = _hello(b, token, caps=["snapshot_hash"])
        if "snapshot_hash" not in h.get("server_caps", []):
            return Result("snapshot_hash_format", True, "skipped: not advertised")
        r = b.send({"cmd": "snapshot_hash"})
        h = r.get("hash", "")
        if r.get("ok") and isinstance(h, str) and len(h) == 16 and all(c in "0123456789abcdefABCDEF" for c in h):
            return Result("snapshot_hash_format", True, f"hash={h}")
        return Result("snapshot_hash_format", False, str(r))
    finally:
        b.close()


def scn_metrics(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        h = _hello(b, token, caps=["metrics"])
        if "metrics" not in h.get("server_caps", []):
            return Result("metrics_returned", True, "skipped: not advertised")
        r = b.send({"cmd": "metrics"})
        m = r.get("metrics", {})
        required = ["commands_total", "events_emitted", "session_seconds"]
        missing = [k for k in required if k not in m]
        if missing:
            return Result("metrics_returned", False, f"missing keys: {missing}")
        return Result("metrics_returned", True, f"commands_total={m.get('commands_total')}")
    finally:
        b.close()


def scn_capabilities_echo(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        h = _hello(b, token)
        r = b.send({"cmd": "capabilities"})
        if r.get("ok") and isinstance(r.get("capabilities"), list):
            if set(r["capabilities"]) == set(h.get("server_caps", [])):
                return Result("capabilities_echo", True, "")
            return Result("capabilities_echo", False,
                          f"caps differ from hello: {set(r['capabilities']) ^ set(h['server_caps'])}")
        return Result("capabilities_echo", False, str(r))
    finally:
        b.close()


def scn_quit_clean_disconnect(host: str, port: int, token: str) -> Result:
    b = Bridge(host, port)
    try:
        _hello(b, token)
        r = b.send({"cmd": "quit"})
        if not r.get("ok"):
            return Result("quit_clean_disconnect", False, str(r))
        return Result("quit_clean_disconnect", True, "")
    finally:
        b.close()


SCENARIO_FNS: dict[str, callable] = {
    name: globals()[fn_name] for name, fn_name in scenarios()
}


def run_all(host: str, port: int, token: str) -> list[Result]:
    """Run every scenario in sequence.

    Each scenario opens its own connection. We sleep briefly between
    scenarios so the adapter can fully process the disconnect before
    the next connection lands -- otherwise the new client may receive
    the eviction notice from the previous (dying) session.
    """
    results: list[Result] = []
    for name, fn_name in scenarios():
        fn = SCENARIO_FNS[name]
        try:
            r = fn(host, port, token)
        except Exception as e:
            r = Result(name, False, f"exception: {e!r}")
        results.append(r)
        time.sleep(0.25)  # let adapter clean up session before next test
    return results


def write_report(adapter_name: str, version: str, results: list[Result], out_path: Path) -> None:
    lines: list[str] = [
        f"# AgentBridge conformance report",
        "",
        f"adapter: **{adapter_name}** {version}",
        f"date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"protocol: 1.0.0",
        "",
        "| Scenario | Verdict | Detail |",
        "|---|---|---|",
    ]
    pass_count = 0
    for r in results:
        v = "PASS" if r.ok else "FAIL"
        if r.ok:
            pass_count += 1
        lines.append(f"| {r.name} | {v} | {r.detail} |")
    lines.append("")
    lines.append(f"**Score: {pass_count}/{len(results)} passed.**")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--launch", help="shell command to launch adapter (with AGENTBRIDGE=1 already set)")
    p.add_argument("--no-launch", action="store_true",
                   help="adapter is already running; just connect")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7777)
    p.add_argument("--token-file", type=Path)
    p.add_argument("--token", default="")
    p.add_argument("--adapter-name", default="unknown")
    p.add_argument("--adapter-version", default="0.0.0")
    p.add_argument("--report", type=Path, default=Path("conformance-report.md"))
    p.add_argument("--boot-wait-sec", type=float, default=4.0)
    args = p.parse_args()

    proc: subprocess.Popen | None = None
    if not args.no_launch:
        if not args.launch:
            print("[conformance] supply --launch '<command>' or --no-launch", file=sys.stderr)
            return 2
        env = os.environ.copy()
        env["AGENTBRIDGE"] = "1"
        env["AGENTBRIDGE_PORT"] = str(args.port)
        # Use posix=False so Windows paths with backslashes/quotes parse
        # cleanly. Capture launch output to a temp log for debugging.
        argv = shlex.split(args.launch, posix=False)
        # shlex with posix=False keeps quotes; strip them.
        argv = [a.strip('"') for a in argv]
        log_path = Path(os.environ.get("TEMP", "/tmp")) / f"agentbridge_conformance_{args.port}.log"
        log_f = open(log_path, "w", encoding="utf-8")
        print(f"[conformance] launching: {argv}")
        print(f"[conformance] adapter log: {log_path}")
        proc = subprocess.Popen(argv, env=env, stdout=log_f, stderr=subprocess.STDOUT)
        if not wait_for_port(args.host, args.port, args.boot_wait_sec * 2):
            print("[conformance] adapter never started listening", file=sys.stderr)
            print(f"[conformance] see log: {log_path}", file=sys.stderr)
            try: proc.terminate()
            except Exception: pass
            return 1

    token = args.token or read_token(args.token_file)
    if not token:
        print("[conformance] WARNING: no token; auth scenarios will fail")

    print(f"[conformance] running {len(scenarios())} scenarios against {args.host}:{args.port}")
    results = run_all(args.host, args.port, token)
    pass_count = sum(1 for r in results if r.ok)

    write_report(args.adapter_name, args.adapter_version, results, args.report)
    print(f"[conformance] {pass_count}/{len(results)} passed -> {args.report}")
    for r in results:
        symbol = "OK" if r.ok else "XX"
        print(f"  {symbol} {r.name:35s} {r.detail}")

    # Tear down
    if proc is not None:
        try:
            # Send a graceful quit if any
            b = Bridge(args.host, args.port, timeout=2.0)
            try:
                _hello(b, token)
                b.send({"cmd": "quit"})
            except Exception:
                pass
            b.close()
        except Exception:
            pass
        try: proc.terminate(); proc.wait(timeout=4)
        except Exception:
            try: proc.kill()
            except Exception: pass

    return 0 if pass_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
