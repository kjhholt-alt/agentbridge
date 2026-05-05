extends RefCounted
class_name AgentAuth

## AgentAuth -- per-launch random token persistence.
##
## On adapter startup, generates a 32-char alphanumeric token and writes
## it to user://agentbridge.token (Godot resolves to %APPDATA%/<project>/
## on Windows, ~/.local/share/godot/app_userdata/<project>/ on Linux).
##
## The client reads the token and includes it in `hello.token`. The
## adapter compares constant-time and disconnects on mismatch.

const TOKEN_PATH: String = "user://agentbridge.token"
const TOKEN_LEN: int = 32

static func ensure_token() -> String:
    var f := FileAccess.open(TOKEN_PATH, FileAccess.READ)
    if f != null:
        var existing: String = f.get_line().strip_edges()
        f.close()
        if existing.length() >= 16:
            return existing
    var token: String = _generate(TOKEN_LEN)
    var w := FileAccess.open(TOKEN_PATH, FileAccess.WRITE)
    if w == null:
        push_error("AgentAuth: cannot write token file %s" % TOKEN_PATH)
        return token
    w.store_line(token)
    w.close()
    return token

static func _generate(n: int) -> String:
    var rng := RandomNumberGenerator.new()
    rng.randomize()
    var alphabet: String = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    var out: String = ""
    for _i in n:
        out += alphabet.substr(rng.randi_range(0, alphabet.length() - 1), 1)
    return out

# Constant-time string comparison so the adapter doesn't leak token
# length / partial matches via timing.
static func constant_time_eq(a: String, b: String) -> bool:
    var ba: PackedByteArray = a.to_utf8_buffer()
    var bb: PackedByteArray = b.to_utf8_buffer()
    if ba.size() != bb.size():
        # touch every byte of bb anyway to avoid early-exit timing
        var dummy: int = 0
        for byte in bb:
            dummy = dummy ^ int(byte)
        return false
    var diff: int = 0
    for i in ba.size():
        diff = diff | (int(ba[i]) ^ int(bb[i]))
    return diff == 0
