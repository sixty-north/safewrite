"""JSON validation function builders.

These return :class:`wellformed.ValidateFunction` callables that can be
passed to :class:`wellformed.FixingLoop` or used as the schema-validation
hook inside :class:`JSONValidatedDocument` subclasses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import jsonschema

from ..fixing_loop import ValidateFunction


def make_json_wellformed_validator() -> ValidateFunction:
    """Return a validator that checks only JSON well-formedness."""

    def validate(content: str) -> list[str]:
        try:
            json.loads(content)
            return []
        except json.JSONDecodeError as e:
            return [str(e)]

    return validate


def make_schema_validator(
    schema_validate: Callable[[str], list[str]],
) -> ValidateFunction:
    """Compose a JSON well-formedness check with a callable schema check.

    Args:
        schema_validate: A function that takes content and returns a list
            of schema error messages (empty if valid).
    """

    def validate(content: str) -> list[str]:
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return [f"JSON parse error: {e}"]

        return schema_validate(content)

    return validate


def make_json_schema_validator(schema_path: Path) -> ValidateFunction:
    """Build a validator that checks content against a JSON Schema.

    Args:
        schema_path: Path to a JSON Schema file (``.json``). The schema
            is compiled once against the 2020-12 draft meta-schema and
            reused across calls.
    """
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    validator = jsonschema.Draft202012Validator(schema)

    def validate(content: str) -> list[str]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            return [f"JSON parse error: {e}"]

        return [str(err.message) for err in validator.iter_errors(parsed)]

    return validate
