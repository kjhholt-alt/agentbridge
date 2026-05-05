extends RefCounted
class_name AgentReplay

## AgentReplay -- writes every command + response + event line to
## user://agentbridge/<session_id>.ndjson when the `replay` capability
## is negotiated.
##
## Each line: {"dir":"in|out","t":<sec>,"frame":<phys_frame>,"line":{...}}

const REPLAY_DIR: String = "user://agentbridge"

var _file: FileAccess = null
var _session_id: String
var _start_t: float

func open_session(session_id: String) -> void:
    _session_id = session_id
    _start_t = Time.get_ticks_msec() / 1000.0
    DirAccess.make_dir_recursive_absolute(REPLAY_DIR)
    var path: String = "%s/%s.ndjson" % [REPLAY_DIR, session_id]
    _file = FileAccess.open(path, FileAccess.WRITE)

func close() -> void:
    if _file != null:
        _file.close()
        _file = null

func log_in(d: Dictionary) -> void:
    _write("in", d)

func log_out(d: Dictionary) -> void:
    _write("out", d)

func log_event(d: Dictionary) -> void:
    _write("event", d)

func _write(direction: String, payload: Dictionary) -> void:
    if _file == null:
        return
    var t: float = Time.get_ticks_msec() / 1000.0 - _start_t
    var entry: Dictionary = {
        "dir": direction,
        "t": t,
        "frame": Engine.get_physics_frames(),
        "line": payload,
    }
    _file.store_line(JSON.stringify(entry))
    _file.flush()
