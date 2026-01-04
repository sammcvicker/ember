"""Unit tests for FileDetectionService.

Tests for git-based change detection to identify files needing indexing.
"""

from unittest.mock import Mock

import pytest

from ember.core.indexing.file_detection import FileDetectionService


@pytest.fixture
def mock_vcs() -> Mock:
    """Create a mock VCS adapter."""
    return Mock()


@pytest.fixture
def mock_meta_repo() -> Mock:
    """Create a mock MetaRepository."""
    return Mock()


@pytest.fixture
def file_detection(mock_vcs: Mock, mock_meta_repo: Mock) -> FileDetectionService:
    """Create FileDetectionService with mock dependencies."""
    return FileDetectionService(mock_vcs, mock_meta_repo)


class TestGetTreeSha:
    """Tests for get_tree_sha method."""

    def test_worktree_mode_returns_worktree_sha(
        self, file_detection: FileDetectionService, mock_vcs: Mock
    ) -> None:
        """Worktree mode returns worktree tree SHA."""
        mock_vcs.get_worktree_tree_sha.return_value = "worktree_sha_123"

        result = file_detection.get_tree_sha("worktree")

        assert result == "worktree_sha_123"
        mock_vcs.get_worktree_tree_sha.assert_called_once()

    def test_staged_mode_returns_worktree_sha(
        self, file_detection: FileDetectionService, mock_vcs: Mock
    ) -> None:
        """Staged mode currently returns worktree tree SHA (staged support pending)."""
        mock_vcs.get_worktree_tree_sha.return_value = "worktree_sha_123"

        result = file_detection.get_tree_sha("staged")

        assert result == "worktree_sha_123"
        mock_vcs.get_worktree_tree_sha.assert_called_once()

    def test_commit_sha_mode_returns_tree_sha(
        self, file_detection: FileDetectionService, mock_vcs: Mock
    ) -> None:
        """Commit SHA mode returns the tree SHA for that commit."""
        commit_sha = "abc123def456"
        mock_vcs.get_tree_sha.return_value = "tree_sha_for_commit"

        result = file_detection.get_tree_sha(commit_sha)

        assert result == "tree_sha_for_commit"
        mock_vcs.get_tree_sha.assert_called_once_with(ref=commit_sha)


class TestDetermineFilesToSync:
    """Tests for determine_files_to_sync method."""

    def test_force_reindex_returns_all_files(
        self, file_detection: FileDetectionService, mock_vcs: Mock
    ) -> None:
        """Force reindex returns all tracked files."""
        mock_vcs.list_tracked_files.return_value = ["file1.py", "file2.py"]

        result = file_detection.determine_files_to_sync(
            tree_sha="abc123", force_reindex=True
        )

        assert result == (["file1.py", "file2.py"], False)
        mock_vcs.list_tracked_files.assert_called_once()

    def test_no_previous_index_returns_all_files(
        self,
        file_detection: FileDetectionService,
        mock_vcs: Mock,
        mock_meta_repo: Mock,
    ) -> None:
        """First index (no last_tree_sha) returns all tracked files."""
        mock_meta_repo.get.return_value = None
        mock_vcs.list_tracked_files.return_value = ["file1.py", "file2.py"]

        result = file_detection.determine_files_to_sync(
            tree_sha="abc123", force_reindex=False
        )

        assert result == (["file1.py", "file2.py"], False)
        mock_meta_repo.get.assert_called_once_with("last_tree_sha")

    def test_same_tree_sha_returns_none(
        self,
        file_detection: FileDetectionService,
        mock_meta_repo: Mock,
    ) -> None:
        """Same tree SHA as last sync returns None (no changes)."""
        mock_meta_repo.get.return_value = "abc123"

        result = file_detection.determine_files_to_sync(
            tree_sha="abc123", force_reindex=False
        )

        assert result is None

    def test_incremental_returns_added_modified_renamed(
        self,
        file_detection: FileDetectionService,
        mock_vcs: Mock,
        mock_meta_repo: Mock,
    ) -> None:
        """Incremental sync returns added, modified, and renamed files."""
        mock_meta_repo.get.return_value = "old_sha"
        mock_vcs.diff_files.return_value = [
            ("added", "new_file.py"),
            ("modified", "changed.py"),
            ("renamed", "renamed.py"),
            ("deleted", "removed.py"),
        ]

        result = file_detection.determine_files_to_sync(
            tree_sha="new_sha", force_reindex=False
        )

        assert result == (["new_file.py", "changed.py", "renamed.py"], True)
        mock_vcs.diff_files.assert_called_once_with(from_sha="old_sha", to_sha="new_sha")


class TestGetDeletedFiles:
    """Tests for get_deleted_files method."""

    def test_no_previous_index_returns_empty(
        self,
        file_detection: FileDetectionService,
        mock_meta_repo: Mock,
    ) -> None:
        """No previous index returns empty list."""
        mock_meta_repo.get.return_value = None

        result = file_detection.get_deleted_files(tree_sha="abc123")

        assert result == []

    def test_returns_deleted_files_only(
        self,
        file_detection: FileDetectionService,
        mock_vcs: Mock,
        mock_meta_repo: Mock,
    ) -> None:
        """Returns only deleted files from diff."""
        mock_meta_repo.get.return_value = "old_sha"
        mock_vcs.diff_files.return_value = [
            ("added", "new.py"),
            ("deleted", "removed1.py"),
            ("modified", "changed.py"),
            ("deleted", "removed2.py"),
        ]

        result = file_detection.get_deleted_files(tree_sha="new_sha")

        assert result == ["removed1.py", "removed2.py"]


class TestGetLastTreeSha:
    """Tests for get_last_tree_sha method."""

    def test_returns_stored_sha(
        self,
        file_detection: FileDetectionService,
        mock_meta_repo: Mock,
    ) -> None:
        """Returns the stored last tree SHA."""
        mock_meta_repo.get.return_value = "stored_sha_123"

        result = file_detection.get_last_tree_sha()

        assert result == "stored_sha_123"
        mock_meta_repo.get.assert_called_once_with("last_tree_sha")

    def test_returns_none_if_not_stored(
        self,
        file_detection: FileDetectionService,
        mock_meta_repo: Mock,
    ) -> None:
        """Returns None if no last tree SHA is stored."""
        mock_meta_repo.get.return_value = None

        result = file_detection.get_last_tree_sha()

        assert result is None
