"""Tests for targeted sync error hints (Issue #400).

Verifies that sync command errors provide specific, actionable hints
based on the type of error encountered, rather than generic hints.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ember.core.errors import EmberCliError
from ember.core.indexing.types import ModelMismatchError
from ember.entrypoints.cli import handle_cli_errors


class TestHandleCliErrorsDecorator:
    """Tests for the handle_cli_errors decorator error handling."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_click_context(self):
        """Create a mock click context for tests."""
        mock_ctx = MagicMock()
        mock_ctx.obj = {"verbose": False}
        return mock_ctx

    def test_model_mismatch_error_provides_init_force_hint(self) -> None:
        """ModelMismatchError should suggest 'ember init --force'."""

        @handle_cli_errors("test")
        def cmd():
            raise ModelMismatchError(
                stored_model="jina-code-v2:768",
                current_model="minilm:384",
            )

        with pytest.raises(EmberCliError) as exc_info:
            cmd()

        error = exc_info.value
        # Should mention model changed
        assert "jina-code-v2:768" in str(error.message)
        assert "minilm:384" in str(error.message)
        # Hint should explain the model mismatch
        assert error.hint is not None
        assert "config differs" in error.hint.lower() or "model" in error.hint.lower()

    def test_permission_error_provides_permission_hint(
        self, mock_click_context
    ) -> None:
        """PermissionError should suggest checking file permissions."""

        @handle_cli_errors("test")
        def cmd():
            error = PermissionError("Permission denied")
            error.filename = "/path/to/protected/file.db"
            raise error

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert "permission" in error.message.lower()
        assert error.hint is not None
        # Should suggest checking permissions
        assert "permission" in error.hint.lower() or "ls -l" in error.hint.lower()

    def test_permission_error_without_filename_provides_generic_permission_hint(
        self, mock_click_context
    ) -> None:
        """PermissionError without filename should suggest checking .ember/ permissions."""

        @handle_cli_errors("test")
        def cmd():
            raise PermissionError("Permission denied")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert "permission" in error.message.lower()
        assert error.hint is not None
        assert ".ember" in error.hint.lower() or "permission" in error.hint.lower()

    def test_disk_full_error_provides_cleanup_hint(self, mock_click_context) -> None:
        """OSError with 'No space left' should suggest freeing disk space."""

        @handle_cli_errors("test")
        def cmd():
            raise OSError("No space left on device")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        # Should mention disk space issue
        assert (
            "disk" in error.message.lower()
            or "space" in error.message.lower()
            or "no space left" in error.message.lower()
        )
        assert error.hint is not None
        # Should suggest freeing space
        assert "free" in error.hint.lower() or "space" in error.hint.lower()

    def test_generic_oserror_provides_verbose_hint(self, mock_click_context) -> None:
        """Generic OSError should suggest verbose mode."""

        @handle_cli_errors("test")
        def cmd():
            raise OSError("Some other OS error occurred")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert error.hint is not None
        # Should suggest verbose mode
        assert "verbose" in error.hint.lower()

    def test_runtime_error_provides_verbose_hint(self) -> None:
        """RuntimeError should suggest running with --verbose."""

        @handle_cli_errors("test")
        def cmd():
            raise RuntimeError("Something went wrong")

        with pytest.raises(EmberCliError) as exc_info:
            cmd()

        error = exc_info.value
        assert error.hint is not None
        assert "verbose" in error.hint.lower()

    def test_generic_exception_provides_verbose_hint(self, mock_click_context) -> None:
        """Generic Exception should suggest running with --verbose."""

        @handle_cli_errors("test")
        def cmd():
            raise ValueError("Unexpected value")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert "test" in error.message  # Command name in message
        assert error.hint is not None
        assert "verbose" in error.hint.lower()


class TestGetTargetedSyncHint:
    """Tests for _get_targeted_sync_hint function."""

    @pytest.mark.parametrize(
        "error_message, expected_keyword",
        [
            pytest.param(
                "database disk image is malformed",
                "reindex",
                id="db-corruption",
            ),
            pytest.param(
                "file is not a database",
                "reindex",
                id="not-a-database",
            ),
            pytest.param(
                "Embedding model changed",
                "init",
                id="model-mismatch",
            ),
            pytest.param(
                "Vector dimension mismatch: expected 768, got 384",
                "init|reindex",
                id="dimension-mismatch",
            ),
            pytest.param(
                "Permission denied: /path/to/file",
                "permission",
                id="permission-denied",
            ),
            pytest.param(
                "Access denied to file.db",
                "permission",
                id="access-denied",
            ),
            pytest.param(
                "No space left on device",
                "space|disk",
                id="disk-full",
            ),
            pytest.param(
                "database is locked",
                "wait|retry",
                id="db-locked",
            ),
            pytest.param(
                "database table is busy",
                "wait|retry",
                id="db-busy",
            ),
            pytest.param(
                "Some unknown error occurred",
                "verbose",
                id="generic-error",
            ),
        ],
    )
    def test_get_targeted_sync_hint(self, error_message, expected_keyword) -> None:
        """Test that error messages produce hints containing expected keywords."""
        from ember.entrypoints.cli import _get_targeted_sync_hint

        hint = _get_targeted_sync_hint(error_message)
        hint_lower = hint.lower()

        # expected_keyword can be "keyword1|keyword2" meaning either must match
        keywords = expected_keyword.split("|")
        assert any(
            kw in hint_lower for kw in keywords
        ), f"Expected one of {keywords} in hint: {hint!r}"


class TestSyncCommandErrorIntegration:
    """Integration tests for sync command error scenarios."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a Click CLI test runner."""
        return CliRunner()

    @patch("ember.entrypoints.cli.get_ember_repo_root")
    @patch("ember.entrypoints.cli._quick_check_unchanged")
    @patch("ember.entrypoints.cli._load_config")
    @patch("ember.entrypoints.cli._create_indexing_usecase")
    def test_sync_model_mismatch_shows_targeted_hint(
        self,
        mock_create_usecase: MagicMock,
        mock_load_config: MagicMock,
        mock_quick_check: MagicMock,
        mock_get_root: MagicMock,
        runner: CliRunner,
        tmp_path,
    ) -> None:
        """Sync command should show targeted hint for model mismatch."""
        from ember.entrypoints.cli import sync

        mock_get_root.return_value = (tmp_path, tmp_path / ".ember")
        mock_quick_check.return_value = False
        mock_load_config.return_value = MagicMock()

        # Simulate model mismatch by raising the exception
        mock_usecase = MagicMock()
        mock_usecase.execute.side_effect = ModelMismatchError(
            stored_model="old-model:768",
            current_model="new-model:384",
        )
        mock_create_usecase.return_value = mock_usecase

        result = runner.invoke(sync, [], obj={"quiet": False})

        # Should fail with specific hint about model
        assert result.exit_code != 0
        assert "old-model:768" in result.output or "model" in result.output.lower()

    @patch("ember.entrypoints.cli.get_ember_repo_root")
    @patch("ember.entrypoints.cli._quick_check_unchanged")
    @patch("ember.entrypoints.cli._load_config")
    @patch("ember.entrypoints.cli._create_indexing_usecase")
    def test_sync_permission_error_shows_targeted_hint(
        self,
        mock_create_usecase: MagicMock,
        mock_load_config: MagicMock,
        mock_quick_check: MagicMock,
        mock_get_root: MagicMock,
        runner: CliRunner,
        tmp_path,
    ) -> None:
        """Sync command should show targeted hint for permission errors."""
        from ember.entrypoints.cli import sync

        mock_get_root.return_value = (tmp_path, tmp_path / ".ember")
        mock_quick_check.return_value = False
        mock_load_config.return_value = MagicMock()

        # Simulate permission error
        mock_usecase = MagicMock()
        perm_error = PermissionError("Permission denied")
        perm_error.filename = str(tmp_path / "index.db")
        mock_usecase.execute.side_effect = perm_error
        mock_create_usecase.return_value = mock_usecase

        result = runner.invoke(sync, [], obj={"quiet": False})

        # Should fail with permission-related hint
        assert result.exit_code != 0
        assert "permission" in result.output.lower()

    @patch("ember.entrypoints.cli.get_ember_repo_root")
    @patch("ember.entrypoints.cli._quick_check_unchanged")
    @patch("ember.entrypoints.cli._load_config")
    @patch("ember.entrypoints.cli._create_indexing_usecase")
    def test_sync_disk_full_shows_targeted_hint(
        self,
        mock_create_usecase: MagicMock,
        mock_load_config: MagicMock,
        mock_quick_check: MagicMock,
        mock_get_root: MagicMock,
        runner: CliRunner,
        tmp_path,
    ) -> None:
        """Sync command should show targeted hint for disk full errors."""
        from ember.entrypoints.cli import sync

        mock_get_root.return_value = (tmp_path, tmp_path / ".ember")
        mock_quick_check.return_value = False
        mock_load_config.return_value = MagicMock()

        # Simulate disk full error
        mock_usecase = MagicMock()
        mock_usecase.execute.side_effect = OSError("No space left on device")
        mock_create_usecase.return_value = mock_usecase

        result = runner.invoke(sync, [], obj={"quiet": False})

        # Should fail with disk space hint
        assert result.exit_code != 0
        assert "disk" in result.output.lower() or "space" in result.output.lower()

    @patch("ember.entrypoints.cli.get_ember_repo_root")
    @patch("ember.entrypoints.cli._quick_check_unchanged")
    @patch("ember.entrypoints.cli._load_config")
    @patch("ember.entrypoints.cli._create_indexing_usecase")
    def test_sync_response_error_shows_targeted_hint(
        self,
        mock_create_usecase: MagicMock,
        mock_load_config: MagicMock,
        mock_quick_check: MagicMock,
        mock_get_root: MagicMock,
        runner: CliRunner,
        tmp_path,
    ) -> None:
        """Sync command should show targeted hint based on error message in response."""
        from ember.core.indexing.types import IndexResponse
        from ember.entrypoints.cli import sync

        mock_get_root.return_value = (tmp_path, tmp_path / ".ember")
        mock_quick_check.return_value = False
        mock_load_config.return_value = MagicMock()

        # Simulate error in response (not exception)
        mock_usecase = MagicMock()
        mock_usecase.execute.return_value = IndexResponse.create_error(
            "database disk image is malformed"
        )
        mock_create_usecase.return_value = mock_usecase

        result = runner.invoke(sync, [], obj={"quiet": False})

        # Should fail with reindex hint for database corruption
        assert result.exit_code != 0
        assert "reindex" in result.output.lower()


class TestSqlite3ErrorHandling:
    """Tests for sqlite3.Error handling in handle_cli_errors decorator."""

    @pytest.fixture
    def mock_click_context(self):
        """Create a mock click context for tests."""
        mock_ctx = MagicMock()
        mock_ctx.obj = {"verbose": False}
        return mock_ctx

    def test_sqlite_operational_error_provides_database_hint(
        self, mock_click_context
    ) -> None:
        """sqlite3.OperationalError should provide database-specific hint."""
        import sqlite3

        @handle_cli_errors("test")
        def cmd():
            raise sqlite3.OperationalError("database is locked")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert "database" in error.message.lower()
        assert error.hint is not None
        # Should suggest reindex as the recovery action
        assert "reindex" in error.hint.lower() or "sync" in error.hint.lower()

    def test_sqlite_integrity_error_provides_database_hint(
        self, mock_click_context
    ) -> None:
        """sqlite3.IntegrityError should provide database-specific hint."""
        import sqlite3

        @handle_cli_errors("test")
        def cmd():
            raise sqlite3.IntegrityError("constraint failed")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert "database" in error.message.lower()
        assert error.hint is not None
        assert "reindex" in error.hint.lower() or "sync" in error.hint.lower()

    def test_sqlite_database_error_provides_database_hint(
        self, mock_click_context
    ) -> None:
        """sqlite3.DatabaseError should provide database-specific hint."""
        import sqlite3

        @handle_cli_errors("test")
        def cmd():
            raise sqlite3.DatabaseError("database disk image is malformed")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert "database" in error.message.lower()
        assert error.hint is not None
        assert "reindex" in error.hint.lower() or "sync" in error.hint.lower()


class TestNetworkErrorHandling:
    """Tests for network/timeout errors in handle_cli_errors decorator."""

    @pytest.fixture
    def mock_click_context(self):
        """Create a mock click context for tests."""
        mock_ctx = MagicMock()
        mock_ctx.obj = {"verbose": False}
        return mock_ctx

    def test_connection_error_provides_network_hint(
        self, mock_click_context
    ) -> None:
        """requests.exceptions.ConnectionError should provide network hint."""
        import requests.exceptions

        @handle_cli_errors("test")
        def cmd():
            raise requests.exceptions.ConnectionError("Failed to connect")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert error.hint is not None
        # Should suggest checking network connection
        assert "network" in error.hint.lower() or "connection" in error.hint.lower() or "internet" in error.hint.lower()

    def test_timeout_error_provides_network_hint(
        self, mock_click_context
    ) -> None:
        """requests.exceptions.Timeout should provide timeout hint."""
        import requests.exceptions

        @handle_cli_errors("test")
        def cmd():
            raise requests.exceptions.Timeout("Connection timed out")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert error.hint is not None
        # Should suggest retry or check connection
        assert "timeout" in error.hint.lower() or "retry" in error.hint.lower() or "network" in error.hint.lower()

    def test_urlerror_provides_network_hint(
        self, mock_click_context
    ) -> None:
        """urllib.error.URLError should provide network hint."""
        from urllib.error import URLError

        @handle_cli_errors("test")
        def cmd():
            raise URLError("Name or service not known")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert error.hint is not None
        # Should suggest checking network connection
        assert "network" in error.hint.lower() or "connection" in error.hint.lower() or "internet" in error.hint.lower()

    def test_builtin_timeout_error_provides_timeout_hint(
        self, mock_click_context
    ) -> None:
        """Built-in TimeoutError should provide timeout hint."""

        @handle_cli_errors("test")
        def cmd():
            raise TimeoutError("Operation timed out")

        with (
            patch("click.get_current_context", return_value=mock_click_context),
            pytest.raises(EmberCliError) as exc_info,
        ):
            cmd()

        error = exc_info.value
        assert error.hint is not None
        # Should suggest retry or check system resources
        assert "timed out" in error.hint.lower() or "try again" in error.hint.lower()


class TestLoadAndDisplayConfigErrorHandling:
    """Tests for _load_and_display_config error handling improvements."""

    def test_load_and_display_config_returns_true_on_success(self) -> None:
        """_load_and_display_config returns True when config loads successfully."""
        from ember.entrypoints.cli import _load_and_display_config

        mock_config = MagicMock()
        result = _load_and_display_config("Test Config", lambda: mock_config)
        assert result is True

    def test_load_and_display_config_returns_false_on_failure(self) -> None:
        """_load_and_display_config returns False when config loading fails."""
        from ember.entrypoints.cli import _load_and_display_config

        def failing_loader():
            raise ValueError("Config parse error")

        result = _load_and_display_config("Test Config", failing_loader)
        assert result is False


class TestQuickCheckUnchangedErrorHandling:
    """Tests for _quick_check_unchanged error handling."""

    def test_quick_check_returns_false_on_exception(self, tmp_path) -> None:
        """_quick_check_unchanged returns False (triggering full sync) on any error."""
        from ember.entrypoints.cli import _quick_check_unchanged

        # Non-existent paths will cause errors
        result = _quick_check_unchanged(
            repo_root=tmp_path / "nonexistent",
            db_path=tmp_path / "nonexistent.db",
            sync_mode="worktree",
            reindex=False,
        )
        # Should return False (indicating need for full sync), not raise
        assert result is False
