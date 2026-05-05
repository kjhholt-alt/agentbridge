# Changelog

All public-API changes documented here. Format: Keep-a-Changelog.

## [Unreleased]

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
