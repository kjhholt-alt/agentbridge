# AgentBridge

Portable AI playtesting infrastructure for game engines.

A spec, two reference adapters (Godot, Unity), a Python harness, and
an MCP wrapper. The same agent script tests a Godot survival horror
game and a Unity roguelike. Drop the adapter in. Implement one
subclass. Done.

## Why this exists

Modern game engines do not ship an "AI agent plays my game" tool.
Every project that wants AI playtesting reinvents the same TCP+state+
input loop. AgentBridge is that loop, formalized once.

## Status (2026-05-05)

| Layer | Status |
|---|---|
| Spec v1.0.0 | shipped (`spec-v1.0.0` tag) |
| Godot adapter | shipped (16/16 conformance) |
| Conformance suite | shipped (Python, engine-agnostic) |
| Python harness | shipped (34/34 pytest) |
| Observability | shipped (4/4 pytest) |
| MCP wrapper | shipped (6/6 pytest) |
| Unity adapter | code shipped; Kruz-side compile + conformance |
| Docs site | this is it |
| QuietWoods migration | Phase 9 |

## Five-minute quickstart

```bash
# 1. Clone
git clone https://github.com/kjhholt-alt/agentbridge
cd agentbridge

# 2. Install harness
pip install -e harness/python

# 3. Drop the addon into a Godot 4.6 project
cp -r adapters/godot/addons/agentbridge \
      /path/to/your/godot/project/addons/

# 4. Add an AgentBridge node to a scene + a player in the "player" group

# 5. Launch with the bridge
AGENTBRIDGE=1 godot --path /path/to/your/godot/project --headless res://main.tscn

# 6. Drive it from Python
python -c "
from agentbridge import Client
from pathlib import Path
token = Path('<userdata>/agentbridge.token').read_text().strip()
with Client.connect('127.0.0.1', 7777, token=token) as c:
    c.hello(agent_name='quickstart', capabilities=['step','snapshot_hash'])
    print(c.state())
    c.action('move_forward', value=True)
    c.action('move_forward', value=False)
    print(c.events())
    c.quit()
"
```

That's the entire integration: 6 steps, ~5 minutes for someone who
already has a Godot project running.

## Where to next

- **[Wire protocol](spec/protocol.md)** -- read this first to
  understand the contract any adapter implements.
- **[Godot quickstart](examples/godot-quickstart.md)** -- the path
  most users take.
- **[Replay verification](harness/replay.md)** -- the "this run
  reproduces" guarantee that most bug-hunting needs.
