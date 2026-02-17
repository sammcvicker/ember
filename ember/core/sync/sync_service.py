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

    # Check for timeout and connection errors BEFORE generic OSError
    # (TimeoutError and ConnectionError are subclasses of OSError in Python 3)
    # These typically occur from network operations during sync
    if isinstance(exception, (TimeoutError, ConnectionError)):
        return SyncErrorType.GIT_ERROR

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


def get_targeted_sync_hint(error_message: str) -> str:
    """Get a targeted hint based on the sync error message.

    Analyzes the error message to provide specific, actionable guidance
    rather than generic hints.

    Args:
        error_message: The error message from the failed sync operation.

    Returns:
        An actionable hint string specific to the error type.
    """
    error_lower = error_message.lower()

    # Database corruption - suggest reindex
    if any(
        term in error_lower
        for term in ["malformed", "corrupt", "database disk image", "not a database"]
    ):
        return "Run 'ember sync --reindex' to rebuild the index"

    # Model mismatch or dimension mismatch - suggest init --force
    if "model" in error_lower and ("changed" in error_lower or "mismatch" in error_lower):
        return "Run 'ember init --force' to reinitialize with the new model"

    # Vector dimension mismatch (model changed but message doesn't say "model")
    if "dimension" in error_lower and "mismatch" in error_lower:
        return "Run 'ember init --force' to reinitialize with the new model"

    # Permission issues
    if "permission" in error_lower or "access denied" in error_lower:
        return "Check file permissions in .ember/ directory"

    # Disk space issues
    if "no space left" in error_lower or "disk full" in error_lower:
        return "Free up disk space and retry"

    # Lock/busy database
    if "locked" in error_lower or "busy" in error_lower:
        return "Another process may be using the database. Wait and retry."

    # Generic fallback - suggest verbose mode
    return "Run 'ember sync --verbose' for more details"


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

    def quick_check_unchanged(self, sync_mode: str, force_reindex: bool) -> bool:
        """Quick check if index is up-to-date without expensive setup.

        This method allows the CLI to skip expensive model initialization
        when the index is already up to date.

        Args:
            sync_mode: Sync mode (worktree, staged, or revision SHA).
            force_reindex: Whether force reindex is requested.

        Returns:
            True if index is unchanged and sync can be skipped, False otherwise.
        """
        # Quick check only applies to worktree mode without force reindex
        if force_reindex or sync_mode != "worktree":
            return False

        return not self.is_stale()

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
