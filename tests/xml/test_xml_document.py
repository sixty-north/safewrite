"""Integration tests for the XML plugin."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("lxml")

from lxml import etree  # noqa: E402

from wellformed import DocumentMutation, SchemaValidationError  # noqa: E402
from wellformed.xml import XMLParseError, XMLValidatedDocument  # noqa: E402


def _has_root_tag(content: str, tag: str) -> list[str]:
    try:
        root = etree.fromstring(content.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        return [str(e)]
    if root.tag != tag:
        return [f"expected root <{tag}>, got <{root.tag}>"]
    return []


@dataclass
class NoteDocument(XMLValidatedDocument):
    @classmethod
    def _validate_schema(cls, content: str) -> list[str]:
        return _has_root_tag(content, "note")

    @classmethod
    def _get_document_type(cls) -> str:
        return "note"

    @classmethod
    async def _repair(cls, content: str, errors: list[str], document_type: str) -> str:
        # Trivial repair: wrap anything non-<note> in a <note>.
        return f"<note>{content}</note>"


async def test_load_success(tmp_path):
    f = tmp_path / "n.xml"
    f.write_text("<note>hello</note>")
    doc = await NoteDocument.load(f)
    assert doc.content == "<note>hello</note>"
    assert doc.tree.tag == "note"
    assert doc.parsed is doc.tree


async def test_malformed_xml_raises_xml_parse_error(tmp_path):
    f = tmp_path / "n.xml"
    f.write_text("<note>unclosed")
    with pytest.raises(XMLParseError) as exc_info:
        await NoteDocument.load(f)
    assert exc_info.value.line is not None


async def test_schema_failure_raises(tmp_path):
    f = tmp_path / "n.xml"
    f.write_text("<wrong/>")
    with pytest.raises(SchemaValidationError):
        await NoteDocument.load(f)


class AppendChild(DocumentMutation):
    async def execute(self, content, parsed):
        child = etree.SubElement(parsed, "line")
        child.text = "added"
        return etree.tostring(parsed, encoding="unicode")


async def test_apply_mutates_tree(tmp_path):
    f = tmp_path / "n.xml"
    f.write_text("<note>hello</note>")
    doc = await NoteDocument.load(f)
    new_doc = await doc.apply(AppendChild(name="append"))
    assert "<line>added</line>" in new_doc.content
    assert new_doc.tree.find("line").text == "added"
