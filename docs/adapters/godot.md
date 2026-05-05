# Godot adapter

Source: [`adapters/godot/addons/agentbridge/`](https://github.com/kjhholt-alt/agentbridge/tree/master/adapters/godot/addons/agentbridge).

A self-contained Godot 4.6 addon. Drop it into your project's
`addons/` directory, enable the plugin, add an `AgentBridge` node to
a scene, and launch with `AGENTBRIDGE=1` set.

## Install

1. Copy `adapters/godot/addons/agentbridge/` into `<your-project>/addons/`.
2. Open Project Settings -> Plugins, enable `AgentBridge`.
3. Add a `Node` to your scene, attach
   `res://addons/agentbridge/agent_bridge.gd`. Name it `AgentBridge`.
4. Add a sibling `Node` with `agent_state_dump.gd` (default state
   dump returns `player` + `time`).
5. Add a sibling `Node` with `agent_input_driver.gd` and call
   `register_default_actions()` from `_ready`.

## Subclass for game-specific state

Most games will subclass `AgentStateDump`:

```gdscript
extends AgentStateDump
class_name MyGameStateDump

func extra_state() -> Dictionary:
    return {
        "inventory": MyInventory.snapshot(),
        "objective": MyQuests.current(),
        "director": {"threat": Director.threat_level()},
    }
```

Then point the AgentBridge node's state_dump at your subclass instead
of the default.

## Verify

After install:

```bash
AGENTBRIDGE=1 godot --path . --headless res://main.tscn
# In another shell:
python ../../../spec/conformance/conformance_suite.py \
  --no-launch --port 7777 \
  --token-file <userdata>/agentbridge.token \
  --adapter-name godot --adapter-version 0.1.0
```

Expect 16/16 PASS.
