"""JSONValidatedDocument: a ValidatedDocument for JSON content."""

from __future__ import annotations

import json
from abc import abstractmethod
from typing import Any

from ..validated_document import ValidatedDocument
from .exceptions import JSONParseError


class JSONValidatedDocument(ValidatedDocument[Any]):
    """Base class for always-valid JSON documents.

    Subclasses override the same three hooks as any
    :class:`wellformed.ValidatedDocument`:

    - ``_validate_schema`` — return schema error messages
    - ``_get_document_type`` — short identifier
    - ``_repair`` — produce repaired content (typically an LLM call)

    JSON parsing is handled by this base class via the stdlib
    :mod:`json` module. The ``parsed`` attribute is the result of
    :func:`json.loads` — typically a ``dict`` or ``list``, though any
    JSON value (``str``, ``int``, ``float``, ``bool``, ``None``) is
    possible at the top level.
    """

    @classmethod
    def _parse(cls, content: str) -> Any:
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise JSONParseError(str(e), line=e.lineno, column=e.colno) from e

    @classmethod
    @abstractmethod
    def _validate_schema(cls, content: str) -> list[str]: ...

    @classmethod
    @abstractmethod
    def _get_document_type(cls) -> str: ...

    @classmethod
    @abstractmethod
    async def _repair(cls, content: str, errors: list[str], document_type: str) -> str: ...
