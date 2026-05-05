# AgentBridge

Portable AI playtesting infrastructure for game engines. A TCP+JSON
protocol + reference adapters for Godot and Unity + a Python harness
that drives any compliant adapter through identical missions with
zero engine-specific code.

The same agent script tests a Godot survival horror game and a Unity
roguelike. Drop the addon in. Implement one subclass. Done.

## Status

| Layer | Status |
|---|---|
| Spec v1.0.0 | shipped |
| Godot adapter | Phase 2 |
| Conformance suite | Phase 3 |
| Python harness | Phase 4 |
| Observability | Phase 5 |
| MCP wrapper | Phase 6 |
| Unity adapter | Phase 7 |
| Docs site | Phase 8 |
| QuietWoods migration | Phase 9 |

## Why

Modern game engines do not ship an "AI agent plays my game" tool. Every
project that wants AI playtesting reinvents the same TCP+state+input
loop. AgentBridge is that loop, formalized once, with reference
implementations for the two most common engines plus a Python harness.

Origin: extracted from the QuietWoods agent playtester (v0.2.1), which
proved the loop works end-to-end -- Sonnet 4.6 drives a survival horror
game from a Python CLI, observes state, sends inputs, captures events.

## Quickstart

(Phase 2+. Until then, see `spec/AGENTBRIDGE_SPEC.md` for the protocol.)

```python
from agentbridge import Client

async with Client.connect("127.0.0.1", 7777, token="...") as bridge:
    await bridge.hello(agent_name="my-agent")
    state = await bridge.state()
    await bridge.action("move_forward", value=True)
    events = await bridge.events()
```

## License

MIT. See LICENSE.
