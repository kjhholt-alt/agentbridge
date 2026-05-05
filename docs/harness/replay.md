# Replay verification

The most useful guarantee AgentBridge provides: **the same inputs in
the same world produce the same outputs**. Every regression hunt
benefits from this.

## How it works

1. Start a session against the adapter with the `replay` capability
   negotiated. The adapter writes every command + response + event
   to `<userdata>/agentbridge/<session_id>.ndjson`.
2. Run any agent (mission / script / human) to drive a meaningful
   sequence. Periodically call `snapshot_hash` -- those hashes are
   the ground truth.
3. After the session, copy the ndjson somewhere stable.
4. Run `agentbridge replay <ndjson>` against a fresh adapter (with
   `set_seed` + `snapshot_hash` capabilities). The harness replays
   the inputs and asserts the snapshot hashes match.

## Determinism is opt-in

The base `AgentStateDump` includes timestamps in `time`, which makes
hashes drift across runs by design. For deterministic replay:

- Game uses `set_seed` to reset all PRNGs.
- State dump excludes wall-clock fields (override `_time_dump` in
  Godot, `TimeDump` in Unity).
- All non-seeded inputs (camera shake amplitudes, particle emit
  rates) are seeded.

Then `snapshot_hash` is byte-stable for the same inputs.

## Catching regression

Drop the previous-known-good ndjson in your CI tree. Every PR runs
`agentbridge replay <recorded>.ndjson`. If a code change breaks
determinism, the divergence index points to the exact step.
