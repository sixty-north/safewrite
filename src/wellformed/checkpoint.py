"""Checkpoint management for document rollback."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

from .exceptions import CheckpointError

if TYPE_CHECKING:
    from .validated_document import ValidatedDocument

T = TypeVar("T", bound="ValidatedDocument")


@dataclass
class Checkpoint(Generic[T]):
    """A checkpoint for restoring document state.

    Checkpoints enable atomic modifications by preserving the original
    document state before mutations. If a mutation fails, the checkpoint
    can restore the original state.

    Usage:
        doc = await MyValidatedDocument.load(filepath)
        checkpoint = doc.checkpoint()
        try:
            new_doc = await doc.apply(mutation)
            new_doc.save()
            checkpoint.discard()
        except MutationFailedError:
            checkpoint.restore()
    """

    filepath: Path
    content: str
    document_cls: type[T] | None

    _discarded: bool = field(default=False, init=False)
    _restored: bool = field(default=False, init=False)

    def restore(self) -> None:
        """Restore the document to its checkpointed state.

        Raises:
            CheckpointError: If checkpoint was already discarded or restored,
                or if the restore operation fails.
        """
        if self._discarded:
            raise CheckpointError("Cannot restore a discarded checkpoint")
        if self._restored:
            raise CheckpointError("Checkpoint has already been restored")

        try:
            self.filepath.write_text(self.content, encoding="utf-8")
            self._restored = True
        except OSError as e:
            raise CheckpointError(f"Failed to restore checkpoint: {e}") from e

    def discard(self) -> None:
        """Discard this checkpoint.

        Raises:
            CheckpointError: If checkpoint was already discarded or restored.
        """
        if self._discarded:
            raise CheckpointError("Checkpoint has already been discarded")
        if self._restored:
            raise CheckpointError("Cannot discard a restored checkpoint")

        self._discarded = True

    @property
    def is_active(self) -> bool:
        return not self._discarded and not self._restored


@dataclass
class MultiFileCheckpoint:
    """A checkpoint for multiple files.

    Useful when an operation modifies several documents as a single
    atomic unit.
    """

    checkpoints: list[Checkpoint] = field(default_factory=list)

    _discarded: bool = field(default=False, init=False)
    _restored: bool = field(default=False, init=False)

    def add(self, checkpoint: Checkpoint) -> None:
        if self._discarded or self._restored:
            raise CheckpointError("Cannot add to an inactive multi-file checkpoint")
        self.checkpoints.append(checkpoint)

    def restore(self) -> None:
        """Restore all files to their checkpointed state.

        Restores files in reverse order (LIFO) to handle dependencies.
        """
        if self._discarded:
            raise CheckpointError("Cannot restore a discarded checkpoint")
        if self._restored:
            raise CheckpointError("Checkpoint has already been restored")

        errors = []
        for checkpoint in reversed(self.checkpoints):
            if checkpoint.is_active:
                try:
                    checkpoint.restore()
                except CheckpointError as e:
                    errors.append(str(e))

        self._restored = True

        if errors:
            raise CheckpointError(f"Partial restore failure: {errors}")

    def discard(self) -> None:
        if self._discarded:
            raise CheckpointError("Checkpoint has already been discarded")
        if self._restored:
            raise CheckpointError("Cannot discard a restored checkpoint")

        for checkpoint in self.checkpoints:
            if checkpoint.is_active:
                checkpoint.discard()

        self._discarded = True

    @property
    def is_active(self) -> bool:
        return not self._discarded and not self._restored


@dataclass
class DirectoryCheckpoint:
    """A checkpoint for an entire directory.

    Useful for operations that may create or delete files.
    """

    original_dirpath: Path
    backup_dirpath: Path

    _discarded: bool = field(default=False, init=False)
    _restored: bool = field(default=False, init=False)

    @classmethod
    def create(cls, dirpath: Path, backup_suffix: str = ".checkpoint") -> "DirectoryCheckpoint":
        """Create a checkpoint by copying the directory.

        Raises:
            CheckpointError: If the backup cannot be created
        """
        backup_dirpath = dirpath.with_name(dirpath.name + backup_suffix)

        if backup_dirpath.exists():
            shutil.rmtree(backup_dirpath)

        try:
            shutil.copytree(dirpath, backup_dirpath)
        except OSError as e:
            raise CheckpointError(f"Failed to create directory checkpoint: {e}") from e

        return cls(original_dirpath=dirpath, backup_dirpath=backup_dirpath)

    def restore(self) -> None:
        if self._discarded:
            raise CheckpointError("Cannot restore a discarded checkpoint")
        if self._restored:
            raise CheckpointError("Checkpoint has already been restored")

        try:
            if self.original_dirpath.exists():
                shutil.rmtree(self.original_dirpath)
            shutil.move(str(self.backup_dirpath), str(self.original_dirpath))
            self._restored = True
        except OSError as e:
            raise CheckpointError(f"Failed to restore directory checkpoint: {e}") from e

    def discard(self) -> None:
        if self._discarded:
            raise CheckpointError("Checkpoint has already been discarded")
        if self._restored:
            raise CheckpointError("Cannot discard a restored checkpoint")

        try:
            if self.backup_dirpath.exists():
                shutil.rmtree(self.backup_dirpath)
            self._discarded = True
        except OSError as e:
            raise CheckpointError(f"Failed to discard checkpoint: {e}") from e

    @property
    def is_active(self) -> bool:
        return not self._discarded and not self._restored
