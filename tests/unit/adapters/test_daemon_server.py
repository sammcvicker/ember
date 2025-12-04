"""Unit tests for daemon server module."""

import socket
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ember.adapters.daemon.server import DaemonServer


class TestSocketTimeoutHandling:
    """Tests for socket timeout exception handling.

    Issue #183: Tests that socket timeout exceptions are properly caught and that
    the server continues operating, checking idle timeout between accept calls.
    """

    @pytest.fixture
    def temp_socket_path(self, tmp_path: Path) -> Path:
        """Temporary socket path for testing."""
        return tmp_path / "test.sock"

    @pytest.fixture
    def server(self, temp_socket_path: Path) -> DaemonServer:
        """Create a DaemonServer instance for testing."""
        return DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=0,  # Disable idle timeout for most tests
        )

    def test_serve_forever_catches_timeout_error(
        self, server: DaemonServer, temp_socket_path: Path
    ) -> None:
        """Test serve_forever catches TimeoutError (Python 3.10+)."""
        # Create mock socket that raises TimeoutError
        mock_socket = MagicMock(spec=socket.socket)
        call_count = 0

        def accept_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("timed out")
            # Second call: stop the server
            server.running = False
            raise TimeoutError("timed out")

        mock_socket.accept.side_effect = accept_side_effect
        server.server_socket = mock_socket

        # Run serve_forever - should not raise
        server.serve_forever()

        # Verify accept was called multiple times (timeout was handled)
        assert call_count >= 1

    def test_serve_forever_handles_multiple_timeouts(
        self, server: DaemonServer, temp_socket_path: Path
    ) -> None:
        """Test serve_forever handles multiple consecutive timeouts."""
        mock_socket = MagicMock(spec=socket.socket)
        call_count = 0

        def accept_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timed out")
            # After a few timeouts, stop the server
            server.running = False
            raise TimeoutError("timed out")

        mock_socket.accept.side_effect = accept_side_effect
        server.server_socket = mock_socket

        # Run serve_forever - should handle multiple timeouts without issue
        server.serve_forever()

        # Verify multiple timeouts were handled
        assert call_count >= 3

    def test_serve_forever_checks_idle_timeout_on_socket_timeout(
        self, temp_socket_path: Path
    ) -> None:
        """Test that idle timeout is checked when socket times out."""
        server = DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=1,  # 1 second timeout
        )

        # Set last_request_time to trigger idle timeout
        server.last_request_time = time.time() - 2  # 2 seconds ago

        mock_socket = MagicMock(spec=socket.socket)
        accept_count = 0

        def accept_side_effect():
            nonlocal accept_count
            accept_count += 1
            raise TimeoutError("timed out")

        mock_socket.accept.side_effect = accept_side_effect
        server.server_socket = mock_socket

        # Run serve_forever - should exit due to idle timeout after first socket timeout
        server.serve_forever()

        # Verify that the loop exited after checking idle timeout
        # (accept was called at least once before idle timeout triggered exit)
        assert accept_count >= 1


class TestErrorBackoff:
    """Tests for error backoff in server loop."""

    @pytest.fixture
    def temp_socket_path(self, tmp_path: Path) -> Path:
        """Temporary socket path for testing."""
        return tmp_path / "test.sock"

    @pytest.fixture
    def server(self, temp_socket_path: Path) -> DaemonServer:
        """Create a DaemonServer instance for testing."""
        return DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=0,
        )

    def test_serve_forever_continues_on_general_exception(
        self, server: DaemonServer
    ) -> None:
        """Test serve_forever continues running after general exceptions."""
        mock_socket = MagicMock(spec=socket.socket)
        call_count = 0

        def accept_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Some error")
            # Second call: stop the server
            server.running = False
            raise RuntimeError("Some error")

        mock_socket.accept.side_effect = accept_side_effect
        server.server_socket = mock_socket

        # Run serve_forever - should not raise, should handle exception
        server.serve_forever()

        # Verify loop continued after first exception
        assert call_count >= 2

    def test_serve_forever_applies_backoff_on_persistent_error(
        self, server: DaemonServer
    ) -> None:
        """Test that backoff delay is applied for non-timeout exceptions."""
        mock_socket = MagicMock(spec=socket.socket)
        call_count = 0
        call_times: list[float] = []

        def accept_side_effect():
            nonlocal call_count
            call_count += 1
            call_times.append(time.time())
            if call_count >= 3:
                server.running = False
            raise RuntimeError("Persistent error")

        mock_socket.accept.side_effect = accept_side_effect
        server.server_socket = mock_socket

        # Run serve_forever
        server.serve_forever()

        # Verify backoff was applied (calls should be spaced apart)
        assert call_count >= 2
        if len(call_times) >= 2:
            # There should be some delay between calls (backoff)
            # We expect at least 0.05s delay due to backoff
            time_diff = call_times[-1] - call_times[0]
            # With 3 calls and ~0.1s backoff, should take at least 0.1s total
            assert time_diff >= 0.05, f"Expected backoff delay, but calls were {time_diff}s apart"


class TestModelCleanup:
    """Tests for model resource cleanup."""

    @pytest.fixture
    def temp_socket_path(self, tmp_path: Path) -> Path:
        """Temporary socket path for testing."""
        return tmp_path / "test.sock"

    def test_cleanup_releases_embedder(self, temp_socket_path: Path) -> None:
        """Test cleanup releases embedder model resources."""
        server = DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=0,
        )

        # Create mock embedder
        mock_embedder = MagicMock()
        server.embedder = mock_embedder

        # Create socket file to be cleaned up
        temp_socket_path.parent.mkdir(parents=True, exist_ok=True)
        temp_socket_path.touch()

        # Create mock server socket
        server.server_socket = MagicMock(spec=socket.socket)

        # Call cleanup
        server.cleanup()

        # Verify embedder was set to None (releases reference)
        assert server.embedder is None

    def test_cleanup_handles_no_embedder(self, temp_socket_path: Path) -> None:
        """Test cleanup works when embedder was never loaded."""
        server = DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=0,
        )

        # Embedder is None by default
        assert server.embedder is None

        # Create socket file
        temp_socket_path.parent.mkdir(parents=True, exist_ok=True)
        temp_socket_path.touch()

        # Create mock server socket
        server.server_socket = MagicMock(spec=socket.socket)

        # Cleanup should not raise
        server.cleanup()

    def test_run_cleans_up_on_success(self, temp_socket_path: Path) -> None:
        """Test run() calls cleanup after serve_forever completes."""
        server = DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=0,
        )

        # Mock all the methods called by run()
        with (
            patch.object(server, "setup_signal_handlers"),
            patch.object(server, "load_model"),
            patch.object(server, "create_socket"),
            patch.object(server, "serve_forever"),
            patch.object(server, "cleanup") as mock_cleanup,
        ):
            server.run()

            # Verify cleanup was called
            mock_cleanup.assert_called_once()

    def test_run_cleans_up_on_exception(self, temp_socket_path: Path) -> None:
        """Test run() calls cleanup even after exceptions."""
        server = DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=0,
        )

        # Mock methods, with load_model raising an exception
        with (
            patch.object(server, "setup_signal_handlers"),
            patch.object(server, "load_model", side_effect=RuntimeError("Model load failed")),
            patch.object(server, "cleanup") as mock_cleanup,
            pytest.raises(SystemExit),
        ):
            server.run()

            # Verify cleanup was still called
            mock_cleanup.assert_called_once()
