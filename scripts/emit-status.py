"""emit-status.py -- emit a status-spec/v1 doc for agentbridge.

The portfolio_health recipe (operator-core) reads
``~/.operator/data/status/agentbridge.json``.

Usage:
    py scripts/emit-status.py --health green --tests-passed 42 --tests-failed 0

Fail-closed-safe:
    - Tries to import status_spec from the sibling status-spec/ repo
      (writers/python/) or from any installed location. If unavailable,
      falls back to hand-rolled v1 JSON.
    - All filesystem failures are caught; the script exits 0 so CI/test
      runners are not poisoned.

Slug must match TRACKED_PROJECTS in operator-core.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_SLUG = "agentbridge"
SCHEMA_VERSION = "status-spec/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_dir() -> Path:
    override = os.environ.get("OPERATOR_STATUS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".operator" / "data" / "status"


def _try_import_writer():
    """Import status_spec writer, searching sibling status-spec/ if needed."""
    here = Path(__file__).resolve().parent
    candidates = []
    # Walk up looking for sibling status-spec/writers/python
    for parent in [here, *here.parents]:
        cand = parent / "status-spec" / "writers" / "python"
        if cand.exists():
            candidates.append(cand)
            break
    for c in candidates:
        if str(c) not in sys.path:
            sys.path.insert(0, str(c))
    try:
        from status_spec import StatusBuilder, write_atomic  # type: ignore
        return StatusBuilder, write_atomic
    except Exception:
        return None, None


def _hand_rolled_write(target: Path, doc: dict) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp",
                               dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target


def main() -> int:
    p = argparse.ArgumentParser(
        description=f"Emit status-spec/v1 doc for {PROJECT_SLUG}")
    p.add_argument("--health", choices=["green", "yellow", "red"], default="green")
    p.add_argument("--summary", default=None)
    p.add_argument("--tests-passed", type=int, default=-1)
    p.add_argument("--tests-failed", type=int, default=-1)
    p.add_argument("--duration-sec", type=int, default=0)
    p.add_argument("--exit-code", type=int, default=0)
    args = p.parse_args()

    summary = args.summary or (
        f"all {args.tests_passed} tests passing"
        if args.health == "green" and args.tests_passed >= 0
        else f"tests exit={args.exit_code}"
    )

    StatusBuilder, write_atomic = _try_import_writer()
    target = _status_dir() / f"{PROJECT_SLUG}.json"

    try:
        if StatusBuilder is not None and write_atomic is not None:
            b = (
                StatusBuilder(PROJECT_SLUG)
                .health(args.health, summary)
                .subsystem(
                    "tests",
                    args.health,
                    f"passed={args.tests_passed} failed={args.tests_failed} "
                    f"exit={args.exit_code} duration={args.duration_sec}s",
                )
                .last_event("test.run.completed", summary)
            )
            if args.tests_passed >= 0:
                b = b.counter("tests_passed", args.tests_passed)
            if args.tests_failed >= 0:
                b = b.counter("tests_failed", args.tests_failed)
            b = b.counter("test_run_duration_sec", args.duration_sec)
            b = b.counter("test_run_exit_code", args.exit_code)
            doc = b.build()
            write_atomic(target, doc)
        else:
            ts = _utc_now()
            doc = {
                "schema_version": SCHEMA_VERSION,
                "project": PROJECT_SLUG,
                "ts": ts,
                "health": args.health,
                "summary": summary,
                "subsystems": [
                    {
                        "name": "tests",
                        "health": args.health,
                        "detail": f"passed={args.tests_passed} failed={args.tests_failed} "
                                  f"exit={args.exit_code} duration={args.duration_sec}s",
                    }
                ],
                "counters": {
                    "test_run_duration_sec": args.duration_sec,
                    "test_run_exit_code": args.exit_code,
                },
                "last_event": {
                    "ts": ts,
                    "type": "test.run.completed",
                    "summary": summary,
                },
            }
            if args.tests_passed >= 0:
                doc["counters"]["tests_passed"] = args.tests_passed
            if args.tests_failed >= 0:
                doc["counters"]["tests_failed"] = args.tests_failed
            _hand_rolled_write(target, doc)
        print(f"[emit-status] wrote {target} ({args.health})")
        return 0
    except Exception as exc:
        print(f"[emit-status] write failed (non-fatal): {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
