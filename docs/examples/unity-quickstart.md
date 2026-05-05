# Unity quickstart

5-minute path from package install to first agent-driven action.

## Prerequisites

- Unity 2022.3+
- Python 3.11+

## 1. Install the package

In your Unity project's `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.kruz.agentbridge": "https://github.com/kjhholt-alt/agentbridge.git?path=adapters/unity/AgentBridge"
  }
}
```

Reload Unity. The package shows in Window -> Package Manager.

## 2. Add the bridge components

1. Create a scene-persistent GameObject named `AgentBridgeRoot`.
2. Add the three components:
   - `AgentBridge.AgentBridge`
   - `AgentBridge.AgentStateDump`
   - `AgentBridge.AgentInputDriver`
3. Tag your player as `Player`.

## 3. Build a headless variant (optional but recommended)

Unity Editor mode also works for testing. For CI/automation, build a
Linux/Windows headless server build.

## 4. Launch with the bridge

```bash
AGENTBRIDGE=1 AGENTBRIDGE_PORT=7777 \
  YourGame.exe -batchmode -nographics
```

The Unity console shows:

```
[agentbridge] v1.0.0 listening on tcp://127.0.0.1:7777
```

## 5. Drive it

```python
from pathlib import Path
from agentbridge import Client

token = Path.home().joinpath('AppData/LocalLow/<Company>/<Game>/agentbridge.token').read_text().strip()

with Client.connect('127.0.0.1', 7777, token=token) as c:
    h = c.hello(agent_name='quickstart')
    print(h.engine, h.engine_version)
    print(c.state())
    c.quit()
```

Expected:

```
unity 2022.3.x
{'player': {'position': [...]}, 'time': {...}, 'ticks': N}
```
