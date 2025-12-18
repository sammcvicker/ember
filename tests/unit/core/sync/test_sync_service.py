"""Tests for the sync service module.

Tests the error classification and SyncService functionality.
"""

import errno
import sqlite3
import subprocess
from unittest.mock import MagicMock

from ember.core.sync import SyncService, classify_sync_error
from ember.domain.entities import SyncErrorType


class TestClassifySyncError:
    """Tests for the classify_sync_error function."""

    def test_classifies_permission_error(self) -> None:
        """PermissionError is classified as PERMISSION_ERROR."""
        error = PermissionError("Access denied")
        result = classify_sync_error(error)
        assert result == SyncErrorType.PERMISSION_ERROR

    def test_classifies_oserror_eacces(self) -> None:
        """OSError with EACCES errno is classified as PERMISSION_ERROR."""
        error = OSError(errno.EACCES, "Permission denied")
        result = classify_sync_error(error)
        assert result == SyncErrorType.PERMISSION_ERROR

    def test_classifies_oserror_eperm(self) -> None:
        """OSError with EPERM errno is classified as PERMISSION_ERROR."""
        error = OSError(errno.EPERM, "Operation not permitted")
        result = classify_sync_error(error)
        assert result == SyncErrorType.PERMISSION_ERROR

    def test_classifies_oserror_other_as_unknown(self) -> None:
        """OSError with other errno is classified as UNKNOWN."""
        error = OSError(errno.ENOENT, "No such file")
        result = classify_sync_error(error)
        assert result == SyncErrorType.UNKNOWN

    def test_classifies_sqlite_error(self) -> None:
        """sqlite3.Error is classified as DATABASE_ERROR."""
        error = sqlite3.OperationalError("database is locked")
        result = classify_sync_error(error)
        assert result == SyncErrorType.DATABASE_ERROR

    def test_classifies_sqlite_integrity_error(self) -> None:
        """sqlite3.IntegrityError is classified as DATABASE_ERROR."""
        error = sqlite3.IntegrityError("constraint failed")
        result = classify_sync_error(error)
        assert result == SyncErrorType.DATABASE_ERROR

    def test_classifies_subprocess_error(self) -> None:
        """subprocess.CalledProcessError is classified as GIT_ERROR."""
        error = subprocess.CalledProcessError(1, "git status")
        result = classify_sync_error(error)
        assert result == SyncErrorType.GIT_ERROR

    def test_classifies_runtime_error_with_git_keyword(self) -> None:
        """RuntimeError with 'git' keyword is classified as GIT_ERROR."""
        error = RuntimeError("Not a git repository: /test")
        result = classify_sync_error(error)
        assert result == SyncErrorType.GIT_ERROR

    def test_classifies_runtime_error_with_repository_keyword(self) -> None:
        """RuntimeError with 'repository' keyword is classified as GIT_ERROR."""
        error = RuntimeError("Failed to open repository")
        result = classify_sync_error(error)
        assert result == SyncErrorType.GIT_ERROR

    def test_classifies_runtime_error_with_commit_keyword(self) -> None:
        """RuntimeError with 'commit' keyword is classified as GIT_ERROR."""
        error = RuntimeError("Invalid commit SHA")
        result = classify_sync_error(error)
        assert result == SyncErrorType.GIT_ERROR

    def test_classifies_runtime_error_with_tree_keyword(self) -> None:
        """RuntimeError with 'tree' keyword is classified as GIT_ERROR."""
        error = RuntimeError("Failed to get tree object")
        result = classify_sync_error(error)
        assert result == SyncErrorType.GIT_ERROR

    def test_classifies_runtime_error_with_ref_keyword(self) -> None:
        """RuntimeError with 'ref' keyword is classified as GIT_ERROR."""
        error = RuntimeError("Invalid ref: HEAD")
        result = classify_sync_error(error)
        assert result == SyncErrorType.GIT_ERROR

    def test_classifies_runtime_error_without_git_keyword_as_unknown(self) -> None:
        """RuntimeError without git keywords is classified as UNKNOWN."""
        error = RuntimeError("Something went wrong")
        result = classify_sync_error(error)
        assert result == SyncErrorType.UNKNOWN

    def test_classifies_value_error_as_unknown(self) -> None:
        """ValueError is classified as UNKNOWN."""
        error = ValueError("Invalid value")
        result = classify_sync_error(error)
        assert result == SyncErrorType.UNKNOWN

    def test_classifies_type_error_as_unknown(self) -> None:
        """TypeError is classified as UNKNOWN."""
        error = TypeError("Type mismatch")
        result = classify_sync_error(error)
        assert result == SyncErrorType.UNKNOWN

    def test_classifies_generic_exception_as_unknown(self) -> None:
        """Generic Exception is classified as UNKNOWN."""
        error = Exception("Generic error")
        result = classify_sync_error(error)
        assert result == SyncErrorType.UNKNOWN

    def test_case_insensitive_keyword_matching(self) -> None:
        """Keyword matching is case-insensitive."""
        error = RuntimeError("Not a GIT Repository")
        result = classify_sync_error(error)
        assert result == SyncErrorType.GIT_ERROR


class TestSyncService:
    """Tests for the SyncService class."""

    def test_is_stale_returns_true_when_shas_differ(self) -> None:
        """is_stale() returns True when tree SHAs are different."""
        mock_vcs = MagicMock()
        mock_vcs.get_worktree_tree_sha.return_value = "new_sha"
        mock_meta = MagicMock()
        mock_meta.get.return_value = "old_sha"

        service = SyncService(mock_vcs, mock_meta)
        assert service.is_stale() is True
        mock_meta.get.assert_called_once_with("last_tree_sha")

    def test_is_stale_returns_false_when_shas_match(self) -> None:
        """is_stale() returns False when tree SHAs match."""
        mock_vcs = MagicMock()
        mock_vcs.get_worktree_tree_sha.return_value = "same_sha"
        mock_meta = MagicMock()
        mock_meta.get.return_value = "same_sha"

        service = SyncService(mock_vcs, mock_meta)
        assert service.is_stale() is False

    def test_is_stale_returns_true_when_no_previous_sha(self) -> None:
        """is_stale() returns True when no previous SHA exists."""
        mock_vcs = MagicMock()
        mock_vcs.get_worktree_tree_sha.return_value = "current_sha"
        mock_meta = MagicMock()
        mock_meta.get.return_value = None

        service = SyncService(mock_vcs, mock_meta)
        assert service.is_stale() is True

    def test_check_staleness_returns_result_without_error_when_up_to_date(self) -> None:
        """check_staleness() returns SyncResult without error when index is up to date."""
        mock_vcs = MagicMock()
        mock_vcs.get_worktree_tree_sha.return_value = "same_sha"
        mock_meta = MagicMock()
        mock_meta.get.return_value = "same_sha"

        service = SyncService(mock_vcs, mock_meta)
        result = service.check_staleness()

        assert result.synced is False
        assert result.files_indexed == 0
        assert result.error is None
        assert result.error_type == SyncErrorType.NONE

    def test_check_staleness_returns_error_on_vcs_failure(self) -> None:
        """check_staleness() returns error result on VCS failure."""
        mock_vcs = MagicMock()
        mock_vcs.get_worktree_tree_sha.side_effect = RuntimeError("Not a git repository")
        mock_meta = MagicMock()

        service = SyncService(mock_vcs, mock_meta)
        result = service.check_staleness()

        assert result.synced is False
        assert result.error is not None
        assert "git repository" in result.error.lower()
        assert result.error_type == SyncErrorType.GIT_ERROR

    def test_check_staleness_returns_error_on_db_failure(self) -> None:
        """check_staleness() returns error result on database failure."""
        mock_vcs = MagicMock()
        mock_vcs.get_worktree_tree_sha.return_value = "new_sha"
        mock_meta = MagicMock()
        mock_meta.get.side_effect = sqlite3.OperationalError("database is locked")

        service = SyncService(mock_vcs, mock_meta)
        result = service.check_staleness()

        assert result.synced is False
        assert result.error is not None
        assert "locked" in result.error.lower()
        assert result.error_type == SyncErrorType.DATABASE_ERROR
