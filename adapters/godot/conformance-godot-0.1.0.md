# AgentBridge conformance report

adapter: **godot** 0.1.0
date: 2026-05-04 22:21:43
protocol: 1.0.0

| Scenario | Verdict | Detail |
|---|---|---|
| handshake_required | PASS |  |
| auth_failure | PASS |  |
| hello_negotiates_caps | PASS | caps=['step', 'set_seed', 'snapshot_hash', 'timescale', 'replay']... |
| ping_after_hello | PASS |  |
| state_has_base_keys | PASS | keys=['player', 'ticks', 'time'] |
| action_unknown_returns_2001 | PASS |  |
| sticky_press_release | PASS |  |
| oneshot_pulse | PASS |  |
| look_delta_returns_ok | PASS |  |
| events_drain | PASS | events=1 |
| subscribe_unsubscribe | PASS |  |
| set_seed_when_negotiated | PASS |  |
| snapshot_hash_format | PASS | hash=ca7fe1e7edacac93 |
| metrics_returned | PASS | commands_total=25 |
| capabilities_echo | PASS |  |
| quit_clean_disconnect | PASS |  |

**Score: 16/16 passed.**