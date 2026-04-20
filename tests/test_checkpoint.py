"""Tests for Checkpoint class."""

import pytest

from safewrite import Checkpoint, CheckpointError


class TestCheckpoint:
    def test_checkpoint_restore(self, tmp_path):
        test_file = tmp_path / "test.txt"
        original_content = "original content"
        test_file.write_text(original_content)

        checkpoint = Checkpoint(
            filepath=test_file,
            content=original_content,
            document_cls=None,
        )

        test_file.write_text("modified content")
        assert test_file.read_text() == "modified content"

        checkpoint.restore()
        assert test_file.read_text() == original_content

    def test_checkpoint_discard(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        checkpoint = Checkpoint(
            filepath=test_file,
            content="content",
            document_cls=None,
        )

        checkpoint.discard()
        assert not checkpoint.is_active

    def test_checkpoint_restore_after_discard_raises(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        checkpoint = Checkpoint(
            filepath=test_file,
            content="content",
            document_cls=None,
        )

        checkpoint.discard()

        with pytest.raises(CheckpointError):
            checkpoint.restore()

    def test_checkpoint_double_restore_raises(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        checkpoint = Checkpoint(
            filepath=test_file,
            content="content",
            document_cls=None,
        )

        checkpoint.restore()

        with pytest.raises(CheckpointError):
            checkpoint.restore()

    def test_checkpoint_is_active(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        checkpoint = Checkpoint(
            filepath=test_file,
            content="content",
            document_cls=None,
        )

        assert checkpoint.is_active

        checkpoint.discard()
        assert not checkpoint.is_active
