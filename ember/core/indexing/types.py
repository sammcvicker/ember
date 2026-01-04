"""Data types for the indexing module.

Contains request/response dataclasses and errors used throughout the indexing pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ember.core.use_case_errors import EmberError


class ModelMismatchError(EmberError):
    """Raised when embedding model differs from the one used to build the index.

    This error prevents dimension mismatch errors during search by requiring
    an explicit --force flag to rebuild the index with the new model.
    """

    def __init__(self, stored_model: str, current_model: str) -> None:
        self.stored_model = stored_model
        self.current_model = current_model
        message = (
            f"Embedding model changed: {stored_model} → {current_model}. "
            f"Run 'ember sync --force' to rebuild the index with the new model."
        )
        super().__init__(message)


@dataclass
class IndexRequest:
    """Request to index (or re-index) files.

    Attributes:
        repo_root: Absolute path to repository root.
        sync_mode: Mode to sync - "worktree" (uncommitted changes), "staged", or commit SHA.
        path_filters: Optional list of path patterns to filter (e.g., ["src/**/*.py"]).
        force_reindex: If True, reindex even if files haven't changed.
    """

    repo_root: Path
    sync_mode: str = "worktree"
    path_filters: list[str] = field(default_factory=list)
    force_reindex: bool = False


@dataclass
class IndexResponse:
    """Response from indexing operation.

    Attributes:
        files_indexed: Number of files processed.
        chunks_created: Number of chunks created.
        chunks_updated: Number of chunks updated (deduplicated).
        chunks_deleted: Number of chunks deleted (from removed files).
        vectors_stored: Number of vectors stored.
        tree_sha: Git tree SHA that was indexed.
        files_failed: Number of files that failed to chunk.
        is_incremental: Whether this was an incremental sync (vs full reindex).
        success: Whether indexing succeeded.
        error: Error message if indexing failed.
    """

    files_indexed: int
    chunks_created: int
    chunks_updated: int
    chunks_deleted: int
    vectors_stored: int
    tree_sha: str
    files_failed: int = 0
    is_incremental: bool = False
    success: bool = True
    error: str | None = None

    @classmethod
    def create_success(
        cls,
        *,
        files_indexed: int,
        chunks_created: int,
        chunks_updated: int,
        chunks_deleted: int,
        vectors_stored: int,
        tree_sha: str,
        is_incremental: bool = False,
        files_failed: int = 0,
    ) -> "IndexResponse":
        """Create a success response with indexing statistics.

        Args:
            files_indexed: Number of files processed.
            chunks_created: Number of chunks created.
            chunks_updated: Number of chunks updated.
            chunks_deleted: Number of chunks deleted.
            vectors_stored: Number of vectors stored.
            tree_sha: Git tree SHA that was indexed.
            is_incremental: Whether this was an incremental sync.
            files_failed: Number of files that failed to chunk.

        Returns:
            IndexResponse with success=True and all statistics.
        """
        return cls(
            files_indexed=files_indexed,
            chunks_created=chunks_created,
            chunks_updated=chunks_updated,
            chunks_deleted=chunks_deleted,
            vectors_stored=vectors_stored,
            tree_sha=tree_sha,
            files_failed=files_failed,
            is_incremental=is_incremental,
            success=True,
            error=None,
        )

    @classmethod
    def create_error(cls, message: str) -> "IndexResponse":
        """Create an error response with zero counts.

        Args:
            message: Error message describing what went wrong.

        Returns:
            IndexResponse with success=False and all counts set to zero.
        """
        return cls(
            files_indexed=0,
            chunks_created=0,
            chunks_updated=0,
            chunks_deleted=0,
            vectors_stored=0,
            tree_sha="",
            files_failed=0,
            is_incremental=False,
            success=False,
            error=message,
        )


@dataclass
class IndexingContext:
    """Context passed between orchestration phases.

    Holds intermediate state during the indexing pipeline, enabling
    each phase to operate independently while sharing necessary data.
    """

    request: IndexRequest
    tree_sha: str = ""
    files_to_index: list[Path] = field(default_factory=list)
    is_incremental: bool = False
    chunks_deleted: int = 0
    stats: dict[str, int] = field(default_factory=dict)
