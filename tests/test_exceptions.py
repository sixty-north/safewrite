"""Tests for custom exceptions."""

from pathlib import Path

import pytest

from safewrite import MutationFailedError


class TestExceptions:
    def test_mutation_failed_error(self):
        error = MutationFailedError(
            "Mutation failed",
            repair_attempts=3,
            final_errors=["Error 1", "Error 2"],
        )

        assert error.repair_attempts == 3
        assert len(error.final_errors) == 2

    def test_xml_parse_error(self):
        """XMLParseError lives in the XML plugin."""
        pytest.importorskip("lxml")
        from safewrite.xml import XMLParseError

        error = XMLParseError(
            "Parse failed",
            filepath=Path("/test/file.xml"),
            line=10,
            column=5,
        )

        assert error.filepath == Path("/test/file.xml")
        assert error.line == 10
        assert error.column == 5
