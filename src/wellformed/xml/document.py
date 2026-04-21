"""XMLValidatedDocument: a ValidatedDocument for XML content."""

from __future__ import annotations

from abc import abstractmethod

from lxml import etree

from ..validated_document import ValidatedDocument
from .exceptions import XMLParseError


class XMLValidatedDocument(ValidatedDocument[etree._Element]):
    """Base class for always-valid XML documents.

    Subclasses override the same three hooks as any
    :class:`wellformed.ValidatedDocument`:

    - ``_validate_schema`` — return schema error messages
    - ``_get_document_type`` — short identifier
    - ``_repair`` — produce repaired content (typically an LLM call)

    XML parsing is handled by this base class via lxml.
    """

    @classmethod
    def _parse(cls, content: str) -> etree._Element:
        try:
            return etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            raise XMLParseError(str(e), line=e.lineno, column=e.offset) from e

    @classmethod
    @abstractmethod
    def _validate_schema(cls, content: str) -> list[str]: ...

    @classmethod
    @abstractmethod
    def _get_document_type(cls) -> str: ...

    @classmethod
    @abstractmethod
    async def _repair(cls, content: str, errors: list[str], document_type: str) -> str: ...

    @property
    def tree(self) -> etree._Element:
        """Alias for :attr:`parsed`, matching common lxml idioms."""
        return self.parsed
