"""Tests for XML validator builders."""

from __future__ import annotations

import pytest

pytest.importorskip("lxml")

from wellformed.xml import (  # noqa: E402
    make_relax_ng_validator,
    make_schema_validator,
    make_xml_schema_validator,
    make_xml_wellformed_validator,
)


class TestWellformedValidator:
    def test_valid(self):
        validator = make_xml_wellformed_validator()
        assert validator("<root/>") == []

    def test_invalid(self):
        validator = make_xml_wellformed_validator()
        errors = validator("<root>")
        assert errors and "tag" in errors[0].lower() or "end" in errors[0].lower()


class TestSchemaValidatorComposition:
    def test_schema_checked_only_if_wellformed(self):
        def schema_fn(content):
            return ["schema check ran"]

        validator = make_schema_validator(schema_fn)
        # Malformed XML short-circuits before schema_fn runs.
        errors = validator("<bad>")
        assert not any("schema check ran" in e for e in errors)

    def test_schema_runs_when_wellformed(self):
        def schema_fn(content):
            return ["expected schema error"]

        validator = make_schema_validator(schema_fn)
        errors = validator("<root/>")
        assert errors == ["expected schema error"]


class TestRelaxNGValidator:
    def test_valid_content_passes(self, tmp_path):
        schema = tmp_path / "schema.rng"
        schema.write_text("""<?xml version="1.0"?>
<element name="note" xmlns="http://relaxng.org/ns/structure/1.0">
  <text/>
</element>""")
        validator = make_relax_ng_validator(schema)
        assert validator("<note>hello</note>") == []

    def test_invalid_content_fails(self, tmp_path):
        schema = tmp_path / "schema.rng"
        schema.write_text("""<?xml version="1.0"?>
<element name="note" xmlns="http://relaxng.org/ns/structure/1.0">
  <text/>
</element>""")
        validator = make_relax_ng_validator(schema)
        errors = validator("<wrong/>")
        assert errors


class TestXMLSchemaValidator:
    def test_valid_content_passes(self, tmp_path):
        xsd = tmp_path / "schema.xsd"
        xsd.write_text("""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="note" type="xs:string"/>
</xs:schema>""")
        validator = make_xml_schema_validator(xsd)
        assert validator("<note>hello</note>") == []

    def test_invalid_content_fails(self, tmp_path):
        xsd = tmp_path / "schema.xsd"
        xsd.write_text("""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="note" type="xs:string"/>
</xs:schema>""")
        validator = make_xml_schema_validator(xsd)
        errors = validator("<wrong/>")
        assert errors
