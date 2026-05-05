extends Node
class_name AgentStateDump

## AgentStateDump -- base class. Returns the minimum-required state
## per spec v1 schema/v1/state.json: {player, time}.
##
## Games extend this and override `extra_state()` to add engine- or
## game-specific keys (e.g. shamblers, inventory, director, region).
## The base + extra are merged in `snapshot()`.
##
## Determinism: the snapshot_hash command uses canonical JSON over
## the merged dict so games can opt in to stable hashing simply by
## returning deterministic data from extra_state().

const FNV_PRIME: int = 1099511628211
# FNV-1a 64-bit offset basis 0xCBF29CE484222325. GDScript ints are
# signed 64-bit so we initialize via decimal-of-bit-pattern trick:
# 0xCBF29CE484222325 == -3750763034362895579 as signed.
const FNV_OFFSET: int = -3750763034362895579
const U64_MASK: int = 0x7FFFFFFFFFFFFFFF  # signed-positive mask; full mask not representable

func snapshot() -> Dictionary:
    var base: Dictionary = {
        "player": _player_dump(),
        "time": _time_dump(),
        "ticks": Engine.get_physics_frames(),
    }
    var extra: Dictionary = extra_state()
    for k in extra.keys():
        base[k] = extra[k]
    return base

# Subclasses override this to add their own state keys.
func extra_state() -> Dictionary:
    return {}

func _player_dump() -> Dictionary:
    var loop := get_tree() if is_inside_tree() else Engine.get_main_loop()
    if loop == null or not (loop is SceneTree):
        return {"position": [0.0, 0.0, 0.0]}
    var tree: SceneTree = loop
    var p := tree.get_first_node_in_group("player")
    if p == null:
        return {"position": [0.0, 0.0, 0.0]}
    var pos: Vector3 = (p as Node3D).global_position if p is Node3D else Vector3.ZERO
    var d: Dictionary = {
        "position": [_r(pos.x), _r(pos.y), _r(pos.z)],
    }
    if p is Node3D:
        d["yaw"] = _r((p as Node3D).rotation.y)
        if p.has_node("Head"):
            var head := (p as Node3D).get_node("Head") as Node3D
            if head != null:
                d["pitch"] = _r(head.rotation.x)
    if "hp" in p:
        d["hp"] = _r(float(p.get("hp")))
    if "hp_max" in p:
        d["hp_max"] = _r(float(p.get("hp_max")))
    return d

func _time_dump() -> Dictionary:
    return {
        "session_seconds": Time.get_ticks_msec() / 1000.0,
        "frame": Engine.get_physics_frames(),
    }

func snapshot_hash() -> String:
    var canonical: String = _canonical_json(snapshot())
    return _fnv64(canonical)

func _canonical_json(v: Variant) -> String:
    if v is Dictionary:
        var keys: Array = (v as Dictionary).keys()
        keys.sort()
        var parts: Array[String] = []
        for k in keys:
            parts.append("%s:%s" % [JSON.stringify(k), _canonical_json((v as Dictionary)[k])])
        return "{%s}" % ",".join(parts)
    if v is Array:
        var ap: Array[String] = []
        for item in v:
            ap.append(_canonical_json(item))
        return "[%s]" % ",".join(ap)
    return JSON.stringify(v)

func _fnv64(s: String) -> String:
    # GDScript ints are signed 64-bit. Multiplications wrap modulo 2^64
    # naturally because of two's-complement; we just keep the low 64
    # bits in the signed slot and format as hex on output via printing
    # the unsigned reinterpretation by manipulating string output.
    var h: int = FNV_OFFSET
    var bytes: PackedByteArray = s.to_utf8_buffer()
    for b in bytes:
        h = h ^ int(b)
        h = h * FNV_PRIME  # natural overflow within signed 64-bit
    # Reinterpret signed -> unsigned hex string
    return _hex_u64(h)

func _hex_u64(n: int) -> String:
    var hi: int = (n >> 32) & 0xFFFFFFFF
    var lo: int = n & 0xFFFFFFFF
    return "%08x%08x" % [hi, lo]

func _r(v: float) -> float:
    return round(v * 100.0) / 100.0
