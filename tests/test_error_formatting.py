"""Tests for error formatting utilities."""

from safewrite import (
    extract_line_column_from_message,
    format_error_with_context,
    format_validation_errors,
    summarize_errors,
)


class TestErrorFormatting:
    def test_format_error_with_context(self):
        content = """line 1
line 2
line 3
line 4 with error
line 5
line 6"""

        formatted = format_error_with_context(
            "Test error message",
            content,
            line=4,
            column=10,
            context_window=2,
        )

        assert "Test error message" in formatted
        assert "Line 4" in formatted
        assert "line 4 with error" in formatted
        assert ">>>" in formatted

    def test_format_error_no_line_number(self):
        formatted = format_error_with_context(
            "Generic error",
            "some content",
            line=None,
        )

        assert "Generic error" in formatted
        assert ">>>" not in formatted

    def test_extract_line_column_from_message(self):
        error_msg = "Opening and ending tag mismatch: p line 47 and section, line 52, column 3"

        line, column = extract_line_column_from_message(error_msg)

        assert line == 47 or line == 52
        assert column == 3

    def test_extract_line_column_no_match(self):
        error_msg = "Some error without location"

        line, column = extract_line_column_from_message(error_msg)

        assert line is None
        assert column is None

    def test_summarize_errors_few(self):
        errors = ["Error 1", "Error 2"]

        summary = summarize_errors(errors, max_errors=5)

        assert "Error 1" in summary
        assert "Error 2" in summary

    def test_summarize_errors_many(self):
        errors = [f"Error {i}" for i in range(10)]

        summary = summarize_errors(errors, max_errors=3)

        assert "Error 0" in summary
        assert "Error 1" in summary
        assert "Error 2" in summary
        assert "7 more" in summary

    def test_format_validation_errors(self):
        errors = [
            "line 10: Missing required element",
            "line 20: Invalid attribute value",
        ]
        content = "\n".join([f"line {i}" for i in range(30)])

        formatted = format_validation_errors(errors, content)

        assert "2 validation error" in formatted
        assert "Missing required element" in formatted
        assert "Invalid attribute value" in formatted
