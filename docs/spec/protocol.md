# Wire protocol v1.0.0

Source of truth: [`spec/AGENTBRIDGE_SPEC.md`](https://github.com/kjhholt-alt/agentbridge/blob/master/spec/AGENTBRIDGE_SPEC.md).

This page is a friendly tour of the canonical spec. Read this first;
read the spec when you need to implement an adapter or write a
non-Python client.

## Three primitives

1. **Handshake + auth**. Client sends `hello` with a per-launch token.
2. **State + actions**. Client polls `state`, sends `action` commands.
3. **Events**. Client drains `events` (or subscribes via
   `subscribe`).

Add deterministic primitives via capability negotiation: `set_seed`,
`step`, `snapshot_hash`, `timescale`. These let you replay sessions
byte-for-byte.

## Why TCP + NDJSON?

- Universally supported in every game engine + every language.
- Newline-delimited JSON is human-readable in tcpdump.
- No schemas to compile -- every line is self-describing.
- Async-friendly (line oriented).

WebSocket and stdio are alternative transports declared via
capabilities `transport.websocket` and `transport.stdio`.
