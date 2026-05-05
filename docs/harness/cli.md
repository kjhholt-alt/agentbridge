# CLI

After `pip install -e harness/python`, `agentbridge` is on PATH.

## Subcommands

| Command | Purpose |
|---|---|
| `agentbridge run` | run a single mission against a launched or running adapter |
| `agentbridge replay <ndjson>` | verify recorded session is deterministic |
| `agentbridge self-check` | validate spec schemas + run fixtures |

## Examples

```bash
# self-check (no adapter required)
agentbridge self-check

# run a scripted mission
agentbridge run \
  --port 7777 \
  --token-file <userdata>/agentbridge.token \
  --script my_script.json

# replay verification
agentbridge replay session_123.ndjson \
  --port 7777 \
  --token-file <userdata>/agentbridge.token
```
