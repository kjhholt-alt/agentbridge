# Changelog

All public-API changes documented here. Format: Keep-a-Changelog.

## [Unreleased]

## [0.2.0] -- 2026-05-05

Phases 2-9.5 -- everything below the spec.

### Added
- `adapters/godot/addons/agentbridge/` -- self-contained Godot 4.6
  addon (7 files, plugin.cfg + 6 .gd). Implements the full mandatory
  spec verbs + 8 capabilities (step, set_seed, snapshot_hash,
  timescale, replay, metrics, actions.bind, events.subscribe).
- `adapters/godot/examples/minimal_godot_project/` -- proves the
  addon boots cleanly with a 2-line scene.
- `spec/conformance/conformance_suite.py` -- engine-agnostic
  black-box test runner. 16 scenarios. Godot scores 16/16.
- `harness/python/agentbridge/` -- typed sync + async client,
  replay verifier, orchestrator, CLI (`agentbridge run`,
  `agentbridge replay`, `agentbridge self-check`). 34/34 pytest.
- `observability/log_shipper.py` -- NDJSON tail -> Discord embed.
  4/4 pytest.
- `mcp/agentbridge_mcp_server/` -- stdio JSON-RPC MCP server with
  3 tools (status, run_mission, replay). 6/6 pytest.
- `adapters/unity/AgentBridge/` -- UPM package mirroring the Godot
  adapter behavior under the same protocol. C# port complete (live
  conformance pending Kruz-side compile).
- `docs/` -- mkdocs-material site (10 pages, builds strict-clean).
- `vercel.json` -- ready for Vercel deploy at
  agentbridge.buildkit.store.
- `.github/workflows/` -- 4 CI workflows (harness-python on 3.11/
  3.12/3.13 matrix, conformance on Godot, adapter-godot lint,
  adapter-unity package-shape).

### Changed
- (Phase 9 in QuietWoods) `quiet-woods` consumes the addon as a
  vendored copy at `quiet-woods/godot/addons/agentbridge/`. Old
  in-tree `quiet-woods/godot/scripts/agent/{agent_bridge,
  agent_state_dump,agent_input_driver}.gd` removed; QW's bridge now
  always boots from the addon.

## [0.1.0] -- 2026-05-05

Phase 1 -- Spec & schema.

### Added
- `spec/AGENTBRIDGE_SPEC.md` v1.0.0: full wire protocol with
  handshake, auth, versioned commands, action vocab, event model,
  error codes, transport profiles, capability negotiation,
  backwards-compat policy.
- `spec/schema/v1/commands.json` -- JSON Schema for every client
  command.
- `spec/schema/v1/responses.json` -- response envelope schema.
- `spec/schema/v1/events.json` -- event type schema.
- `spec/schema/v1/state.json` -- base state shape (engines extend).
- `agentbridge.protocol` Python module skeleton with `--self-check`.
- Repo scaffolding (CLAUDE.md, LICENSE, README, .gitignore, CHANGELOG).
