"""Tests for the unified ensure_synced() helper.

Verifies that ensure_synced() provides:
1. Single code path for sync-before-run across all commands
2. Progress indicator visible when syncing happens
3. Easy-to-use pattern for new commands

See issue #209 for requirements.
"""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch


@dataclass
class MockIndexResponse:
    """Mock IndexResponse for testing ensure_synced."""

    files_indexed: int = 0
    chunks_created: int = 0
    chunks_updated: int = 0
    chunks_deleted: int = 0
    vectors_stored: int = 0
    tree_sha: str = "abc123def456"
    files_failed: int = 0
    is_incremental: bool = True
    success: bool = True
    error: str | None = None


class TestEnsureSynced:
    """Tests for ensure_synced() function."""

    def test_shows_progress_when_syncing_and_show_progress_true(self) -> None:
        """Progress bar is shown when syncing and show_progress=True."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.progress_context") as mock_progress_ctx,
        ):
            # Setup mocks - index is stale
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.return_value = "old_sha"
            mock_usecase.return_value.execute.return_value = MockIndexResponse(files_indexed=5)

            # Setup progress context mock
            mock_progress = MagicMock()
            mock_progress_ctx.return_value.__enter__ = MagicMock(return_value=mock_progress)
            mock_progress_ctx.return_value.__exit__ = MagicMock(return_value=None)

            # Call ensure_synced with show_progress=True
            ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
                show_progress=True,
            )

            # Should use progress context with quiet_mode=False
            mock_progress_ctx.assert_called_once_with(quiet_mode=False)

    def test_no_progress_when_syncing_and_show_progress_false(self) -> None:
        """Progress bar is NOT shown when show_progress=False."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.progress_context") as mock_progress_ctx,
        ):
            # Setup mocks - index is stale
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.return_value = "old_sha"
            mock_usecase.return_value.execute.return_value = MockIndexResponse(files_indexed=5)

            # Setup progress context mock to return None (quiet mode)
            mock_progress_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_progress_ctx.return_value.__exit__ = MagicMock(return_value=None)

            # Call ensure_synced with show_progress=False
            ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
                show_progress=False,
            )

            # Should use progress context with quiet_mode=True
            mock_progress_ctx.assert_called_once_with(quiet_mode=True)

    def test_shows_syncing_message_when_interactive_mode(self) -> None:
        """A brief 'Syncing...' message is shown in interactive_mode even without progress bar."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.progress_context") as mock_progress_ctx,
            patch("ember.entrypoints.cli.click.echo") as mock_echo,
        ):
            # Setup mocks - index is stale
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.return_value = "old_sha"
            mock_usecase.return_value.execute.return_value = MockIndexResponse(files_indexed=3)

            # Setup progress context mock
            mock_progress_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_progress_ctx.return_value.__exit__ = MagicMock(return_value=None)

            # Call ensure_synced with interactive_mode=True
            ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
                show_progress=False,  # No progress bar
                interactive_mode=True,  # But show status message
            )

            # Should show "Syncing..." message to stderr
            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("Syncing" in str(call) for call in calls)

    def test_no_output_when_index_up_to_date(self) -> None:
        """No message is shown when index is already up to date."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.click.echo") as mock_echo,
        ):
            # Setup mocks - index is NOT stale (same SHA)
            mock_git.return_value.get_worktree_tree_sha.return_value = "same_sha"
            mock_meta.return_value.get.return_value = "same_sha"

            # Call ensure_synced
            ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
                show_progress=True,
            )

            # Should NOT create indexing usecase (no sync needed)
            mock_usecase.assert_not_called()
            # Should NOT show any sync messages
            assert not mock_echo.called

    def test_shows_completion_message_after_sync(self) -> None:
        """Shows completion message after sync when show_progress=True."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.progress_context") as mock_progress_ctx,
            patch("ember.entrypoints.cli.click.echo") as mock_echo,
        ):
            # Setup mocks - index is stale
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.return_value = "old_sha"
            mock_usecase.return_value.execute.return_value = MockIndexResponse(files_indexed=5)

            # Setup progress context mock
            mock_progress = MagicMock()
            mock_progress_ctx.return_value.__enter__ = MagicMock(return_value=mock_progress)
            mock_progress_ctx.return_value.__exit__ = MagicMock(return_value=None)

            # Call ensure_synced with show_progress=True
            ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
                show_progress=True,
            )

            # Should show completion message with file count
            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("Synced" in str(call) and "5" in str(call) for call in calls)

    def test_continues_on_error_when_verbose_false(self) -> None:
        """Silently continues if sync check fails and verbose=False."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch("ember.entrypoints.cli.click.echo") as mock_echo,
        ):
            # Setup mock to raise an exception
            mock_git.return_value.get_worktree_tree_sha.side_effect = Exception("Git error")

            # Should NOT raise exception
            ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
                verbose=False,
            )

            # Should not print error message
            warning_calls = [call for call in mock_echo.call_args_list if "Warning" in str(call)]
            assert len(warning_calls) == 0

    def test_shows_warning_on_error_when_verbose_true(self) -> None:
        """Shows warning message if sync check fails and verbose=True."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch("ember.entrypoints.cli.click.echo") as mock_echo,
        ):
            # Setup mock to raise an exception
            mock_git.return_value.get_worktree_tree_sha.side_effect = Exception("Git error")

            # Should NOT raise exception
            ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
                verbose=True,
            )

            # Should print warning message to stderr
            warning_calls = [call for call in mock_echo.call_args_list if "Warning" in str(call)]
            assert len(warning_calls) == 1


class TestEnsureSyncedReturnsStatus:
    """Tests for ensure_synced() return value."""

    def test_returns_synced_true_when_sync_performed(self) -> None:
        """Returns synced=True when sync was actually performed."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.progress_context") as mock_progress_ctx,
        ):
            # Setup mocks - index is stale
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.return_value = "old_sha"
            mock_usecase.return_value.execute.return_value = MockIndexResponse(files_indexed=5)

            mock_progress_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_progress_ctx.return_value.__exit__ = MagicMock(return_value=None)

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is True
            assert result.files_indexed == 5

    def test_returns_synced_false_when_already_up_to_date(self) -> None:
        """Returns synced=False when index was already up to date."""
        from ember.entrypoints.cli import ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
        ):
            # Setup mocks - index is NOT stale
            mock_git.return_value.get_worktree_tree_sha.return_value = "same_sha"
            mock_meta.return_value.get.return_value = "same_sha"

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.files_indexed == 0

    def test_returns_error_on_failure(self) -> None:
        """Returns error when sync fails."""
        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with (
            patch(
                "ember.adapters.git_cmd.git_adapter.GitAdapter"
            ) as mock_git,
        ):
            # Setup mock to raise an exception
            mock_git.return_value.get_worktree_tree_sha.side_effect = Exception("Git error")

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error is not None
            assert "Git error" in result.error
            # Unknown error type for generic Exception
            assert result.error_type == SyncErrorType.UNKNOWN


class TestEnsureSyncedErrorClassification:
    """Tests for error classification in ensure_synced()."""

    def test_classifies_git_runtime_error(self) -> None:
        """RuntimeError with git-related message is classified as GIT_ERROR."""
        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git:
            mock_git.return_value.get_worktree_tree_sha.side_effect = RuntimeError(
                "Not a git repository: /test"
            )

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error_type == SyncErrorType.GIT_ERROR
            assert "git repository" in result.error.lower()

    def test_classifies_subprocess_error_as_git(self) -> None:
        """subprocess.CalledProcessError is classified as GIT_ERROR."""
        import subprocess

        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git:
            mock_git.return_value.get_worktree_tree_sha.side_effect = (
                subprocess.CalledProcessError(1, "git status")
            )

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error_type == SyncErrorType.GIT_ERROR

    def test_classifies_sqlite_error_as_database(self) -> None:
        """sqlite3.Error is classified as DATABASE_ERROR."""
        import sqlite3

        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with (
            patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
        ):
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.side_effect = sqlite3.OperationalError(
                "database is locked"
            )

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error_type == SyncErrorType.DATABASE_ERROR
            assert "locked" in result.error.lower()

    def test_classifies_permission_error(self) -> None:
        """PermissionError is classified as PERMISSION_ERROR."""
        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git:
            mock_git.return_value.get_worktree_tree_sha.side_effect = PermissionError(
                "Access denied"
            )

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error_type == SyncErrorType.PERMISSION_ERROR

    def test_classifies_oserror_eacces_as_permission(self) -> None:
        """OSError with EACCES errno is classified as PERMISSION_ERROR."""
        import errno

        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git:
            error = OSError(errno.EACCES, "Permission denied")
            mock_git.return_value.get_worktree_tree_sha.side_effect = error

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error_type == SyncErrorType.PERMISSION_ERROR

    def test_classifies_unknown_error(self) -> None:
        """Generic exceptions are classified as UNKNOWN."""
        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git:
            mock_git.return_value.get_worktree_tree_sha.side_effect = ValueError(
                "Something went wrong"
            )

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error_type == SyncErrorType.UNKNOWN

    def test_successful_sync_has_no_error_type(self) -> None:
        """Successful sync has error_type=NONE."""
        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with (
            patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.progress_context") as mock_progress_ctx,
        ):
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.return_value = "old_sha"
            mock_usecase.return_value.execute.return_value = MockIndexResponse(
                files_indexed=5
            )
            mock_progress_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_progress_ctx.return_value.__exit__ = MagicMock(return_value=None)

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is True
            assert result.error is None
            assert result.error_type == SyncErrorType.NONE

    def test_already_synced_has_no_error_type(self) -> None:
        """Already synced (no changes) has error_type=NONE."""
        from ember.entrypoints.cli import SyncErrorType, ensure_synced

        with (
            patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
        ):
            mock_git.return_value.get_worktree_tree_sha.return_value = "same_sha"
            mock_meta.return_value.get.return_value = "same_sha"

            result = ensure_synced(
                repo_root=Path("/test"),
                db_path=Path("/test/.ember/index.db"),
                config=MagicMock(),
            )

            assert result.synced is False
            assert result.error is None
            assert result.error_type == SyncErrorType.NONE
