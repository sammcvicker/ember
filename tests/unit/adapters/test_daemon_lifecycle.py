"""Unit tests for daemon lifecycle module."""

import os
import signal
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


class TestStopHelperMethods:
    """Tests for stop() helper methods extracted in #263."""

    @pytest.fixture
    def lifecycle(self, tmp_path: Path) -> DaemonLifecycle:
        """Create a DaemonLifecycle instance for testing."""
        return DaemonLifecycle(
            socket_path=tmp_path / "test.sock",
            pid_file=tmp_path / "test.pid",
            log_file=tmp_path / "test.log",
        )

    def test_reap_zombie_suppresses_child_process_error(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _reap_zombie suppresses ChildProcessError (not our child)."""
        with patch("os.waitpid") as mock_waitpid:
            mock_waitpid.side_effect = ChildProcessError("No child processes")
            # Should not raise
            lifecycle._reap_zombie(12345)
            mock_waitpid.assert_called_once_with(12345, os.WNOHANG)

    def test_reap_zombie_suppresses_os_error(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _reap_zombie suppresses OSError (process doesn't exist)."""
        with patch("os.waitpid") as mock_waitpid:
            mock_waitpid.side_effect = OSError("No such process")
            # Should not raise
            lifecycle._reap_zombie(12345)
            mock_waitpid.assert_called_once_with(12345, os.WNOHANG)

    def test_wait_for_death_returns_true_when_process_dies(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _wait_for_death returns True when process dies."""
        with patch.object(lifecycle, "is_process_alive") as mock_alive:
            # Process dies on second check
            mock_alive.side_effect = [True, False]

            with patch("time.sleep"):
                result = lifecycle._wait_for_death(12345, 2.0)

            assert result is True
            assert mock_alive.call_count == 2

    def test_wait_for_death_returns_false_on_timeout(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _wait_for_death returns False when process survives timeout."""
        with patch.object(lifecycle, "is_process_alive") as mock_alive:
            mock_alive.return_value = True  # Process always alive

            with patch("time.sleep"):
                result = lifecycle._wait_for_death(12345, 1.0)

            assert result is False
            # 1.0s timeout / 0.5s interval = 2 checks
            assert mock_alive.call_count == 2

    def test_send_signal_and_wait_returns_true_when_process_dies(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _send_signal_and_wait returns True on successful termination."""
        with patch("os.kill") as mock_kill:
            mock_kill.return_value = None

            with patch.object(lifecycle, "_wait_for_death") as mock_wait:
                mock_wait.return_value = True

                result = lifecycle._send_signal_and_wait(
                    12345, signal.SIGTERM, 5.0
                )

                assert result is True
                mock_kill.assert_called_once_with(12345, signal.SIGTERM)
                mock_wait.assert_called_once_with(12345, 5.0)

    def test_send_signal_and_wait_returns_false_on_timeout(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _send_signal_and_wait returns False when process survives."""
        with patch("os.kill") as mock_kill:
            mock_kill.return_value = None

            with patch.object(lifecycle, "_wait_for_death") as mock_wait:
                mock_wait.return_value = False

                result = lifecycle._send_signal_and_wait(
                    12345, signal.SIGTERM, 5.0
                )

                assert result is False

    def test_send_signal_and_wait_returns_none_on_signal_failure(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _send_signal_and_wait returns None when signal fails."""
        with patch("os.kill") as mock_kill:
            mock_kill.side_effect = OSError("Permission denied")

            result = lifecycle._send_signal_and_wait(
                12345, signal.SIGTERM, 5.0
            )

            assert result is None

    def test_stop_with_sigterm_returns_true_on_graceful_stop(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _stop_with_sigterm returns True on graceful shutdown."""
        with patch.object(lifecycle, "_send_signal_and_wait") as mock_signal:
            mock_signal.return_value = True

            result = lifecycle._stop_with_sigterm(12345, 10)

            assert result is True
            mock_signal.assert_called_once_with(12345, signal.SIGTERM, 10.0)

    def test_stop_with_sigterm_returns_true_when_already_dead(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _stop_with_sigterm returns True when process already dead."""
        with patch.object(lifecycle, "_send_signal_and_wait") as mock_signal:
            mock_signal.return_value = None  # Signal failed

            with patch.object(lifecycle, "is_process_alive") as mock_alive:
                mock_alive.return_value = False  # Process already dead

                result = lifecycle._stop_with_sigterm(12345, 10)

                assert result is True

    def test_stop_with_sigkill_returns_true_on_successful_kill(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _stop_with_sigkill returns True when SIGKILL works."""
        with patch.object(lifecycle, "_send_signal_and_wait") as mock_signal:
            mock_signal.return_value = True

            result = lifecycle._stop_with_sigkill(12345)

            assert result is True
            mock_signal.assert_called_once_with(12345, signal.SIGKILL, 2.5)

    def test_stop_with_sigkill_returns_false_when_process_survives(
        self, lifecycle: DaemonLifecycle
    ) -> None:
        """Test _stop_with_sigkill returns False when process survives."""
        with patch.object(lifecycle, "_send_signal_and_wait") as mock_signal:
            mock_signal.return_value = False  # Process survived

            result = lifecycle._stop_with_sigkill(12345)

            assert result is False
