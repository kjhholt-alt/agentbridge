# Conformance suite

A black-box test runner at
[`spec/conformance/conformance_suite.py`](https://github.com/kjhholt-alt/agentbridge/blob/master/spec/conformance/conformance_suite.py).

## What it tests

16 scenarios (as of v0.1.0):

- `handshake_required` -- pre-hello commands return code 1001
- `auth_failure` -- bad token returns code 1002
- `hello_negotiates_caps` -- session_id + server_caps returned
- `ping_after_hello`
- `state_has_base_keys` -- `player`, `time` always present
- `action_unknown_returns_2001`
- `sticky_press_release`, `oneshot_pulse`, `look_delta_returns_ok`
- `events_drain`, `subscribe_unsubscribe`
- `set_seed_when_negotiated`, `snapshot_hash_format`
- `metrics_returned`, `capabilities_echo`
- `quit_clean_disconnect`

## Run against any adapter

```bash
# Adapter must already be running on host:port
python spec/conformance/conformance_suite.py \
  --no-launch \
  --host 127.0.0.1 --port 7777 \
  --token-file <userdata>/agentbridge.token \
  --adapter-name <engine> --adapter-version <v> \
  --report conformance-<engine>-<v>.md
```

## Reference results

| Adapter | Version | Score | Report |
|---|---|---|---|
| Godot | 0.1.0 | 16/16 | `adapters/godot/conformance-godot-0.1.0.md` |
| Unity | 0.1.0 | pending Kruz-side compile | -- |
