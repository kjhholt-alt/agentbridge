extends RefCounted
class_name AgentMetrics

## AgentMetrics -- rolling counters for the bridge.
## Returned by the `metrics` command when its capability is negotiated.

var actions_total: int = 0
var commands_total: int = 0
var events_emitted: int = 0
var events_dropped: int = 0
var bytes_in: int = 0
var bytes_out: int = 0
var session_start_t: float = 0.0
var _latency_samples: Array[float] = []
const MAX_LATENCY_SAMPLES: int = 256

func _init() -> void:
    session_start_t = Time.get_ticks_msec() / 1000.0

func record_command(latency_ms: float) -> void:
    commands_total += 1
    _latency_samples.append(latency_ms)
    if _latency_samples.size() > MAX_LATENCY_SAMPLES:
        _latency_samples.pop_front()

func record_action() -> void:
    actions_total += 1

func record_event_emitted() -> void:
    events_emitted += 1

func record_event_dropped() -> void:
    events_dropped += 1

func record_bytes(in_bytes: int, out_bytes: int) -> void:
    bytes_in += in_bytes
    bytes_out += out_bytes

func dump() -> Dictionary:
    var p50: float = _percentile(0.50)
    var p99: float = _percentile(0.99)
    var t: float = Time.get_ticks_msec() / 1000.0
    var elapsed: float = max(0.0001, t - session_start_t)
    return {
        "session_seconds": elapsed,
        "actions_total": actions_total,
        "actions_per_sec": actions_total / elapsed,
        "commands_total": commands_total,
        "events_emitted": events_emitted,
        "events_dropped": events_dropped,
        "bytes_in": bytes_in,
        "bytes_out": bytes_out,
        "latency_ms_p50": p50,
        "latency_ms_p99": p99,
        "fps": Engine.get_frames_per_second(),
    }

func _percentile(q: float) -> float:
    if _latency_samples.is_empty():
        return 0.0
    var sorted_arr: Array[float] = _latency_samples.duplicate()
    sorted_arr.sort()
    var idx: int = int(q * (sorted_arr.size() - 1))
    return sorted_arr[idx]
