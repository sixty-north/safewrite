"""Exceptions for safewrite's core document integrity layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class DocumentIntegrityError(Exception):
    """Base exception for document integrity errors."""


class DocumentParseError(DocumentIntegrityError):
    """Raised when a document cannot be parsed by its format plugin.

    Format-specific plugins should subclass this with richer fields
    (e.g. XMLParseError adds line/column; a hypothetical JSONParseError
    might add a JSON pointer path).
    """

    def __init__(
        self,
        message: str,
        filepath: Path | None = None,
        line: int | None = None,
        column: int | None = None,
    ):
        self.filepath = filepath
        self.line = line
        self.column = column
        super().__init__(message)


class SchemaValidationError(DocumentIntegrityError):
    """Raised when document fails schema validation."""

    def __init__(self, message: str, filepath: Path | None = None, errors: list[str] | None = None):
        self.filepath = filepath
        self.errors = errors or []
        super().__init__(message)


class MutationFailedError(DocumentIntegrityError):
    """Raised when a document mutation fails after all repair attempts."""

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        repair_attempts: int = 0,
        final_errors: list[str] | None = None,
    ):
        self.original_error = original_error
        self.repair_attempts = repair_attempts
        self.final_errors = final_errors or []
        super().__init__(message)


class CheckpointError(DocumentIntegrityError):
    """Raised when checkpoint operations fail."""


@dataclass
class InvariantViolationError(DocumentIntegrityError):
    """Raised when an operation violates lower-layer invariants."""

    current_layer: int
    broken_layer: int
    violations: list[str]

    def __str__(self) -> str:
        return f"Layer {self.current_layer} operation violated Layer {self.broken_layer} invariants: {self.violations}"
