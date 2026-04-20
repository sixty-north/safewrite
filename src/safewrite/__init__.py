"""safewrite: invariant-preserving document wrappers for agents.

safewrite provides three composable primitives for agents that modify
persistent structured documents:

- :class:`ValidatedDocument` — a document that is always well-formed
  and schema-valid by construction.
- :class:`FixingLoop` — validate-repair-re-validate, format-agnostic.
- :class:`Checkpoint` — atomic rollback at file, multi-file, or
  directory granularity.

The core is format-agnostic. Install the XML plugin with
``pip install safewrite[xml]`` and import from :mod:`safewrite.xml`.
"""

from .checkpoint import Checkpoint, DirectoryCheckpoint, MultiFileCheckpoint
from .error_formatting import (
    ErrorLocation,
    FormattedError,
    LocationExtractor,
    extract_line_column_from_message,
    format_error_with_context,
    format_validation_errors,
    summarize_errors,
)
from .exceptions import (
    CheckpointError,
    DocumentIntegrityError,
    DocumentParseError,
    InvariantViolationError,
    MutationFailedError,
    SchemaValidationError,
)
from .fixing_loop import (
    FixingLoop,
    FixingLoopResult,
    FixingLoopStatus,
    RepairFunction,
    ValidateFunction,
    run_fixing_loop,
)
from .validated_document import DocumentMutation, ValidatedDocument

__all__ = [
    # Core abstractions
    "ValidatedDocument",
    "DocumentMutation",
    # Checkpoints
    "Checkpoint",
    "MultiFileCheckpoint",
    "DirectoryCheckpoint",
    # Fixing loop
    "FixingLoop",
    "FixingLoopResult",
    "FixingLoopStatus",
    "RepairFunction",
    "ValidateFunction",
    "run_fixing_loop",
    # Error formatting
    "ErrorLocation",
    "FormattedError",
    "LocationExtractor",
    "extract_line_column_from_message",
    "format_error_with_context",
    "format_validation_errors",
    "summarize_errors",
    # Exceptions
    "DocumentIntegrityError",
    "DocumentParseError",
    "SchemaValidationError",
    "MutationFailedError",
    "CheckpointError",
    "InvariantViolationError",
]
