"""Unit tests for daemon lifecycle module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ember.adapters.daemon.lifecycle import DaemonLifecycle


class TestTokenizersParallelismEnvVar:
    """Tests for TOKENIZERS_PARALLELISM environment variable fix (#215)."""

    @pytest.fixture
    def lifecycle(self, tmp_path: Path) -> DaemonLifecycle:
        """Create a DaemonLifecycle instance for testing."""
        return DaemonLifecycle(
            socket_path=tmp_path / "test.sock",
            pid_file=tmp_path / "test.pid",
            log_file=tmp_path / "test.log",
        )

    def test_spawn_sets_tokenizers_parallelism_false(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _spawn_background_process sets TOKENIZERS_PARALLELISM=false."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            lifecycle._spawn_background_process(["python", "-c", "pass"])

            # Verify Popen was called with env parameter
            call_kwargs = mock_popen.call_args[1]
            assert "env" in call_kwargs
            assert call_kwargs["env"]["TOKENIZERS_PARALLELISM"] == "false"

    def test_spawn_preserves_existing_env_vars(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _spawn_background_process preserves existing environment."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            # Set up a test environment variable
            original_path = os.environ.get("PATH", "")
            lifecycle._spawn_background_process(["python", "-c", "pass"])

            # Verify PATH is preserved
            call_kwargs = mock_popen.call_args[1]
            assert call_kwargs["env"]["PATH"] == original_path

    def test_spawn_does_not_override_user_tokenizers_parallelism(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test user's TOKENIZERS_PARALLELISM is not overridden."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            # User has explicitly set TOKENIZERS_PARALLELISM=true
            with patch.dict(os.environ, {"TOKENIZERS_PARALLELISM": "true"}):
                lifecycle._spawn_background_process(["python", "-c", "pass"])

                # Verify user's setting is preserved (setdefault doesn't override)
                call_kwargs = mock_popen.call_args[1]
                assert call_kwargs["env"]["TOKENIZERS_PARALLELISM"] == "true"


class TestDaemonLifecycleInit:
    """Tests for DaemonLifecycle initialization."""

    def test_default_paths_use_home_ember_dir(self) -> None:
        """Test default paths are under ~/.ember/."""
        lifecycle = DaemonLifecycle()

        ember_dir = Path.home() / ".ember"
        assert lifecycle.socket_path == ember_dir / "daemon.sock"
        assert lifecycle.pid_file == ember_dir / "daemon.pid"
        assert lifecycle.log_file == ember_dir / "daemon.log"

    def test_custom_paths_are_used(self, tmp_path: Path) -> None:
        """Test custom paths override defaults."""
        custom_socket = tmp_path / "custom.sock"
        custom_pid = tmp_path / "custom.pid"
        custom_log = tmp_path / "custom.log"

        lifecycle = DaemonLifecycle(
            socket_path=custom_socket,
            pid_file=custom_pid,
            log_file=custom_log,
        )

        assert lifecycle.socket_path == custom_socket
        assert lifecycle.pid_file == custom_pid
        assert lifecycle.log_file == custom_log
