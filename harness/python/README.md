# agentbridge — python harness

Spec-validated client + replay + orchestrator for AI playtesting any
AgentBridge-compliant game adapter (Godot, Unity).

This is the Python sub-package. See the [project root README](https://github.com/kjhholt-alt/agentbridge#readme)
for the full spec, adapter docs, and conformance details.

## Install

```bash
pip install agentbridge          # once published to PyPI
# or
pip install -e .[dev]            # from this directory, in a clone
```

## Quick start

```python
from agentbridge import Client

client = Client(adapter_url="http://localhost:7700")
session = client.start_session()
client.send("look around")
print(client.last_response())
```

See the project root for full docs.
