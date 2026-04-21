"""Error formatting utilities with source context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class ErrorLocation:
    """Location of an error in a document."""

    line: int | None = None
    column: int | None = None
    xpath: str | None = None


@dataclass
class FormattedError:
    """An error with formatted context."""

    message: str
    location: ErrorLocation
    context_lines: str


LocationExtractor = Callable[[str], tuple[int | None, int | None]]


def format_error_with_context(
    error_message: str,
    content: str,
    line: int | None = None,
    column: int | None = None,
    context_window: int = 5,
) -> str:
    """Format error with source context window around error location.

    Example output::

        Error: Element 'marker' missing required attribute 'name'
        Line 47, column 12:
             45 |   <p id="intro-p3">
             46 |     Some introductory text here.
        >>>  47 |     <marker/>
             48 |     More content follows.
             49 |   </p>
    """
    lines = content.splitlines()

    result_parts = [f"Error: {error_message}"]

    if line is not None:
        location_str = f"Line {line}"
        if column is not None:
            location_str += f", column {column}"
        result_parts.append(f"{location_str}:")

        start_line = max(0, line - 1 - context_window)
        end_line = min(len(lines), line + context_window)

        max_line_num_width = len(str(end_line))
        context_parts = []

        for i in range(start_line, end_line):
            line_num = i + 1
            line_content = lines[i] if i < len(lines) else ""

            prefix = ">>> " if line_num == line else "    "
            formatted_line = f"{prefix}{line_num:>{max_line_num_width}} | {line_content}"
            context_parts.append(formatted_line)

            if line_num == line and column is not None:
                indicator_padding = len(prefix) + max_line_num_width + 3 + column - 1
                indicator = " " * indicator_padding + "^"
                context_parts.append(indicator)

        result_parts.extend(context_parts)

    return "\n".join(result_parts)


def extract_line_column_from_message(error_message: str) -> tuple[int | None, int | None]:
    """Extract line and column numbers from a parser error message.

    Works out of the box for parsers that emit messages like
    ``"..., line X, column Y"`` (lxml, json.JSONDecoder via str()
    wrapping, and many others). Plugins can supply their own extractor
    via the ``location_extractor`` parameter of
    :func:`format_validation_errors`.
    """
    line_match = re.search(r"line (\d+)", error_message, re.IGNORECASE)
    column_match = re.search(r"column (\d+)", error_message, re.IGNORECASE)

    line = int(line_match.group(1)) if line_match else None
    column = int(column_match.group(1)) if column_match else None

    return line, column


def format_validation_errors(
    errors: list[str],
    content: str,
    context_window: int = 3,
    location_extractor: LocationExtractor | None = None,
) -> str:
    """Format multiple validation errors with source context.

    Args:
        errors: List of error messages.
        content: The document content.
        context_window: Number of context lines around each error.
        location_extractor: Callable that returns (line, column) for an
            error message. Defaults to :func:`extract_line_column_from_message`,
            which handles most parser dialects.
    """
    if not errors:
        return "No errors"

    extractor = location_extractor or extract_line_column_from_message

    formatted_parts = [f"Found {len(errors)} validation error(s):\n"]

    for i, error in enumerate(errors, 1):
        formatted_parts.append(f"--- Error {i} of {len(errors)} ---")

        line, column = extractor(error)
        formatted_error = format_error_with_context(
            error, content, line=line, column=column, context_window=context_window
        )
        formatted_parts.append(formatted_error)
        formatted_parts.append("")

    return "\n".join(formatted_parts)


def summarize_errors(errors: list[str], max_errors: int = 5) -> str:
    """Create a brief summary of errors for logging."""
    if not errors:
        return "No errors"

    if len(errors) <= max_errors:
        return "\n".join(f"  - {e}" for e in errors)

    shown = errors[:max_errors]
    remaining = len(errors) - max_errors
    summary_lines = [f"  - {e}" for e in shown]
    summary_lines.append(f"  ... and {remaining} more error(s)")
    return "\n".join(summary_lines)
