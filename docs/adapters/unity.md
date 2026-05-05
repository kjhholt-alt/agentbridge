# Unity adapter

Source: [`adapters/unity/AgentBridge/`](https://github.com/kjhholt-alt/agentbridge/tree/master/adapters/unity/AgentBridge).

UPM package targeting Unity 2022.3+. Mirrors the Godot adapter
behavior under the same wire protocol.

## Install

Add to your project's `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.kruz.agentbridge": "https://github.com/kjhholt-alt/agentbridge.git?path=adapters/unity/AgentBridge"
  }
}
```

## Setup

1. Add a scene-persistent GameObject (e.g. `AgentBridgeRoot`).
2. Attach the three components (in this order):
   - `AgentBridge.AgentBridge`
   - `AgentBridge.AgentStateDump`
   - `AgentBridge.AgentInputDriver`
3. Tag your player GameObject as `Player` so the default state dump
   can find it.

## Subclass for game-specific state

```csharp
public class MyGameState : AgentBridge.AgentStateDump
{
    public override Dictionary<string, object> ExtraState()
    {
        return new Dictionary<string, object>
        {
            ["inventory"] = MyInventory.Snapshot(),
            ["weapon"] = MyWeapons.Current(),
        };
    }
}
```

Assign the subclass to `AgentBridge.StateDump` in the inspector.

## Driving InputSystem

`AgentInputDriver.DriveSticky` and `DriveOneShot` are virtual hooks.
Override them to integrate with the new InputSystem:

```csharp
public class MyInputDriver : AgentBridge.AgentInputDriver
{
    protected override void DriveSticky(string inputAction, bool on)
    {
        var action = MyInputActions.asset[inputAction];
        if (on) action.Enable(); else action.Disable();
    }
}
```
