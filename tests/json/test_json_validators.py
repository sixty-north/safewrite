"""Tests for JSON validator builders."""

from __future__ import annotations

import pytest

pytest.importorskip("jsonschema")

from wellformed.json import (  # noqa: E402
    make_json_schema_validator,
    make_json_wellformed_validator,
    make_schema_validator,
)


class TestWellformedValidator:
    def test_valid(self):
        validator = make_json_wellformed_validator()
        assert validator('{"x": 1}') == []

    def test_invalid(self):
        validator = make_json_wellformed_validator()
        errors = validator('{"x":')
        assert errors


class TestSchemaValidatorComposition:
    def test_schema_checked_only_if_wellformed(self):
        def schema_fn(content):
            return ["schema check ran"]

        validator = make_schema_validator(schema_fn)
        # Malformed JSON short-circuits before schema_fn runs.
        errors = validator('{"x":')
        assert not any("schema check ran" in e for e in errors)

    def test_schema_runs_when_wellformed(self):
        def schema_fn(content):
            return ["expected schema error"]

        validator = make_schema_validator(schema_fn)
        errors = validator('{"x": 1}')
        assert errors == ["expected schema error"]


class TestJSONSchemaValidator:
    def test_valid_content_passes(self, tmp_path):
        schema = tmp_path / "schema.json"
        schema.write_text('{"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}')
        validator = make_json_schema_validator(schema)
        assert validator('{"name": "alice"}') == []

    def test_invalid_content_fails(self, tmp_path):
        schema = tmp_path / "schema.json"
        schema.write_text('{"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}')
        validator = make_json_schema_validator(schema)
        errors = validator('{"other": 1}')
        assert errors

    def test_malformed_json_short_circuits(self, tmp_path):
        schema = tmp_path / "schema.json"
        schema.write_text('{"type": "object"}')
        validator = make_json_schema_validator(schema)
        errors = validator('{"x":')
        assert errors
        assert any("parse" in e.lower() for e in errors)
