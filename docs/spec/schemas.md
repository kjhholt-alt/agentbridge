# JSON schemas

All four v1 schemas live at
[`spec/schema/v1/`](https://github.com/kjhholt-alt/agentbridge/tree/master/spec/schema/v1).

| Schema | Purpose |
|---|---|
| `commands.json` | Every JSON line sent client -> adapter |
| `responses.json` | Every JSON line sent adapter -> client |
| `events.json` | Every event entry returned by `events` |
| `state.json` | Base shape every adapter MUST emit on `state` |

## Validate locally

```bash
pip install jsonschema
python -m agentbridge.protocol --self-check
```

Self-check loads all 4 schemas, runs 31 positive + 16 negative
fixtures, exits 0 if everything matches the spec.

## Backwards compat

After v1.0.0, schema changes are additive only. Major version bumps
require a new `schema/v2/` directory while keeping v1 served for at
least 12 months. Adapters MAY support multiple protocol versions
concurrently.
