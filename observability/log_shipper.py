"""AgentBridge log shipper.

Tails an adapter's session NDJSON, fans key event types as Discord
embeds via the configured webhook. Optionally reposts the whole thing
to operator-core's Discord routing.

Routes:
  regression_failed   -- replay verifier diverged
  replay_diverged     -- explicit divergence event
  mission_complete    -- a successful run wrapped
  agent_killed        -- exception/disconnect mid-mission
  director_event      -- pacing-relevant moments

Usage:
    python log_shipper.py --watch <ndjson_path> --webhook <discord_url>
    python log_shipper.py --once <ndjson_path> --webhook <url>  (one-shot summary)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KEY_TYPES: set[str] = {
    "regression_failed", "replay_diverged", "mission_complete",
    "agent_killed", "director_event", "extracted",
    "player_died", "client_evicted",
}


def _post(webhook: str, embed: dict) -> int:
    """Post a Discord webhook embed. Returns HTTP code (0 if dryrun)."""
    if webhook == "DRYRUN":
        print(f"[shipper] DRYRUN webhook embed: {json.dumps(embed)[:200]}")
        return 0
    body = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(webhook, data=body,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print(f"[shipper] webhook error: {e!r}", file=sys.stderr)
        return -1


def make_embed(line: dict) -> dict | None:
    if line.get("dir") != "event":
        return None
    payload = line.get("line", {})
    t = payload.get("type", "")
    if t not in KEY_TYPES:
        return None
    color = {
        "regression_failed": 0xC0432A,
        "replay_diverged":   0xC0432A,
        "agent_killed":      0xE1B365,
        "player_died":       0xE1B365,
        "client_evicted":    0xE1B365,
        "mission_complete":  0x9ED084,
        "extracted":         0x9ED084,
        "director_event":    0x7EC0D6,
    }.get(t, 0xCCCCCC)
    title = f"agentbridge :: {t}"
    desc_parts: list[str] = []
    for k, v in payload.items():
        if k == "type":
            continue
        if isinstance(v, (str, int, float, bool)):
            desc_parts.append(f"**{k}** {v}")
        elif isinstance(v, dict):
            for kk, vv in v.items():
                desc_parts.append(f"**{k}.{kk}** {vv}")
    return {
        "title": title,
        "description": "\n".join(desc_parts) if desc_parts else "(no payload)",
        "color": color,
    }


def ship_one(line: str, webhook: str) -> int:
    try:
        entry = json.loads(line)
    except Exception:
        return -1
    embed = make_embed(entry)
    if embed is None:
        return 0
    return _post(webhook, embed)


def watch(path: Path, webhook: str) -> int:
    if not path.exists():
        print(f"[shipper] {path} does not exist; will wait", file=sys.stderr)
    while not path.exists():
        time.sleep(1.0)
    pos = 0
    posted = 0
    print(f"[shipper] watching {path} -> {webhook}")
    while True:
        try:
            with path.open("r", encoding="utf-8") as f:
                f.seek(pos)
                line = f.readline()
                while line:
                    if line.endswith("\n"):
                        rc = ship_one(line.rstrip("\n"), webhook)
                        if rc and 200 <= rc < 300:
                            posted += 1
                        pos = f.tell()
                    else:
                        # partial line; back off and retry
                        break
                    line = f.readline()
        except FileNotFoundError:
            time.sleep(1.0)
            continue
        time.sleep(0.5)


def once(path: Path, webhook: str) -> int:
    if not path.exists():
        print(f"[shipper] {path} not found", file=sys.stderr)
        return 1
    posted = 0
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            rc = ship_one(raw.rstrip("\n"), webhook)
            if rc and 200 <= rc < 300:
                posted += 1
            elif rc == 0 and webhook == "DRYRUN":
                posted += 1
    print(f"[shipper] one-shot complete: {posted} embeds posted")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--watch", type=Path, help="tail ndjson and ship as it grows")
    g.add_argument("--once", type=Path, help="ship existing ndjson once and exit")
    p.add_argument("--webhook", default=os.environ.get("AGENTBRIDGE_DISCORD_WEBHOOK", "DRYRUN"),
                   help="Discord webhook URL or 'DRYRUN' for stdout")
    args = p.parse_args()
    if args.watch:
        return watch(args.watch, args.webhook)
    return once(args.once, args.webhook)


if __name__ == "__main__":
    sys.exit(main())
