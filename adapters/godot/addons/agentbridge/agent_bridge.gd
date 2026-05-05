extends Node
class_name AgentBridge

## AgentBridge -- Godot 4 reference adapter for the AgentBridge wire
## protocol v1.0.0. See spec at:
##   https://github.com/kjhholt-alt/agentbridge/blob/master/spec/AGENTBRIDGE_SPEC.md
##
## Boot:
##   - Set env AGENTBRIDGE=1 to opt the listener in.
##   - Set env AGENTBRIDGE_PORT (optional, default 7777).
##   - Add this node + agent_state_dump + agent_input_driver as children
##     of any scene. The example minimal_godot_project shows this layout.
##
## Capabilities supported by this reference adapter:
##   step, set_seed, snapshot_hash, timescale, replay, metrics,
##   actions.bind, events.subscribe.

const PROTOCOL_VERSION: String = "1.0.0"
const SCHEMA_URL: String = "https://github.com/kjhholt-alt/agentbridge/blob/master/spec/schema/v1"
const DEFAULT_PORT: int = 7777
const RECENT_EVENT_BUF: int = 256
const SERVER_CAPS: Array[String] = [
    "step", "set_seed", "snapshot_hash", "timescale", "replay",
    "metrics", "actions.bind", "events.subscribe",
]

# Error codes (mirror spec section 8)
const E_UNKNOWN_CMD: int = 1000
const E_HANDSHAKE_REQUIRED: int = 1001
const E_AUTH_FAILED: int = 1002
const E_PROTOCOL_MISMATCH: int = 1003
const E_CAP_NOT_NEGOTIATED: int = 1004
const E_INVALID_PAYLOAD: int = 2000
const E_UNKNOWN_ACTION: int = 2001
const E_INVALID_ACTION_VALUE: int = 2002
const E_ENGINE_INTERNAL: int = 3000

@export var enabled: bool = false
@export var port: int = DEFAULT_PORT
@export var auto_register_default_actions: bool = true

var _server: TCPServer = null
var _client: StreamPeerTCP = null
var _buffer: String = ""
var _state_dump: Node = null
var _input_driver: Node = null
var _events: Array = []
var _subscriptions: Dictionary = {}  # type -> true; if any subs, only those go to events buffer
var _started: bool = false
var _token: String = ""
var _session_id: String = ""
var _client_handshaked: bool = false
var _granted_caps: Array[String] = []
# Use Object/dynamic typing to avoid class_name registry races --
# class_name resolution requires editor scan + import, which doesn't
# always happen in test-runner mode.
var _replay = null
var _metrics = null
var _step_remaining: int = 0
var _step_caller_was_paused: bool = false
var _seed_set: bool = false
var _rng_seed: int = 0
var _events_dropped: int = 0

signal bridge_ready
signal client_connected(session_id: String)
signal client_disconnected

func _ready() -> void:
    # Accept both AGENTBRIDGE (spec v1) and the legacy QW_AGENT_BRIDGE
    # used by QuietWoods pre-v0.2.3 so existing tooling keeps working.
    var env_enabled: bool = OS.get_environment("AGENTBRIDGE") == "1" \
        or OS.get_environment("QW_AGENT_BRIDGE") == "1"
    if not enabled and not env_enabled:
        return
    var env_port: String = OS.get_environment("AGENTBRIDGE_PORT")
    if env_port == "":
        env_port = OS.get_environment("QW_AGENT_PORT")
    if env_port != "":
        port = int(env_port)
    _ensure_state_dump()
    _ensure_input_driver()
    if auto_register_default_actions and _input_driver != null:
        _input_driver.call("register_default_actions")
    var auth_script: GDScript = load("res://addons/agentbridge/agent_auth.gd")
    _token = auth_script.ensure_token()
    var metrics_script: GDScript = load("res://addons/agentbridge/agent_metrics.gd")
    _metrics = metrics_script.new()
    _server = TCPServer.new()
    var err: int = _server.listen(port, "127.0.0.1")
    if err != OK:
        push_error("AgentBridge: listen on 127.0.0.1:%d failed (err=%d)" % [port, err])
        return
    _started = true
    print("[agentbridge] v%s listening on tcp://127.0.0.1:%d" % [PROTOCOL_VERSION, port])
    _wire_event_capture()
    set_process(true)
    bridge_ready.emit()

func _ensure_state_dump() -> void:
    var existing := get_parent().get_node_or_null("AgentStateDump")
    if existing == null and has_node("../AgentStateDump"):
        existing = get_node("../AgentStateDump")
    if existing == null:
        var node := Node.new()
        node.name = "AgentStateDump"
        node.set_script(load("res://addons/agentbridge/agent_state_dump.gd"))
        get_parent().call_deferred("add_child", node)
        _state_dump = node
    else:
        _state_dump = existing

func _ensure_input_driver() -> void:
    var existing := get_parent().get_node_or_null("AgentInputDriver")
    if existing == null:
        var node := Node.new()
        node.name = "AgentInputDriver"
        node.set_script(load("res://addons/agentbridge/agent_input_driver.gd"))
        # call_deferred avoids "Parent node is busy setting up children"
        # when the bridge's _ready fires inside the scene tree build.
        get_parent().call_deferred("add_child", node)
        _input_driver = node
    else:
        _input_driver = existing

func _wire_event_capture() -> void:
    # The base adapter does NOT subscribe to engine signals. Games
    # extend this and call push_event() themselves, or emit a custom
    # signal that they connect to push_event in their own scene script.
    # That keeps the addon engine-agnostic.
    pass

func push_event(d: Dictionary) -> void:
    if d.size() == 0:
        return
    var ev: Dictionary = d.duplicate(true)
    if not ev.has("type"):
        push_error("AgentBridge.push_event missing 'type'")
        return
    ev["t"] = Time.get_ticks_msec() / 1000.0
    if _session_id != "":
        ev["session_id"] = _session_id
    var t: String = String(ev["type"])
    if not _subscriptions.is_empty() and not _subscriptions.has(t):
        return
    _events.append(ev)
    _metrics.record_event_emitted()
    if _replay != null:
        _replay.log_event(ev)
    while _events.size() > RECENT_EVENT_BUF:
        _events.pop_front()
        _events_dropped += 1
        _metrics.record_event_dropped()

func _process(_delta: float) -> void:
    if not _started or _server == null:
        return
    if _step_remaining > 0:
        _step_remaining -= 1
        if _step_remaining == 0:
            _send_step_done()
    if _client != null:
        _client.poll()
        var status: int = _client.get_status()
        if status != StreamPeerTCP.STATUS_CONNECTED:
            _drop_client()
    if _client == null and _server.is_connection_available():
        _accept_new_client()
    if _client == null:
        return
    _drain_input()

func _accept_new_client() -> void:
    var new_client: StreamPeerTCP = _server.take_connection()
    if new_client == null:
        return
    new_client.set_no_delay(true)
    if _client != null:
        # Existing client is being preempted. We do NOT send an
        # eviction notice over its socket because that socket may be
        # in CLOSE_WAIT and put_data could stall the engine main
        # thread. Just clean up state and accept the new client.
        _drop_client(false)
    _client = new_client
    _buffer = ""
    _client_handshaked = false
    _granted_caps.clear()
    _subscriptions.clear()
    _session_id = "sess-%d-%d" % [Time.get_ticks_msec(), randi() % 1000000]
    push_event({"type": "client_connected"})
    print("[agentbridge] client connected: %s" % _session_id)
    client_connected.emit(_session_id)

func _drop_client(emit_signal: bool = true) -> void:
    if _input_driver != null:
        _input_driver.call("release_all")
    if _replay != null:
        _replay.close()
        _replay = null
    _client = null
    _buffer = ""
    _client_handshaked = false
    _granted_caps.clear()
    _subscriptions.clear()
    _events.clear()
    if emit_signal:
        client_disconnected.emit()

func _drain_input() -> void:
    var avail: int = _client.get_available_bytes()
    if avail <= 0:
        return
    var chunk: PackedByteArray = _client.get_data(avail)[1]
    _buffer += chunk.get_string_from_utf8()
    _metrics.record_bytes(avail, 0)
    while true:
        var nl: int = _buffer.find("\n")
        if nl < 0:
            break
        var line: String = _buffer.substr(0, nl).strip_edges()
        _buffer = _buffer.substr(nl + 1)
        if line == "":
            continue
        _handle_line(line)

func _handle_line(line: String) -> void:
    var parsed: Variant = JSON.parse_string(line)
    if not (parsed is Dictionary):
        _send_err(E_INVALID_PAYLOAD, "json must be an object")
        return
    var d: Dictionary = parsed
    var t0: float = Time.get_ticks_msec()
    if _replay != null:
        _replay.log_in(d)
    var cmd: String = String(d.get("cmd", ""))
    if cmd != "hello" and not _client_handshaked:
        _send_err(E_HANDSHAKE_REQUIRED, "send hello first")
        return
    if cmd != "hello" and _token != "" and String(d.get("token", "")) != "":
        var auth_script: GDScript = load("res://addons/agentbridge/agent_auth.gd")
        if not auth_script.constant_time_eq(_token, String(d.get("token", ""))):
            _send_err(E_AUTH_FAILED, "token mismatch")
            _drop_client()
            return
    match cmd:
        "hello":           _handle_hello(d)
        "ping":            _send({"ok": true, "pong": true})
        "state":           _handle_state(d)
        "action":          _handle_action(d)
        "events":          _handle_events()
        "reset":           _handle_reset()
        "quit":            _handle_quit()
        "capabilities":    _send({"ok": true, "capabilities": SERVER_CAPS})
        "subscribe":       _handle_subscribe(d, true)
        "unsubscribe":     _handle_subscribe(d, false)
        "set_seed":        _handle_set_seed(d)
        "step":            _handle_step(d)
        "set_timescale":   _handle_set_timescale(d)
        "snapshot_hash":   _handle_snapshot_hash()
        "bind_action":     _handle_bind_action(d)
        "metrics":         _send({"ok": true, "metrics": _metrics.dump()})
        _:                 _send_err(E_UNKNOWN_CMD, "unknown cmd: %s" % cmd)
    _metrics.record_command(Time.get_ticks_msec() - t0)

func _handle_hello(d: Dictionary) -> void:
    var supplied_token: String = String(d.get("token", ""))
    var auth_script: GDScript = load("res://addons/agentbridge/agent_auth.gd")
    if not auth_script.constant_time_eq(_token, supplied_token):
        _send_err(E_AUTH_FAILED, "token mismatch")
        _drop_client()
        return
    var proto: String = String(d.get("protocol", ""))
    if not proto.begins_with("1."):
        _send_err(E_PROTOCOL_MISMATCH, "this adapter speaks 1.x; got %s" % proto)
        _drop_client()
        return
    var requested_caps: Array = d.get("capabilities", [])
    _granted_caps.clear()
    for cap in requested_caps:
        if SERVER_CAPS.has(String(cap)):
            _granted_caps.append(String(cap))
    if "replay" in _granted_caps:
        var replay_script: GDScript = load("res://addons/agentbridge/agent_replay.gd")
        _replay = replay_script.new()
        _replay.open_session(_session_id)
    _client_handshaked = true
    _send({
        "ok": true,
        "session_id": _session_id,
        "server_caps": SERVER_CAPS.duplicate(),
        "max_event_buffer": RECENT_EVENT_BUF,
        "schema_url": SCHEMA_URL,
        "engine": "godot",
        "engine_version": Engine.get_version_info().get("string", ""),
    })

func _handle_state(_d: Dictionary) -> void:
    if _state_dump == null or not _state_dump.has_method("snapshot"):
        _send_err(E_ENGINE_INTERNAL, "state_dump unavailable")
        return
    _send({"ok": true, "state": _state_dump.snapshot()})

func _handle_action(d: Dictionary) -> void:
    if _input_driver == null or not _input_driver.has_method("apply_command"):
        _send_err(E_ENGINE_INTERNAL, "input_driver unavailable")
        return
    var res: Dictionary = _input_driver.apply_command(d)
    _metrics.record_action()
    _send(res)

func _handle_events() -> void:
    var drained: Array = _events.duplicate(true)
    _events.clear()
    _send({"ok": true, "events": drained, "events_dropped": _events_dropped})
    _events_dropped = 0

func _handle_reset() -> void:
    _events.clear()
    _events_dropped = 0
    if _input_driver != null:
        _input_driver.call("release_all")
    var loop := get_tree()
    if loop != null:
        loop.reload_current_scene()
    _send({"ok": true})

func _handle_quit() -> void:
    _send({"ok": true})
    var loop := get_tree()
    if loop != null:
        loop.quit(0)

func _handle_subscribe(d: Dictionary, on: bool) -> void:
    var types: Array = d.get("types", [])
    if types.size() == 0:
        _send_err(E_INVALID_PAYLOAD, "subscribe needs types[]")
        return
    for t in types:
        var k: String = String(t)
        if on:
            _subscriptions[k] = true
        else:
            _subscriptions.erase(k)
    _send({"ok": true, "subscriptions": _subscriptions.keys()})

func _handle_set_seed(d: Dictionary) -> void:
    if not "set_seed" in _granted_caps:
        _send_err(E_CAP_NOT_NEGOTIATED, "set_seed not granted")
        return
    var seed_v: int = int(d.get("seed", 0))
    _rng_seed = seed_v
    _seed_set = true
    seed(seed_v)  # global RNG
    _send({"ok": true, "seed": seed_v})

func _handle_step(d: Dictionary) -> void:
    if not "step" in _granted_caps:
        _send_err(E_CAP_NOT_NEGOTIATED, "step not granted")
        return
    var n: int = int(d.get("frames", 1))
    if n < 1 or n > 100000:
        _send_err(E_INVALID_PAYLOAD, "frames out of range")
        return
    _step_remaining = n
    # The actual response is sent by _send_step_done() once frames advanced.

func _send_step_done() -> void:
    _send({"ok": true, "stepped": true})

func _handle_set_timescale(d: Dictionary) -> void:
    if not "timescale" in _granted_caps:
        _send_err(E_CAP_NOT_NEGOTIATED, "timescale not granted")
        return
    var s: float = float(d.get("scale", 1.0))
    if s < 0.0 or s > 64.0:
        _send_err(E_INVALID_PAYLOAD, "scale out of range")
        return
    Engine.time_scale = s
    _send({"ok": true, "scale": s})

func _handle_snapshot_hash() -> void:
    if not "snapshot_hash" in _granted_caps:
        _send_err(E_CAP_NOT_NEGOTIATED, "snapshot_hash not granted")
        return
    if _state_dump == null or not _state_dump.has_method("snapshot_hash"):
        _send_err(E_ENGINE_INTERNAL, "state_dump.snapshot_hash unavailable")
        return
    _send({"ok": true, "hash": _state_dump.snapshot_hash()})

func _handle_bind_action(d: Dictionary) -> void:
    if not "actions.bind" in _granted_caps:
        _send_err(E_CAP_NOT_NEGOTIATED, "actions.bind not granted")
        return
    if _input_driver == null:
        _send_err(E_ENGINE_INTERNAL, "input_driver unavailable")
        return
    var res: Dictionary = _input_driver.bind_action(
        String(d.get("name", "")),
        String(d.get("input_action", "")),
        String(d.get("kind", "")),
    )
    _send(res)

func _send(d: Dictionary) -> void:
    if _client == null:
        return
    var line: String = JSON.stringify(d) + "\n"
    var bytes: PackedByteArray = line.to_utf8_buffer()
    _client.put_data(bytes)
    _metrics.record_bytes(0, bytes.size())
    if _replay != null:
        _replay.log_out(d)

func _send_err(code: int, msg: String) -> void:
    _send({"ok": false, "error": msg, "code": code})

# Public helper for game code that wants to register additional actions
func register_actions(names: Array, kinds: Dictionary = {}) -> void:
    if _input_driver == null:
        return
    for n in names:
        var name_s: String = String(n)
        var kind: String = String(kinds.get(name_s, "oneshot"))
        _input_driver.bind_action(name_s, name_s, kind)

func session_id() -> String:
    return _session_id

func granted_caps() -> Array[String]:
    return _granted_caps.duplicate()
