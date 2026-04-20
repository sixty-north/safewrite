"""XML validation function builders.

These return :class:`safewrite.ValidateFunction` callables that can be
passed to :class:`safewrite.FixingLoop` or used as the schema-validation
hook inside :class:`XMLValidatedDocument` subclasses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from lxml import etree

from ..fixing_loop import ValidateFunction


def make_xml_wellformed_validator() -> ValidateFunction:
    """Return a validator that checks only XML well-formedness."""

    def validate(content: str) -> list[str]:
        try:
            etree.fromstring(content.encode("utf-8"))
            return []
        except etree.XMLSyntaxError as e:
            return [str(e)]

    return validate


def make_schema_validator(
    schema_validate: Callable[[str], list[str]],
) -> ValidateFunction:
    """Compose an XML well-formedness check with a callable schema check.

    Args:
        schema_validate: A function that takes content and returns a list
            of schema error messages (empty if valid).
    """

    def validate(content: str) -> list[str]:
        try:
            etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            return [f"XML parse error: {e}"]

        return schema_validate(content)

    return validate


def make_relax_ng_validator(schema_path: Path) -> ValidateFunction:
    """Build a validator that checks content against a RELAX NG schema.

    Args:
        schema_path: Path to a ``.rng`` file.
    """
    with schema_path.open("rb") as f:
        schema_doc = etree.parse(f)
    schema = etree.RelaxNG(schema_doc)

    def validate(content: str) -> list[str]:
        try:
            doc = etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            return [f"XML parse error: {e}"]

        if schema.validate(doc):
            return []
        return [str(err) for err in schema.error_log]

    return validate


def make_xml_schema_validator(xsd_path: Path) -> ValidateFunction:
    """Build a validator that checks content against an XSD schema.

    Args:
        xsd_path: Path to a ``.xsd`` file.
    """
    with xsd_path.open("rb") as f:
        schema_doc = etree.parse(f)
    schema = etree.XMLSchema(schema_doc)

    def validate(content: str) -> list[str]:
        try:
            doc = etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            return [f"XML parse error: {e}"]

        if schema.validate(doc):
            return []
        return [str(err) for err in schema.error_log]

    return validate
