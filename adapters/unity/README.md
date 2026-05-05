# AgentBridge Unity adapter

Unity 2022.3+ implementation of the AgentBridge wire protocol v1.0.0.
Mirrors the Godot adapter at
`adapters/godot/addons/agentbridge/agent_bridge.gd`.

## Install via UPM

In your Unity project's `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.kruz.agentbridge": "https://github.com/kjhholt-alt/agentbridge.git?path=adapters/unity/AgentBridge"
  }
}
```

Or copy `adapters/unity/AgentBridge/` into your project's `Packages/`
folder for offline use.

## Usage

1. Add a scene-persistent GameObject (`AgentBridgeRoot` is a good name).
2. Attach the three components:
   - `AgentBridge.AgentBridge` (the listener)
   - `AgentBridge.AgentStateDump` (or your subclass)
   - `AgentBridge.AgentInputDriver` (or your subclass)
3. Tag your player GameObject as `Player` so the default StateDump can
   find it. Or assign `Player` on AgentStateDump in the inspector.
4. Launch Unity with `AGENTBRIDGE=1` set in the process environment.
   The bridge will print `[agentbridge] v1.0.0 listening on
   tcp://127.0.0.1:7777`.
5. The token lives at `<Application.persistentDataPath>/agentbridge.token`.
   Pass it to the Python harness or your own client.

## Ports

The default port is `7777`. Override with `AGENTBRIDGE_PORT=<n>`.

## What the adapter implements

All mandatory verbs (hello, ping, state, action, events, reset, quit,
capabilities) plus the optional capabilities: step (basic via reset
loop), set_seed, snapshot_hash, timescale (via Time.timeScale),
metrics, actions.bind, events.subscribe.

The Unity adapter does NOT implement scene-frame stepping the same
way as Godot; for fully deterministic replay use Time.captureFramerate
+ explicit Update calls in your test runner.

## Conformance

Run the conformance suite (which is engine-agnostic):

```
python ../../spec/conformance/conformance_suite.py \
  --no-launch \
  --port 7777 \
  --token-file <Application.persistentDataPath>/agentbridge.token \
  --adapter-name unity --adapter-version 0.1.0 \
  --report conformance-unity-0.1.0.md
```

## Caveat: extra_state subclassing

For game-specific state (inventory, AI, weapons), subclass
`AgentStateDump` and override `ExtraState()`:

```csharp
public class MyGameState : AgentBridge.AgentStateDump
{
    public override Dictionary<string, object> ExtraState()
    {
        return new Dictionary<string, object>
        {
            ["inventory"] = MyInventory.Snapshot(),
            ["objective"] = MyQuests.Current(),
        };
    }
}
```

Then assign your subclass to `AgentBridge.StateDump` in the inspector.
