# Python harness

Install:

```bash
pip install -e harness/python
```

## Sync client

```python
from agentbridge import Client
from pathlib import Path

token = Path("<userdata>/agentbridge.token").read_text().strip()
with Client.connect("127.0.0.1", 7777, token=token) as c:
    h = c.hello(agent_name="my-script",
                capabilities=["set_seed", "snapshot_hash"])
    print(h.engine, h.engine_version, h.session_id)
    state = c.state()
    c.action("move_forward", value=True)
    c.action("move_forward", value=False)
    events = c.events()
    c.quit()
```

## Async client

```python
import asyncio
from agentbridge import AsyncClient

async def main():
    c = await AsyncClient.connect("127.0.0.1", 7777, token="...")
    await c.hello("agent")
    print(await c.state())
    await c.quit()
    await c.close()

asyncio.run(main())
```

## Replay verifier

```python
from pathlib import Path
from agentbridge import verify

report = verify("127.0.0.1", 7777, token="...",
                recorded_path=Path("session.ndjson"))
assert report.deterministic, f"diverged at {report.first_divergence_at}"
```

The verifier replays the recorded inputs against a fresh adapter,
comparing `snapshot_hash` sequences. Divergence indicates a real
non-determinism bug.

## Coverage

Phase 4 ships the client + replay + orchestrator + CLI. Test
coverage is on the public API; conformance is the integration test.
