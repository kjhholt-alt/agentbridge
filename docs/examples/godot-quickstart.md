# Godot quickstart

5-minute path from clone to first agent-driven action.

## Prerequisites

- Godot 4.6.2-stable
- Python 3.11+

## 1. Clone the repo

```bash
git clone https://github.com/kjhholt-alt/agentbridge
cd agentbridge
```

## 2. Install the harness

```bash
pip install -e harness/python
```

## 3. Open the minimal example

```bash
godot --path adapters/godot/examples/minimal_godot_project
```

Verify the addon shows up as enabled in Project Settings -> Plugins.

## 4. Boot with the bridge

```bash
AGENTBRIDGE=1 AGENTBRIDGE_PORT=7777 \
  godot --path adapters/godot/examples/minimal_godot_project \
  --headless res://main.tscn
```

You should see:

```
[agentbridge] v1.0.0 listening on tcp://127.0.0.1:7777
```

## 5. Drive it

In another terminal:

```bash
python -c "
from pathlib import Path
from agentbridge import Client

# On Windows: %APPDATA%/Godot/app_userdata/<project>/agentbridge.token
token = Path.home().joinpath('AppData/Roaming/Godot/app_userdata/AgentBridge Minimal/agentbridge.token').read_text().strip()

with Client.connect('127.0.0.1', 7777, token=token) as c:
    h = c.hello(agent_name='quickstart', capabilities=['snapshot_hash'])
    print('engine:', h.engine, h.engine_version)
    print('session:', h.session_id)
    print('state keys:', list(c.state().keys()))
    print('hash:', c.snapshot_hash())
    c.quit()
"
```

Expected output:

```
engine: godot 4.6.2-stable (official)
session: sess-<n>-<m>
state keys: ['player', 'ticks', 'time']
hash: <16 hex chars>
```

You're now driving Godot from Python. Anything more is just more
verbs and more state.

## Next steps

- Subclass `AgentStateDump` to expose your game's state.
- Run the conformance suite to verify your adapter integration.
- Read [Replay verification](../harness/replay.md) to add
  determinism testing to CI.
