"""Tests for ValidatedDocument against a toy dict-based format.

These tests exercise the generic (format-agnostic) path of the library
using nothing but the Python standard library — proving the core works
without any of the optional plugin dependencies installed.

The toy format: content is JSON object with a mandatory "title" string
and a mandatory integer "count" >= 0. Parsing uses stdlib json; schema
validation checks the required fields and types.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from safewrite import (
    DocumentMutation,
    DocumentParseError,
    MutationFailedError,
    SchemaValidationError,
    ValidatedDocument,
)


@dataclass
class ToyDocument(ValidatedDocument[dict]):
    @classmethod
    def _parse(cls, content: str) -> dict:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise DocumentParseError(str(e), line=e.lineno, column=e.colno) from e
        if not isinstance(data, dict):
            raise DocumentParseError("Root must be a JSON object")
        return data

    @classmethod
    def _validate_schema(cls, content: str) -> list[str]:
        data = json.loads(content)
        errors = []
        if "title" not in data:
            errors.append("missing required field 'title'")
        elif not isinstance(data["title"], str):
            errors.append("'title' must be a string")
        if "count" not in data:
            errors.append("missing required field 'count'")
        elif not isinstance(data["count"], int) or data["count"] < 0:
            errors.append("'count' must be a non-negative integer")
        return errors

    @classmethod
    def _get_document_type(cls) -> str:
        return "toy"

    @classmethod
    async def _repair(cls, content: str, errors: list[str], document_type: str) -> str:
        # Deterministic repair that fills in missing fields with defaults.
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {}
        if "title" not in data or not isinstance(data.get("title"), str):
            data["title"] = "untitled"
        if "count" not in data or not isinstance(data.get("count"), int) or data["count"] < 0:
            data["count"] = 0
        return json.dumps(data)


async def test_load_success(tmp_path):
    f = tmp_path / "doc.json"
    f.write_text('{"title": "hello", "count": 3}')

    doc = await ToyDocument.load(f)

    assert doc.content == '{"title": "hello", "count": 3}'
    assert doc.parsed == {"title": "hello", "count": 3}


async def test_load_raises_on_parse_failure(tmp_path):
    f = tmp_path / "doc.json"
    f.write_text("not valid json {")

    with pytest.raises(DocumentParseError):
        await ToyDocument.load(f)


async def test_load_raises_on_schema_failure(tmp_path):
    f = tmp_path / "doc.json"
    f.write_text('{"title": "hello"}')  # missing count

    with pytest.raises(SchemaValidationError) as exc_info:
        await ToyDocument.load(f)

    assert any("count" in e for e in exc_info.value.errors)


async def test_load_with_repair_fills_in_missing_fields(tmp_path):
    f = tmp_path / "doc.json"
    f.write_text('{"title": "hello"}')

    doc = await ToyDocument.load_with_repair(f)

    assert doc.parsed["title"] == "hello"
    assert doc.parsed["count"] == 0
    # Repair writes the fixed content back to disk.
    on_disk = json.loads(f.read_text())
    assert on_disk["count"] == 0


async def test_load_with_repair_raises_when_repair_insufficient(tmp_path):
    class StubbornlyInvalid(ToyDocument):
        @classmethod
        async def _repair(cls, content, errors, document_type):
            return content  # refuses to help

    f = tmp_path / "doc.json"
    f.write_text('{"title": "hello"}')

    with pytest.raises(MutationFailedError):
        await StubbornlyInvalid.load_with_repair(f, max_attempts=2)


async def test_from_content_without_validation(tmp_path):
    # Schema-invalid but parseable content is allowed when validate=False.
    doc = await ToyDocument.from_content('{"title": "hi"}', tmp_path / "x.json", validate=False)
    assert doc.parsed == {"title": "hi"}


async def test_from_content_with_validation_raises(tmp_path):
    with pytest.raises(SchemaValidationError):
        await ToyDocument.from_content('{"title": "hi"}', tmp_path / "x.json", validate=True)


class IncrementCount(DocumentMutation[dict]):
    async def execute(self, content: str, parsed: dict) -> str:
        parsed["count"] += 1
        return json.dumps(parsed)


async def test_apply_mutation_succeeds(tmp_path):
    f = tmp_path / "doc.json"
    f.write_text('{"title": "hello", "count": 3}')
    doc = await ToyDocument.load(f)

    new_doc = await doc.apply(IncrementCount(name="increment"))

    assert new_doc.parsed["count"] == 4
    assert new_doc is not doc


class BreakSchema(DocumentMutation[dict]):
    async def execute(self, content: str, parsed: dict) -> str:
        del parsed["count"]
        return json.dumps(parsed)


async def test_apply_triggers_fixing_loop_on_invalid_result(tmp_path):
    f = tmp_path / "doc.json"
    f.write_text('{"title": "hello", "count": 3}')
    doc = await ToyDocument.load(f)

    new_doc = await doc.apply(BreakSchema(name="break"))

    # Repair fills in count=0 after the mutation removed it.
    assert new_doc.parsed["count"] == 0


async def test_checkpoint_round_trip(tmp_path):
    f = tmp_path / "doc.json"
    original = '{"title": "hello", "count": 3}'
    f.write_text(original)
    doc = await ToyDocument.load(f)

    checkpoint = doc.checkpoint()

    # Simulate a destructive external change.
    f.write_text('{"title": "bye", "count": 99}')

    checkpoint.restore()
    assert f.read_text() == original


async def test_save_writes_content(tmp_path):
    f = tmp_path / "doc.json"
    f.write_text('{"title": "hello", "count": 3}')
    doc = await ToyDocument.load(f)
    f.write_text("clobbered")

    doc.save()
    assert f.read_text() == '{"title": "hello", "count": 3}'


async def test_refresh_parsed(tmp_path):
    doc = await ToyDocument.from_content(
        '{"title": "a", "count": 1}',
        tmp_path / "doc.json",
    )
    # Replace content externally, then refresh.
    doc.content = '{"title": "b", "count": 2}'
    doc.refresh_parsed()
    assert doc.parsed == {"title": "b", "count": 2}
