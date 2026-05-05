extends Node
class_name AgentInputDriver

## AgentInputDriver -- registry-driven input injection.
##
## Engines/games register their action vocabulary at startup via
## register_actions([...]) or bind_action(name, input_action, kind).
## The bridge calls apply_command(cmd) on every "action" message from
## the agent.
##
## Three input kinds:
##   sticky      held until released by the agent (move, sprint, block)
##   oneshot     single press + release on next frame (attack, vault)
##   look_delta  float radians applied once and cleared (mouse equivalent)
##
## Names use snake_case ASCII matching ^[a-z][a-z0-9_]{0,47}$. Names
## starting with `_` are reserved.

const STICKY: String = "sticky"
const ONESHOT: String = "oneshot"
const LOOK_DELTA: String = "look_delta"

var _registry: Dictionary = {}
var _sticky_state: Dictionary = {}
var _pending_yaw: float = 0.0
var _pending_pitch: float = 0.0
var _pending_roll: float = 0.0

func _ready() -> void:
    set_process(true)

func register_default_actions() -> void:
    var sticky_defaults: Array[String] = [
        "move_forward", "move_back", "strafe_left", "strafe_right",
        "sprint", "crouch_held", "block",
    ]
    var oneshot_defaults: Array[String] = [
        "attack", "interact", "vault", "crouch_toggle", "pause",
        "weapon_1", "weapon_2", "weapon_3", "weapon_4",
    ]
    var alias_overrides: Dictionary = {
        "strafe_left": "move_left",
        "strafe_right": "move_right",
        "crouch_toggle": "crouch",
    }
    for n in sticky_defaults:
        var alias: String = alias_overrides.get(n, n)
        _registry[n] = {"input_action": alias, "kind": STICKY}
    for n in oneshot_defaults:
        var alias2: String = alias_overrides.get(n, n)
        _registry[n] = {"input_action": alias2, "kind": ONESHOT}
    for n in ["look_yaw_delta", "look_pitch_delta", "look_roll_delta"]:
        _registry[n] = {"input_action": "", "kind": LOOK_DELTA}

func bind_action(name: String, input_action: String, kind: String) -> Dictionary:
    if not _valid_name(name):
        return {"ok": false, "error": "invalid action name", "code": 2000}
    if not (kind in [STICKY, ONESHOT, LOOK_DELTA]):
        return {"ok": false, "error": "invalid kind", "code": 2000}
    _registry[name] = {"input_action": input_action, "kind": kind}
    return {"ok": true}

func apply_command(d: Dictionary) -> Dictionary:
    var name: String = String(d.get("name", ""))
    if not _registry.has(name):
        return {"ok": false, "error": "unknown_action: %s" % name, "code": 2001}
    var entry: Dictionary = _registry[name]
    var kind: String = entry["kind"]
    var input_action: String = entry["input_action"]
    match kind:
        LOOK_DELTA:
            var v: float = float(d.get("value", 0.0))
            if name.begins_with("look_yaw"):
                _pending_yaw += v
            elif name.begins_with("look_pitch"):
                _pending_pitch += v
            elif name.begins_with("look_roll"):
                _pending_roll += v
            return {"ok": true}
        STICKY:
            if input_action == "" or not InputMap.has_action(input_action):
                return {"ok": false, "error": "input action missing: %s" % input_action,
                        "code": 2002}
            var on: bool = bool(d.get("value", true))
            var was: bool = bool(_sticky_state.get(name, false))
            if on == was:
                return {"ok": true, "noop": true}
            _sticky_state[name] = on
            if on:
                Input.action_press(input_action)
            else:
                Input.action_release(input_action)
            return {"ok": true}
        ONESHOT:
            if input_action == "" or not InputMap.has_action(input_action):
                return {"ok": false, "error": "input action missing: %s" % input_action,
                        "code": 2002}
            Input.action_press(input_action)
            call_deferred("_release_pulse", input_action)
            return {"ok": true}
    return {"ok": false, "error": "internal: unknown kind", "code": 3000}

func _release_pulse(action_name: String) -> void:
    if InputMap.has_action(action_name):
        Input.action_release(action_name)

func _process(_delta: float) -> void:
    if _pending_yaw == 0.0 and _pending_pitch == 0.0 and _pending_roll == 0.0:
        return
    var loop := get_tree()
    if loop == null:
        _pending_yaw = 0.0
        _pending_pitch = 0.0
        _pending_roll = 0.0
        return
    var p := loop.get_first_node_in_group("player")
    if p == null:
        _pending_yaw = 0.0
        _pending_pitch = 0.0
        _pending_roll = 0.0
        return
    if p is Node3D and abs(_pending_yaw) > 0.0001:
        if "_yaw" in p:
            p._yaw -= _pending_yaw
            (p as Node3D).rotation.y = p._yaw
        else:
            (p as Node3D).rotation.y -= _pending_yaw
    if p is Node3D and abs(_pending_pitch) > 0.0001:
        if "_pitch" in p and p.has_node("Head"):
            p._pitch = clamp(p._pitch - _pending_pitch, -1.535, 1.535)
            ((p as Node3D).get_node("Head") as Node3D).rotation.x = p._pitch
    _pending_yaw = 0.0
    _pending_pitch = 0.0
    _pending_roll = 0.0

func release_all() -> void:
    for name in _sticky_state.keys():
        if bool(_sticky_state[name]):
            var entry: Dictionary = _registry.get(name, {})
            var input_action: String = String(entry.get("input_action", ""))
            if input_action != "" and InputMap.has_action(input_action):
                Input.action_release(input_action)
    _sticky_state.clear()

func registered_names() -> Array:
    return _registry.keys()

func _valid_name(name: String) -> bool:
    if name.length() == 0 or name.length() > 48:
        return false
    if name.begins_with("_"):
        return false
    var first: int = name.unicode_at(0)
    if not (first >= 97 and first <= 122):  # 'a'..'z'
        return false
    for i in range(name.length()):
        var c: int = name.unicode_at(i)
        var ok: bool = (c >= 97 and c <= 122) or (c >= 48 and c <= 57) or c == 95
        if not ok:
            return false
    return true
