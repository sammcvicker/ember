"""Sync service for coordinating index synchronization.

This module contains the core sync orchestration logic, extracted from the CLI
to improve testability and maintain clean architecture separation.

The CLI layer should use SyncService to handle sync operations, keeping only
UI concerns (progress display, messages) in the entrypoint layer.
"""

import errno
import sqlite3
import subprocess

from ember.domain.entities import SyncErrorType, SyncResult
from ember.ports.repositories import MetaRepository
from ember.ports.vcs import VCS


def classify_sync_error(exception: Exception) -> SyncErrorType:
    """Classify an exception into a SyncErrorType.

    This function determines the appropriate error category for a given exception,
    allowing callers to handle different failure modes appropriately.

    Args:
        exception: The exception to classify.

    Returns:
        SyncErrorType indicating the category of error.
    """
    # Check for permission errors first
    if isinstance(exception, PermissionError):
        return SyncErrorType.PERMISSION_ERROR

    # Check for OSError with permission-related errno
    if isinstance(exception, OSError):
        if exception.errno in (errno.EACCES, errno.EPERM):
            return SyncErrorType.PERMISSION_ERROR
        return SyncErrorType.UNKNOWN

    # Check for database errors
    if isinstance(exception, sqlite3.Error):
        return SyncErrorType.DATABASE_ERROR

    # Check for git/subprocess errors
    if isinstance(exception, subprocess.CalledProcessError):
        return SyncErrorType.GIT_ERROR

    # Check RuntimeError messages for git-related errors
    if isinstance(exception, RuntimeError):
        error_msg = str(exception).lower()
        git_keywords = ("git", "repository", "ref", "commit", "tree")
        if any(keyword in error_msg for keyword in git_keywords):
            return SyncErrorType.GIT_ERROR

    return SyncErrorType.UNKNOWN


class SyncService:
    """Service for coordinating index synchronization.

    Handles staleness detection and sync orchestration, separating business logic
    from CLI concerns like progress display and user messages.

    This service is designed to be used by the CLI layer, which handles:
    - Progress bar display
    - User-facing messages
    - Dependency creation (IndexingUseCase, etc.)

    The SyncService handles:
    - Checking if the index is stale
    - Executing sync operations
    - Classifying errors appropriately
    """

    def __init__(self, vcs: VCS, meta_repo: MetaRepository) -> None:
        """Initialize the sync service.

        Args:
            vcs: Version control system adapter for git operations.
            meta_repo: Metadata repository for storing sync state.
        """
        self._vcs = vcs
        self._meta_repo = meta_repo

    def is_stale(self) -> bool:
        """Check if the index is stale and needs syncing.

        Compares the current worktree tree SHA with the last indexed tree SHA.

        Returns:
            True if the index needs syncing, False if it's up to date.

        Raises:
            RuntimeError: If git operations fail.
            sqlite3.Error: If database operations fail.
        """
        current_tree_sha = self._vcs.get_worktree_tree_sha()
        last_tree_sha = self._meta_repo.get("last_tree_sha")
        return last_tree_sha != current_tree_sha

    def check_staleness(self) -> SyncResult:
        """Check if sync is needed without performing it.

        Returns:
            SyncResult with synced=False if up to date,
            or error information if check failed.
        """
        try:
            is_stale = self.is_stale()
            if not is_stale:
                return SyncResult(synced=False, files_indexed=0)
            # Index is stale - return a result indicating sync is needed
            # The caller should then execute the sync
            return SyncResult(synced=False, files_indexed=0)
        except Exception as e:
            error_type = classify_sync_error(e)
            return SyncResult(
                synced=False,
                files_indexed=0,
                error=str(e),
                error_type=error_type,
            )
