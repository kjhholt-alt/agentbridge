"""Tests for agentbridge.protocol -- the spec self-check loader."""

from __future__ import annotations

import json

import pytest

from agentbridge import protocol


def test_load_v1_schemas_has_four_files():
    schemas = protocol.load_v1_schemas()
    assert set(schemas.keys()) == {"commands", "responses", "events", "state"}


def test_validate_schemas_clean():
    failures = protocol.validate_schemas()
    assert failures == [], f"schemas invalid: {failures}"


def test_positive_command_fixtures_accepted():
    failures = protocol.validate_fixtures()
    assert failures == [], f"fixture validation failed: {failures}"


@pytest.mark.parametrize("fx", protocol.COMMAND_FIXTURES)
def test_each_positive_command(fx):
    from jsonschema import Draft202012Validator
    schemas = protocol.load_v1_schemas()
    v = Draft202012Validator(schemas["commands"])
    errs = list(v.iter_errors(fx))
    assert not errs, f"{fx} rejected: {errs[0].message if errs else ''}"


@pytest.mark.parametrize("fx", protocol.COMMAND_NEGATIVE_FIXTURES)
def test_each_negative_command_rejected(fx):
    from jsonschema import Draft202012Validator
    schemas = protocol.load_v1_schemas()
    v = Draft202012Validator(schemas["commands"])
    errs = list(v.iter_errors(fx))
    assert errs, f"{fx} should have been rejected"


def test_self_check_main_returns_zero(capsys):
    rc = protocol.main(["--self-check"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "self-check OK" in out
