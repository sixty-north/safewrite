"""Integration tests for the JSON plugin."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

pytest.importorskip("jsonschema")

from wellformed import DocumentMutation, SchemaValidationError  # noqa: E402
from wellformed.json import JSONParseError, JSONValidatedDocument  # noqa: E402


def _is_note(content: str) -> list[str]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        return [str(e)]
    if not isinstance(parsed, dict):
        return [f"expected a JSON object, got {type(parsed).__name__}"]
    if parsed.get("type") != "note":
        return [f"expected type 'note', got {parsed.get('type')!r}"]
    return []


@dataclass
class NoteDocument(JSONValidatedDocument):
    @classmethod
    def _validate_schema(cls, content: str) -> list[str]:
        return _is_note(content)

    @classmethod
    def _get_document_type(cls) -> str:
        return "note"

    @classmethod
    async def _repair(cls, content: str, errors: list[str], document_type: str) -> str:
        # Trivial repair: wrap any object in a note envelope.
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return content
        if isinstance(parsed, dict):
            parsed["type"] = "note"
            return json.dumps(parsed)
        return content


async def test_load_success(tmp_path):
    f = tmp_path / "n.json"
    f.write_text('{"type": "note", "body": "hello"}')
    doc = await NoteDocument.load(f)
    assert doc.parsed == {"type": "note", "body": "hello"}


async def test_malformed_json_raises_json_parse_error(tmp_path):
    f = tmp_path / "n.json"
    f.write_text('{"type": "note",')
    with pytest.raises(JSONParseError) as exc_info:
        await NoteDocument.load(f)
    assert exc_info.value.line is not None


async def test_schema_failure_raises(tmp_path):
    f = tmp_path / "n.json"
    f.write_text('{"type": "memo"}')
    with pytest.raises(SchemaValidationError):
        await NoteDocument.load(f)


class AppendKey(DocumentMutation):
    async def execute(self, content, parsed):
        parsed["added"] = True
        return json.dumps(parsed)


async def test_apply_mutates_parsed(tmp_path):
    f = tmp_path / "n.json"
    f.write_text('{"type": "note", "body": "hello"}')
    doc = await NoteDocument.load(f)
    new_doc = await doc.apply(AppendKey(name="append"))
    assert new_doc.parsed["added"] is True
    assert new_doc.parsed["type"] == "note"
