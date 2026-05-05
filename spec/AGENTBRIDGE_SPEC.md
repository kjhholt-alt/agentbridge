# AgentBridge Wire Protocol

**Version:** 1.0.0
**Status:** stable
**Last revision:** 2026-05-05

This document is the source of truth for the AgentBridge wire
protocol. Adapters and clients that conform to this spec
interoperate without engine-specific knowledge.

## 1. Goals

- Allow an external process (the *agent*) to drive a running game
  (the *adapter*) over a localhost TCP connection.
- Be engine-agnostic: a single agent script must drive Godot, Unity,
  Bevy, web, or terminal games equally.
- Be deterministic-friendly: protocol supports seeded simulation,
  fixed-step advancement, and replay validation.
- Be safe by default: localhost-only, env-gated, token-authenticated.
- Be backwards-compatible forever after v1.0.0.

## 2. Transport

- **Mandatory:** TCP, line-delimited JSON (NDJSON). One JSON object
  per line, terminated by `\n` (LF, not CRLF). UTF-8 encoded.
- **Optional:** WebSocket (capability `transport.websocket`) and
  stdio (capability `transport.stdio`, used by the MCP wrapper).
- Adapter binds to `127.0.0.1` only. Never bind a public interface.
- Adapter binds only when the environment variable `AGENTBRIDGE=1`
  is set. This prevents accidental listeners during normal headless
  test runs.
- Default port: `7777`. Override via env `AGENTBRIDGE_PORT`.

## 3. Session lifecycle

```
client                                       adapter
  |                                              |
  |-- TCP connect 127.0.0.1:7777 ------------>   |
  |                                              |
  |-- {"cmd":"hello","protocol":"1.0.0",          |
  |    "agent_name":"playtester",                 |
  |    "capabilities":["replay","step"],          |
  |    "token":"<token>"} ------------------>    |
  |                                              |
  |   <----------- {"ok":true,                    |
  |                 "server_caps":["step",        |
  |                                "snapshot_hash"|
  |                                "replay"],     |
  |                 "session_id":"sess-...",      |
  |                 "max_event_buffer":256,       |
  |                 "schema_url":"...",           |
  |                 "engine":"godot",             |
  |                 "engine_version":"4.6.2"}     |
  |                                              |
  |-- {"cmd":"state"} ----------------------->   |
  |   <-------------- {"ok":true,"state":{...}}  |
  |                                              |
  |-- ... regular commands ...                   |
  |                                              |
  |-- {"cmd":"quit"} ------------------------>   |
  |   <-------------- {"ok":true}                |
  |   ... TCP closes ...                         |
```

The adapter MUST respond to `hello` before any other command. Any
command before `hello` returns error code 1001 ("handshake
required").

## 4. Authentication

A per-launch random token is written to a project-local file:

| OS | Path |
|---|---|
| Windows | `%APPDATA%\<project>\agentbridge.token` (Godot uses `user://agentbridge.token`) |
| macOS | `~/Library/Application Support/<project>/agentbridge.token` |
| Linux | `~/.local/share/<project>/agentbridge.token` |

The file is created on adapter start with mode `0600` and contains a
single line: 32+ random alphanumeric characters.

The client reads the token, includes it in `hello.token`. Any other
command may also carry `token` (recommended for long-lived sessions
where the server might rotate). Mismatched token returns error
code 1002 ("auth") and the adapter MUST disconnect within 1 second.

## 5. Commands

All commands are JSON objects with at least a `cmd` field. Optional
`token` field carries the auth token. Optional `id` field carries an
opaque correlation ID echoed in the response.

### 5.1 Mandatory commands (every adapter MUST implement)

#### `hello`
```json
{"cmd":"hello","protocol":"1.0.0","agent_name":"playtester",
 "capabilities":["replay"],"token":"<token>"}
```

Response:
```json
{"ok":true,"server_caps":["step","snapshot_hash"],
 "session_id":"sess-1234","max_event_buffer":256,
 "schema_url":"https://agentbridge.dev/schema/v1",
 "engine":"godot","engine_version":"4.6.2"}
```

The intersection of client `capabilities` and adapter `server_caps`
defines what the session can do.

#### `ping`
```json
{"cmd":"ping"}
```
Response: `{"ok":true,"pong":true}`. Used for liveness checks.

#### `state`
```json
{"cmd":"state"}
```
Response: `{"ok":true,"state":{...}}`. The state object conforms to
`schema/v1/state.json`. Engines MUST include the base keys
(`player`, `time`) and MAY add their own keys (state shape is
extensible).

#### `action`
```json
{"cmd":"action","name":"move_forward","value":true}
```
Response: `{"ok":true}` or `{"ok":false,"error":"...","code":N}`.
See section 6 for the action vocabulary.

#### `events`
```json
{"cmd":"events"}
```
Response:
```json
{"ok":true,"events":[
  {"type":"director_event","id":"growl_drift","payload":{...},"t":32.41}
]}
```
Drains accumulated events (FIFO order) and returns them. Events are
described in section 7.

#### `reset`
```json
{"cmd":"reset"}
```
Reloads the current scene. Releases all sticky inputs. Clears event
buffer. Response: `{"ok":true}`.

#### `quit`
```json
{"cmd":"quit"}
```
Adapter shuts down with exit code 0. Response: `{"ok":true}` then
the TCP connection closes.

#### `capabilities`
```json
{"cmd":"capabilities"}
```
Response: `{"ok":true,"capabilities":["step","snapshot_hash",...]}`.
Identical to the `server_caps` field of `hello`. Useful for
re-querying after a `bind_action` registration.

### 5.2 Optional commands (gated by capability)

#### `subscribe` / `unsubscribe` (capability `events.subscribe`)
Client subscribes to specific event types so they push out-of-band
on the same TCP connection (a server-initiated message). When this
capability is not negotiated, clients MUST poll via `events`.

#### `set_seed` (capability `determinism`)
```json
{"cmd":"set_seed","seed":73104}
```
Resets all PRNGs to the given seed. Combined with `step` and
`snapshot_hash`, lets a replay run be byte-identical.

#### `step` (capability `step`)
```json
{"cmd":"step","frames":60}
```
Advances the simulation by `frames` physics frames, blocks until
done, then returns. Combined with `set_timescale`, used for fixed-
budget mission running.

#### `set_timescale` (capability `timescale`)
```json
{"cmd":"set_timescale","scale":4.0}
```
Multiplies the simulation rate. `scale=0` pauses; `scale=4` runs
4x speed. Useful for fast-forwarding deterministic missions.

#### `snapshot_hash` (capability `snapshot_hash`)
```json
{"cmd":"snapshot_hash"}
```
Response: `{"ok":true,"hash":"<hex64>"}`. The hash is a 64-bit FNV
of canonical-keyed JSON state. Two runs with the same seed + same
inputs MUST produce identical sequences of snapshot hashes.

#### `bind_action` (capability `actions.bind`)
```json
{"cmd":"bind_action","name":"toss_grenade",
 "input_action":"throw_primary","kind":"oneshot"}
```
Registers a game-specific action with the input driver. After this,
the agent can call `action` with `name="toss_grenade"`.

#### `metrics` (capability `metrics`)
```json
{"cmd":"metrics"}
```
Response includes rolling counters: actions/sec, latency p50/p99,
events fired, memory usage, current FPS.

## 6. Action vocabulary

Three flavors:

### 6.1 Sticky toggles
Held-state actions. `value:true` activates; `value:false` releases.
Default vocabulary (every adapter that supports movement MUST
implement these names if they exist in the engine):
`move_forward`, `move_back`, `strafe_left`, `strafe_right`, `sprint`,
`crouch_held`, `block`.

### 6.2 One-shot pulses
Single press + release within one frame.
Default vocabulary: `attack`, `interact`, `vault`, `crouch_toggle`,
`pause`, `weapon_1`, `weapon_2`, `weapon_3`, `weapon_4`.

### 6.3 Look deltas
Float radians applied once and cleared.
`look_yaw_delta`, `look_pitch_delta`, `look_roll_delta`.

### 6.4 Game-specific actions
Registered via `bind_action`. Once bound, callable via `action` with
the registered name.

### 6.5 Action namespace rules

- Names are snake_case ASCII, max 48 chars.
- Names beginning with `_` are reserved for adapter internal use.
- Unknown action name -> error code 2001 ("unknown_action").
- Inputs only flow into the simulation while the agent has a live
  session. On disconnect, the adapter MUST release all sticky
  inputs within 100ms.

## 7. Event types

Adapters emit events to a buffer. Clients drain via `events` (or
receive pushed if `events.subscribe` is negotiated).

### 7.1 Reserved (universal) types

- `client_connected` / `client_evicted` -- emitted on join/preempt
- `state_changed` -- generic; carries diff payload
- `action_failed` -- carries name + reason

### 7.2 Suggested (common) types

- `entity_killed` (formerly `infected_killed` in QW)
- `entity_spawned`
- `entity_alerted`
- `region_changed`
- `poi_entered`
- `poi_exited`
- `objective_completed`
- `player_died`
- `extracted` (mission-end success)
- `director_event` -- pacing/AI Director firings

### 7.3 Game-specific types

Engines declare them in `hello.server_caps` as
`event:<type_name>` so clients can filter / subscribe.

### 7.4 Event envelope

Every event has at minimum:
```json
{"type":"<name>","t":<seconds_since_session_start>,
 "session_id":"<sid>"}
```
Plus arbitrary type-specific keys.

Buffer size is bounded by `max_event_buffer` (returned by `hello`).
When full, the OLDEST events are dropped (FIFO eviction). This is
visible to clients via the `events_dropped` counter in `metrics`.

## 8. Error model

All error responses have the shape:
```json
{"ok":false,"error":"<human_readable>","code":<numeric>}
```

Reserved codes:

| Code | Meaning |
|---|---|
| 1000 | unknown_command |
| 1001 | handshake_required |
| 1002 | auth_failed |
| 1003 | protocol_mismatch |
| 1004 | capability_not_negotiated |
| 1005 | rate_limited |
| 2000 | invalid_payload |
| 2001 | unknown_action |
| 2002 | invalid_action_value |
| 2003 | invalid_state_path |
| 3000 | engine_internal |
| 3001 | engine_busy |
| 3002 | engine_paused |
| 4000 | session_terminated |

Codes 5000+ are reserved for game-specific use.

## 9. Capability registry

Capabilities are short stable identifiers. Both client and adapter
declare which they support; the **intersection** is what the session
can use. Clients MUST check `server_caps` from `hello` before using
optional verbs and gracefully degrade.

| Capability | Adds verbs | Notes |
|---|---|---|
| `step` | `step` | deterministic stepping |
| `set_seed` | `set_seed` | reproducibility |
| `snapshot_hash` | `snapshot_hash` | replay validation |
| `timescale` | `set_timescale` | fast-forward |
| `events.subscribe` | `subscribe`/`unsubscribe` | push events |
| `actions.bind` | `bind_action` | dynamic action registry |
| `metrics` | `metrics` | rolling perf counters |
| `replay` | (recording side-effect) | adapter logs to ndjson |
| `transport.websocket` | (alternate transport) | WS upgrade |
| `transport.stdio` | (alternate transport) | for MCP |

Adapters MAY add custom capabilities prefixed with the engine name
(e.g. `godot.scene_reload`).

## 10. Backwards-compatibility policy

After v1.0.0:
- Existing verbs MUST keep working unchanged. Adding optional fields
  to commands or responses is allowed.
- Verb removals are forbidden. Deprecation requires a major version
  bump.
- Breaking schema changes require a major version bump and a new
  `schema/v2/` directory; the old schema MUST stay served for at
  least 12 months.
- Adapters MAY support multiple protocol versions concurrently
  (preferred). Clients announce their version via
  `hello.protocol`; adapter selects the highest version both
  support.

## 11. Replay format

When an adapter has the `replay` capability, every line on the wire
(both directions) is appended to `<userdir>/agentbridge/<session_id>.ndjson`
in this format:

```
{"dir":"in","t":<sec>,"frame":<phys_frame>,"line":{...}}
{"dir":"out","t":<sec>,"frame":<phys_frame>,"line":{...}}
```

The replay is a complete reproduction of the session. Clients can
drive `set_seed -> ... -> snapshot_hash` against the same recording
to verify byte-identical re-runs.

## 12. Worked examples

### 12.1 Minimal session (poll-based)

```
> {"cmd":"hello","protocol":"1.0.0","agent_name":"smoke","token":"abc"}
< {"ok":true,"server_caps":["step","snapshot_hash"],"session_id":"s1",
   "max_event_buffer":256,"engine":"godot","engine_version":"4.6.2"}
> {"cmd":"ping"}
< {"ok":true,"pong":true}
> {"cmd":"state"}
< {"ok":true,"state":{"player":{"position":[0,1.8,0],"hp":100},
                       "time":{"phase":"night","day":1}}}
> {"cmd":"action","name":"move_forward","value":true}
< {"ok":true}
... 2 seconds ...
> {"cmd":"action","name":"move_forward","value":false}
< {"ok":true}
> {"cmd":"events"}
< {"ok":true,"events":[{"type":"poi_entered","name":"Cabin","t":1.2}]}
> {"cmd":"quit"}
< {"ok":true}
```

### 12.2 Deterministic replay validation

```
> {"cmd":"hello","protocol":"1.0.0","agent_name":"replay","capabilities":
   ["step","set_seed","snapshot_hash"],"token":"abc"}
< {"ok":true,"server_caps":["step","set_seed","snapshot_hash"],...}
> {"cmd":"set_seed","seed":42}
< {"ok":true}
> {"cmd":"step","frames":60}
< {"ok":true}
> {"cmd":"snapshot_hash"}
< {"ok":true,"hash":"3a7f9b2c8e1d4f60"}
... rerun with same seed + step ...
> {"cmd":"snapshot_hash"}
< {"ok":true,"hash":"3a7f9b2c8e1d4f60"}   # MUST match
```

### 12.3 Capability degradation

```
> {"cmd":"hello","protocol":"1.0.0","agent_name":"x","capabilities":
   ["step","timescale","ml_export"],"token":"abc"}
< {"ok":true,"server_caps":["step"],...}
# Client sees: timescale + ml_export not granted. Skip those verbs.
```

## 13. Adapter implementation notes

- The adapter MUST drain the TCP read buffer on every tick or
  half-tick. Backlog should never exceed 64KB.
- The adapter MUST NOT block the engine main thread waiting for a
  client. All bridge I/O is non-blocking poll + per-frame drain.
- The adapter MUST support graceful shutdown: on `quit` or SIGTERM,
  flush events buffer + replay log + release sticky inputs before
  exiting.

## 14. Conformance

A reference conformance suite lives at
`spec/conformance/conformance_suite.py`. An adapter is conformant
when:
- All mandatory verbs (5.1) implemented and tested.
- Capability negotiation respected.
- Auth + handshake gates both enforced.
- Replay log produced if `replay` capability declared.
- Determinism: same seed + same input sequence -> identical
  snapshot_hash sequence.
- Eviction semantics: a 2nd client connection preempts the 1st with
  a `client_evicted` event delivered before the 1st socket closes.

Engines that ship a conformance report (`conformance-<engine>-<v>.md`)
in their adapter's README are listed in the master compatibility
matrix.
