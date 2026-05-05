# Changelog

The canonical changelog lives at
[`CHANGELOG.md`](https://github.com/kjhholt-alt/agentbridge/blob/master/CHANGELOG.md).

## 0.1.0 -- 2026-05-05

All 9 phases shipped:

1. Spec v1.0.0 + JSON schemas + protocol self-check (31 positive +
   16 negative fixtures).
2. Godot adapter as a Godot 4.6 addon.
3. Conformance suite (engine-agnostic) -- 16/16 PASS on Godot.
4. Python harness (sync + async client + replay + orchestrator + CLI)
   -- 34/34 pytest.
5. Observability log shipper -- 4/4 pytest.
6. MCP server -- 6/6 pytest.
7. Unity adapter (UPM package) -- code complete.
8. Docs site (this site).
9. QuietWoods migration to consume the addon.
