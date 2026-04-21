"""XML-specific exceptions."""

from __future__ import annotations

from pathlib import Path

from ..exceptions import DocumentParseError


class XMLParseError(DocumentParseError):
    """Raised when XML cannot be parsed.

    Inherits from :class:`wellformed.DocumentParseError` so callers can
    catch parse failures generically without knowing the document format.
    """

    def __init__(
        self,
        message: str,
        filepath: Path | None = None,
        line: int | None = None,
        column: int | None = None,
    ):
        super().__init__(message, filepath=filepath, line=line, column=column)
