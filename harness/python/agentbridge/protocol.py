"""AgentBridge protocol loader + self-check.

Loads the v1 JSON Schemas from disk, validates them with jsonschema,
parses example fixtures to confirm the schemas accept what the spec
documents.

Run from any cwd:

    python -m agentbridge.protocol --self-check

Returns exit 0 on success, non-zero with a list of failures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    Draft202012Validator = None  # type: ignore
    ValidationError = Exception  # type: ignore


SCHEMA_DIR = Path(__file__).resolve().parents[3] / "spec" / "schema" / "v1"


def _load_schema(name: str) -> dict:
    path = SCHEMA_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_v1_schemas() -> dict[str, dict]:
    """Return all v1 schemas as {name: parsed_dict}."""
    return {
        "commands": _load_schema("commands.json"),
        "responses": _load_schema("responses.json"),
        "events": _load_schema("events.json"),
        "state": _load_schema("state.json"),
    }


def validate_schemas() -> list[str]:
    """Validate that each schema is itself a legal JSON Schema. Returns failure list."""
    if Draft202012Validator is None:
        return ["jsonschema library not installed -- pip install jsonschema"]
    failures: list[str] = []
    schemas = load_v1_schemas()
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as e:
            failures.append(f"{name}: schema invalid: {e!r}")
    return failures


# Fixture documents that the schemas MUST accept (positive cases).
COMMAND_FIXTURES = [
    {"cmd": "ping"},
    {"cmd": "hello", "protocol": "1.0.0", "agent_name": "smoke", "token": "abc123"},
    {"cmd": "hello", "protocol": "1.0.0", "agent_name": "smoke",
     "capabilities": ["step", "set_seed"], "token": "abc123"},
    {"cmd": "state"},
    {"cmd": "action", "name": "move_forward", "value": True},
    {"cmd": "action", "name": "look_yaw_delta", "value": 0.05},
    {"cmd": "action", "name": "attack"},
    {"cmd": "events"},
    {"cmd": "reset"},
    {"cmd": "quit"},
    {"cmd": "capabilities"},
    {"cmd": "subscribe", "types": ["director_event", "region_changed"]},
    {"cmd": "unsubscribe", "types": ["director_event"]},
    {"cmd": "set_seed", "seed": 73104},
    {"cmd": "step", "frames": 60},
    {"cmd": "set_timescale", "scale": 4.0},
    {"cmd": "snapshot_hash"},
    {"cmd": "bind_action", "name": "toss_grenade",
     "input_action": "throw_primary", "kind": "oneshot"},
    {"cmd": "metrics"},
]

# Fixture documents that the schemas MUST REJECT (negative cases).
COMMAND_NEGATIVE_FIXTURES = [
    # missing cmd
    {},
    # bogus cmd value
    {"cmd": "notarealcommand"},
    # action with uppercase name (against the regex)
    {"cmd": "action", "name": "MoveForward", "value": True},
    # set_seed missing required seed
    {"cmd": "set_seed"},
    # step with frames out of range
    {"cmd": "step", "frames": 0},
    # bind_action with bad kind
    {"cmd": "bind_action", "name": "x", "input_action": "y", "kind": "bogus"},
]

RESPONSE_FIXTURES = [
    {"ok": True, "pong": True},
    {"ok": True, "session_id": "s1", "server_caps": ["step"],
     "max_event_buffer": 256, "engine": "godot", "engine_version": "4.6.2"},
    {"ok": True, "state": {"player": {"position": [0.0, 1.8, 0.0]},
                            "time": {"phase": "night"}}},
    {"ok": True, "events": [{"type": "ping_pong", "t": 0.0}]},
    {"ok": True, "hash": "3a7f9b2c8e1d4f60"},
    {"ok": True, "capabilities": ["step", "snapshot_hash"]},
    {"ok": False, "error": "auth", "code": 1002},
]

RESPONSE_NEGATIVE_FIXTURES = [
    # ok=true with no fields ok; but missing ok entirely should fail
    {},
    # ok=false without error
    {"ok": False, "code": 1002},
    # err with extra fields beyond the err shape
    {"ok": False, "error": "x", "code": 1, "rogue_extra": True},
    # bad hash format
    {"ok": True, "hash": "nothex"},
]

EVENT_FIXTURES = [
    {"type": "poi_entered", "name": "Cabin", "t": 1.2},
    {"type": "director_event", "id": "growl_drift",
     "payload": {"reason": "loneliness"}, "t": 32.41},
    {"type": "region_changed", "id": "the_hollow",
     "name": "The Hollow", "t": 18.7},
]

EVENT_NEGATIVE_FIXTURES = [
    # missing type
    {"t": 0.0},
    # missing t
    {"type": "ping"},
    # type empty string
    {"type": "", "t": 0.0},
]

STATE_FIXTURES = [
    {
        "player": {
            "position": [0.0, 1.8, 0.0],
            "yaw": 0.0,
            "hp": 100.0,
        },
        "time": {"phase": "night", "day": 1, "session_seconds": 12.5}
    },
    {
        "player": {"position": [-50.0, 0.0, 50.0]},
        "time": {},
        "extra_engine_specific_field": {"foo": "bar"}
    }
]

STATE_NEGATIVE_FIXTURES = [
    # missing player
    {"time": {}},
    # player without position
    {"player": {"hp": 100.0}, "time": {}},
    # position too short
    {"player": {"position": [0.0, 1.8]}, "time": {}}
]


def validate_fixtures() -> list[str]:
    failures: list[str] = []
    if Draft202012Validator is None:
        return ["jsonschema library not installed"]
    schemas = load_v1_schemas()
    cmd_v = Draft202012Validator(schemas["commands"])
    rsp_v = Draft202012Validator(schemas["responses"])
    evt_v = Draft202012Validator(schemas["events"])
    sta_v = Draft202012Validator(schemas["state"])

    for fx in COMMAND_FIXTURES:
        errs = list(cmd_v.iter_errors(fx))
        if errs:
            failures.append(f"command-positive {fx!r}: rejected: {errs[0].message}")
    for fx in COMMAND_NEGATIVE_FIXTURES:
        errs = list(cmd_v.iter_errors(fx))
        if not errs:
            failures.append(f"command-negative {fx!r}: incorrectly accepted")
    for fx in RESPONSE_FIXTURES:
        errs = list(rsp_v.iter_errors(fx))
        if errs:
            failures.append(f"response-positive {fx!r}: rejected: {errs[0].message}")
    for fx in RESPONSE_NEGATIVE_FIXTURES:
        errs = list(rsp_v.iter_errors(fx))
        if not errs:
            failures.append(f"response-negative {fx!r}: incorrectly accepted")
    for fx in EVENT_FIXTURES:
        errs = list(evt_v.iter_errors(fx))
        if errs:
            failures.append(f"event-positive {fx!r}: rejected: {errs[0].message}")
    for fx in EVENT_NEGATIVE_FIXTURES:
        errs = list(evt_v.iter_errors(fx))
        if not errs:
            failures.append(f"event-negative {fx!r}: incorrectly accepted")
    for fx in STATE_FIXTURES:
        errs = list(sta_v.iter_errors(fx))
        if errs:
            failures.append(f"state-positive {fx!r}: rejected: {errs[0].message}")
    for fx in STATE_NEGATIVE_FIXTURES:
        errs = list(sta_v.iter_errors(fx))
        if not errs:
            failures.append(f"state-negative {fx!r}: incorrectly accepted")

    return failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AgentBridge protocol self-check")
    p.add_argument("--self-check", action="store_true",
                   help="validate schemas + run positive/negative fixtures")
    p.add_argument("--list-schemas", action="store_true",
                   help="print loaded schema names + sizes")
    args = p.parse_args(argv)

    if args.list_schemas:
        for name, schema in load_v1_schemas().items():
            print(f"{name:12s} {len(json.dumps(schema)):>6d} bytes  $id={schema.get('$id','')}")
        return 0

    if args.self_check or argv is None:
        schema_failures = validate_schemas()
        if schema_failures:
            print("[protocol] schema validation FAILED:", file=sys.stderr)
            for f in schema_failures:
                print(f"  - {f}", file=sys.stderr)
            return 1
        fixture_failures = validate_fixtures()
        if fixture_failures:
            print("[protocol] fixture validation FAILED:", file=sys.stderr)
            for f in fixture_failures:
                print(f"  - {f}", file=sys.stderr)
            return 1
        n_pos = (len(COMMAND_FIXTURES) + len(RESPONSE_FIXTURES)
                 + len(EVENT_FIXTURES) + len(STATE_FIXTURES))
        n_neg = (len(COMMAND_NEGATIVE_FIXTURES) + len(RESPONSE_NEGATIVE_FIXTURES)
                 + len(EVENT_NEGATIVE_FIXTURES) + len(STATE_NEGATIVE_FIXTURES))
        print(f"[protocol] self-check OK -- 4 schemas validated, "
              f"{n_pos} positive + {n_neg} negative fixtures all green")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
