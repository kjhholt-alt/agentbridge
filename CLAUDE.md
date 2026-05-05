# AgentBridge - Claude Code project instructions

Portable AI playtesting infrastructure for game engines. Multi-repo,
multi-engine. Spec-first, reference-implementations second.

## Hard rules

1. **Backwards compat the protocol.** Once spec v1.0.0 ships, never
   break schema. Additive changes only (new optional fields, new
   capabilities, new verbs gated by capability).
2. **ASCII-only** in `.gd`, `.cs`, `.ps1`, `.py`. PS 5.1 cp1252
   compatibility. No em-dashes -- use double-hyphen `--`.
3. **No networking outside 127.0.0.1.** Adapters must bind to
   loopback only.
4. **Bind requires `AGENTBRIDGE=1`** environment variable. Never
   auto-listens.
5. **Auth token mandatory** even for localhost. Stops cross-project
   hijack.
6. **No paid dependencies.** Stdlib + open-source only.
7. **Conventional commits + Co-Author trailer**:
   `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
8. **Two-attempt rule**: 3rd failure -> write
   `docs/<phase>_BLOCKER_<date>.md`, push, move on.
9. **Phase gates are mandatory.** Each phase ships only when its
   verify is green. No skipping.
10. **No TODOs in shipped code.** Open items go to
    `docs/<topic>_BLOCKER_<date>.md`.

## Verify discipline

| Layer | Verify |
|---|---|
| Schemas | `jsonschema --check` + `python -m agentbridge.protocol --self-check` |
| Godot adapter | GUT tests + conformance suite |
| Python harness | `pytest -q` + coverage gate (>=90%) |
| Unity adapter | `Unity -batchmode -runTests` + conformance suite |
| MCP | smoke harness call + introspection |
| Docs | `mkdocs build --strict` |
| CI | `.github/workflows/*.yml` all green on the PR |

## Phase gates

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | Spec v1 + schemas | self-check passes, jsonschema --check |
| 2 | Godot addon | GUT 60+ tests + conformance 100% |
| 3 | Conformance suite | runs against any adapter |
| 4 | Python harness | pytest 80+, coverage >=90% |
| 5 | Observability | Discord embed posts in test |
| 6 | MCP wrapper | tools registered + smoke green |
| 7 | Unity adapter | conformance 100% with same suite |
| 8 | Docs site | mkdocs build strict + Vercel deploy |
| 9 | QW migration | 71+ tests still green, smoke reproduces |

## What this repo IS

- The protocol (spec/)
- Reference adapters (adapters/)
- The agent harness (harness/)
- The MCP server (mcp/)
- Observability (observability/)

## What this repo IS NOT

- A game engine
- A game
- A model trainer
- A general-purpose RPC framework

## Cross-project rules

- **Never modify QuietWoods until Phase 9.** Phases 1-8 build the new
  repo from scratch using the QuietWoods bridge as a reference only.
- Never modify any other game project (signal-game, case-zero-game,
  game-forge, MindForge) without explicit user approval -- they will
  consume agentbridge as a Phase 9.5+ concern.
