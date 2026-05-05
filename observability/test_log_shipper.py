"""Tests for log_shipper. Uses DRYRUN webhook so no network calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import log_shipper


def test_make_embed_skips_non_event_lines():
    assert log_shipper.make_embed({"dir": "in", "line": {"cmd": "ping"}}) is None


def test_make_embed_skips_unkeyed_event_types():
    assert log_shipper.make_embed({"dir": "event", "line": {"type": "client_connected"}}) is None


def test_make_embed_for_director_event():
    embed = log_shipper.make_embed({
        "dir": "event",
        "line": {"type": "director_event", "id": "growl_drift",
                 "payload": {"reason": "loneliness"}},
    })
    assert embed is not None
    assert embed["title"] == "agentbridge :: director_event"
    assert "growl_drift" in embed["description"]


def test_once_ships_only_key_events(tmp_path: Path):
    log = tmp_path / "session.ndjson"
    lines = [
        {"dir": "in", "line": {"cmd": "ping"}},
        {"dir": "event", "line": {"type": "client_connected"}},
        {"dir": "event", "line": {"type": "director_event", "id": "wave_spawn"}},
        {"dir": "event", "line": {"type": "mission_complete", "score": 7}},
        {"dir": "out", "line": {"ok": True}},
    ]
    log.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    rc = log_shipper.once(log, "DRYRUN")
    assert rc == 0
