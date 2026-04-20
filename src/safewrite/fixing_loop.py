"""Inner fixing loop for repairing invalid documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .error_formatting import summarize_errors
from .exceptions import MutationFailedError

logger = logging.getLogger(__name__)


class FixingLoopStatus(Enum):
    SUCCESS = "success"
    ALREADY_VALID = "already_valid"
    FAILED = "failed"


@dataclass
class FixingLoopResult:
    status: FixingLoopStatus
    content: str
    attempts: int = 0
    final_errors: list[str] = field(default_factory=list)
    repair_history: list[str] = field(default_factory=list)


class RepairFunction(Protocol):
    """Protocol for document repair functions.

    The repair function is format-agnostic. It can be an LLM call, a
    rule-based fixer, or a human-in-the-loop — the fixing loop does not
    care. Return the repaired content; raise any exception to signal
    failure and continue to the next attempt.
    """

    async def __call__(
        self,
        content: str,
        errors: list[str],
        document_type: str,
    ) -> str: ...


class ValidateFunction(Protocol):
    """Protocol for document validation functions.

    Returns a list of error messages. Empty list means "valid".
    """

    def __call__(self, content: str) -> list[str]: ...


@dataclass
class FixingLoop:
    """Inner loop for repairing invalid documents.

    Repeatedly validates and repairs content until it is valid or
    ``max_attempts`` is reached.
    """

    max_attempts: int = 3
    repair_fn: RepairFunction | None = None

    async def run(
        self,
        content: str,
        validate_fn: ValidateFunction,
        document_type: str,
        repair_fn: RepairFunction | None = None,
    ) -> FixingLoopResult:
        repair = repair_fn or self.repair_fn
        current_content = content
        repair_history = []

        errors = validate_fn(current_content)

        if not errors:
            return FixingLoopResult(
                status=FixingLoopStatus.ALREADY_VALID,
                content=current_content,
                attempts=0,
            )

        if repair is None:
            return FixingLoopResult(
                status=FixingLoopStatus.FAILED,
                content=current_content,
                attempts=0,
                final_errors=errors,
            )

        for attempt in range(1, self.max_attempts + 1):
            logger.info(
                f"Fixing loop attempt {attempt}/{self.max_attempts} for {document_type}: {len(errors)} error(s)"
            )

            repair_history.append(f"Attempt {attempt}: {len(errors)} error(s)")

            try:
                repaired_content = await repair(
                    current_content,
                    errors,
                    document_type,
                )
            except Exception as e:
                # Repair is user-provided (often an LLM call); isolate its
                # failures from the loop so one bad attempt doesn't abort
                # the whole retry cycle.
                logger.warning(f"Repair function failed: {e}")
                repair_history.append(f"Attempt {attempt} repair failed: {e}")
                continue

            current_content = repaired_content
            errors = validate_fn(current_content)

            if not errors:
                logger.info(f"Fixing loop succeeded after {attempt} attempt(s)")
                return FixingLoopResult(
                    status=FixingLoopStatus.SUCCESS,
                    content=current_content,
                    attempts=attempt,
                    repair_history=repair_history,
                )

            logger.info(f"Attempt {attempt} reduced errors to {len(errors)}")

        logger.warning(f"Fixing loop failed after {self.max_attempts} attempts: {len(errors)} error(s) remain")
        return FixingLoopResult(
            status=FixingLoopStatus.FAILED,
            content=current_content,
            attempts=self.max_attempts,
            final_errors=errors,
            repair_history=repair_history,
        )


async def run_fixing_loop(
    content: str,
    validate_fn: ValidateFunction,
    repair_fn: RepairFunction,
    document_type: str,
    max_attempts: int = 3,
) -> str:
    """Convenience wrapper: run a fixing loop and return content or raise.

    Raises:
        MutationFailedError: If validation fails after all repair attempts.
    """
    loop = FixingLoop(max_attempts=max_attempts)
    result = await loop.run(content, validate_fn, document_type, repair_fn)

    if result.status == FixingLoopStatus.FAILED:
        error_summary = summarize_errors(result.final_errors)
        raise MutationFailedError(
            f"Failed to repair {document_type} after {result.attempts} attempts:\n{error_summary}",
            repair_attempts=result.attempts,
            final_errors=result.final_errors,
        )

    return result.content
