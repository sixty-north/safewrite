"""ValidatedDocument: always-valid document wrappers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Self, TypeVar

from .checkpoint import Checkpoint
from .error_formatting import format_validation_errors
from .exceptions import DocumentParseError, MutationFailedError, SchemaValidationError
from .fixing_loop import FixingLoop, FixingLoopStatus, ValidateFunction

logger = logging.getLogger(__name__)

ParsedT = TypeVar("ParsedT")


@dataclass
class DocumentMutation(Generic[ParsedT]):
    """A mutation to apply to a document.

    Subclass and override :meth:`execute` to produce new content. The
    returned content is validated before being accepted. If validation
    fails, the fixing loop attempts repair.
    """

    name: str
    description: str = ""

    async def execute(self, content: str, parsed: ParsedT) -> str:
        """Execute this mutation on document content.

        Args:
            content: The current document content (string).
            parsed: The already-parsed representation — format-specific
                (e.g. ``lxml.etree._Element`` for XML, ``dict`` for JSON).

        Returns:
            The mutated document content as a string.

        Raises:
            MutationFailedError: If the mutation cannot be executed.
        """
        raise NotImplementedError("Subclasses must implement execute()")


@dataclass
class ValidatedDocument(ABC, Generic[ParsedT]):
    """A document guaranteed to be well-formed and schema-compliant.

    Core invariant: an instance always holds content that parsed
    successfully and passed schema validation. Invalid content cannot
    be represented.

    Subclasses must implement four hooks:

    - :meth:`_parse` — parse content into ``ParsedT``; raise
      :class:`DocumentParseError` on failure.
    - :meth:`_validate_schema` — return a list of schema error messages.
    - :meth:`_get_document_type` — short identifier used in logs/errors.
    - :meth:`_repair` — produce repaired content from invalid content
      and a list of errors; typically an LLM call.
    """

    filepath: Path
    content: str
    parsed: ParsedT = field(repr=False)

    @classmethod
    @abstractmethod
    def _parse(cls, content: str) -> ParsedT:
        """Parse content into the parsed representation.

        Raises:
            DocumentParseError: If content cannot be parsed.
        """
        ...

    @classmethod
    @abstractmethod
    def _validate_schema(cls, content: str) -> list[str]:
        """Validate content against the document schema.

        Returns:
            List of validation error messages (empty if valid).
        """
        ...

    @classmethod
    @abstractmethod
    def _get_document_type(cls) -> str:
        """Return a short string identifier for the document type."""
        ...

    @classmethod
    @abstractmethod
    async def _repair(cls, content: str, errors: list[str], document_type: str) -> str:
        """Repair invalid document content.

        Typically an LLM call, but can be rule-based or human-in-the-loop.
        """
        ...

    @classmethod
    def _validate_fn(cls) -> ValidateFunction:
        """Return the combined validation function (parse + schema).

        Default implementation calls :meth:`_parse` once (catching
        :class:`DocumentParseError`) then :meth:`_validate_schema`.
        Subclasses can override if they need a different composition.
        """

        def validate(content: str) -> list[str]:
            try:
                cls._parse(content)
            except DocumentParseError as e:
                return [str(e)]
            return cls._validate_schema(content)

        return validate

    @classmethod
    async def load(cls, filepath: Path) -> Self:
        """Load and validate a document from disk.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            DocumentParseError: If content cannot be parsed.
            SchemaValidationError: If content fails schema validation.
        """
        content = filepath.read_text(encoding="utf-8")
        parsed = cls._parse(content)

        errors = cls._validate_schema(content)
        if errors:
            raise SchemaValidationError(
                f"{cls._get_document_type()} failed schema validation",
                filepath=filepath,
                errors=errors,
            )

        return cls(filepath=filepath, content=content, parsed=parsed)

    @classmethod
    async def load_with_repair(
        cls,
        filepath: Path,
        max_attempts: int = 3,
    ) -> Self:
        """Load with an automatic fixing loop if the document is invalid.

        If repair succeeds, the repaired content is written back to disk.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            MutationFailedError: If validation fails after all repair attempts.
        """
        content = filepath.read_text(encoding="utf-8")

        loop = FixingLoop(max_attempts=max_attempts)
        result = await loop.run(
            content=content,
            validate_fn=cls._validate_fn(),
            document_type=cls._get_document_type(),
            repair_fn=cls._repair,
        )

        if result.status == FixingLoopStatus.FAILED:
            formatted_errors = format_validation_errors(result.final_errors, result.content)
            raise MutationFailedError(
                f"Failed to repair {cls._get_document_type()} at {filepath} "
                f"after {result.attempts} attempts:\n{formatted_errors}",
                repair_attempts=result.attempts,
                final_errors=result.final_errors,
            )

        if result.status == FixingLoopStatus.SUCCESS:
            logger.info(f"Repaired {cls._get_document_type()} at {filepath} after {result.attempts} attempt(s)")
            filepath.write_text(result.content, encoding="utf-8")

        parsed = cls._parse(result.content)
        return cls(filepath=filepath, content=result.content, parsed=parsed)

    @classmethod
    async def from_content(
        cls,
        content: str,
        filepath: Path,
        validate: bool = True,
    ) -> Self:
        """Create a document from an in-memory content string.

        Args:
            content: The document content.
            filepath: Path where the document will be saved.
            validate: Whether to run schema validation (raises on failure).

        Raises:
            DocumentParseError: If content cannot be parsed.
            SchemaValidationError: If ``validate`` and content fails schema.
        """
        parsed = cls._parse(content)

        if validate:
            errors = cls._validate_schema(content)
            if errors:
                raise SchemaValidationError(
                    f"{cls._get_document_type()} failed schema validation",
                    filepath=filepath,
                    errors=errors,
                )

        return cls(filepath=filepath, content=content, parsed=parsed)

    async def apply(
        self,
        mutation: DocumentMutation[ParsedT],
        max_fix_attempts: int = 3,
    ) -> Self:
        """Apply a mutation, returning a new ValidatedDocument.

        The mutation runs, the result is validated, and the fixing loop
        repairs it if invalid.

        Raises:
            MutationFailedError: If the mutation fails after all repairs.
        """
        logger.info(f"Applying mutation '{mutation.name}' to {self.filepath}")

        try:
            mutated_content = await mutation.execute(self.content, self.parsed)
        except MutationFailedError:
            raise
        except Exception as e:
            # Mutations are user-provided callables; surface their failure
            # through the library's own exception type for consistency.
            raise MutationFailedError(
                f"Mutation '{mutation.name}' failed: {e}",
                original_error=e,
            ) from e

        loop = FixingLoop(max_attempts=max_fix_attempts)
        result = await loop.run(
            content=mutated_content,
            validate_fn=self._validate_fn(),
            document_type=self._get_document_type(),
            repair_fn=self._repair,
        )

        if result.status == FixingLoopStatus.FAILED:
            formatted_errors = format_validation_errors(result.final_errors, result.content)
            raise MutationFailedError(
                f"Mutation '{mutation.name}' produced invalid content "
                f"that could not be repaired after {result.attempts} attempts:\n"
                f"{formatted_errors}",
                repair_attempts=result.attempts,
                final_errors=result.final_errors,
            )

        parsed = type(self)._parse(result.content)
        return type(self)(
            filepath=self.filepath,
            content=result.content,
            parsed=parsed,
        )

    def checkpoint(self) -> Checkpoint[Self]:
        """Create a checkpoint for rollback."""
        return Checkpoint(
            filepath=self.filepath,
            content=self.content,
            document_cls=type(self),
        )

    def save(self) -> None:
        """Write the validated content to disk."""
        self.filepath.write_text(self.content, encoding="utf-8")
        logger.debug(f"Saved {self._get_document_type()} to {self.filepath}")

    def refresh_parsed(self) -> None:
        """Re-parse the in-memory representation from :attr:`content`.

        Useful after external modifications to keep ``parsed`` in sync.
        """
        self.parsed = self._parse(self.content)
