"""Integration tests for daemon-based embedding service.

Tests the daemon server, client, and lifecycle management.
"""


import signal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ember.adapters.daemon.client import (
    DaemonEmbedderClient,
    get_daemon_pid,
    is_daemon_running,
)
from ember.adapters.daemon.lifecycle import DaemonLifecycle
from ember.adapters.daemon.protocol import ProtocolError, Request, Response
from ember.adapters.daemon.server import DaemonServer


@pytest.fixture
def temp_socket_path(tmp_path):
    """Temporary socket path for testing.

    Uses a short base path (/tmp) to avoid AF_UNIX path length limits (~104 chars on macOS).
    The pytest tmp_path can be too long for Unix domain sockets.
    """
    # Create a short temp directory for the socket
    # Unix sockets have ~104 char limit on macOS, pytest tmp_path can exceed this
    short_tmp = tempfile.mkdtemp(prefix="emb_", dir="/tmp")
    socket_path = Path(short_tmp) / "d.sock"  # Keep filename short too
    yield socket_path
    # Cleanup
    if socket_path.exists():
        socket_path.unlink()
    Path(short_tmp).rmdir()


@pytest.fixture
def temp_pid_file(tmp_path):
    """Temporary PID file for testing."""
    return tmp_path / "test-daemon.pid"


@pytest.fixture
def temp_log_file(tmp_path):
    """Temporary log file for testing."""
    return tmp_path / "test-daemon.log"


class TestProtocol:
    """Test JSON-RPC protocol."""

    def test_request_serialization(self):
        """Test request serialization and deserialization."""
        req = Request(method="embed_texts", params={"texts": ["hello"]}, request_id=1)
        json_str = req.to_json()

        # Deserialize
        req2 = Request.from_json(json_str)
        assert req2.method == "embed_texts"
        assert req2.params == {"texts": ["hello"]}
        assert req2.id == 1

    def test_response_serialization(self):
        """Test response serialization and deserialization."""
        resp = Response.success([[0.1, 0.2]], request_id=1)
        json_str = resp.to_json()

        # Deserialize
        resp2 = Response.from_json(json_str)
        assert resp2.result == [[0.1, 0.2]]
        assert resp2.error is None
        assert resp2.id == 1

    def test_error_response(self):
        """Test error response."""
        resp = Response.error(code=500, message="Model failed", request_id=1)
        assert resp.is_error()
        assert resp.error["code"] == 500
        assert resp.error["message"] == "Model failed"

    def test_invalid_json(self):
        """Test invalid JSON handling."""
        with pytest.raises(ProtocolError):
            Request.from_json("{invalid json")

    def test_large_message_handling(self):
        """Test that messages larger than buffer size (4096 bytes) are handled correctly."""
        import socket
        import threading

        from ember.adapters.daemon.protocol import receive_message, send_message

        # Create a large request (>4096 bytes)
        large_texts = ["x" * 1000 for _ in range(10)]  # ~10KB of text
        large_request = Request(
            method="embed_texts", params={"texts": large_texts}, request_id=1
        )

        # Create socket pair for testing
        server_sock, client_sock = socket.socketpair()

        try:
            # Send large message in separate thread
            def send_large_message():
                send_message(client_sock, large_request)

            sender = threading.Thread(target=send_large_message)
            sender.start()

            # Receive and verify
            received = receive_message(server_sock, Request)
            sender.join()

            assert received.method == "embed_texts"
            assert received.params["texts"] == large_texts
            assert len(large_request.to_json()) > 4096  # Verify it's actually large

        finally:
            server_sock.close()
            client_sock.close()

    def test_multiple_messages_warns(self, caplog):
        """Test that multiple messages in one recv() triggers a warning."""
        import socket

        from ember.adapters.daemon.protocol import receive_message

        # Create two small messages
        req1 = Request(method="health", params={}, request_id=1)
        req2 = Request(method="health", params={}, request_id=2)

        # Create socket pair
        server_sock, client_sock = socket.socketpair()

        try:
            # Send both messages at once (without waiting for response)
            data = req1.to_json().encode("utf-8") + req2.to_json().encode("utf-8")
            client_sock.sendall(data)

            # Receive should get first message and warn about second
            with caplog.at_level("WARNING"):
                received = receive_message(server_sock, Request)

            # Should receive first message
            assert received.method == "health"
            assert received.id == 1

            # Should have logged warning about remaining data
            assert any(
                "bytes after first message delimiter" in record.message
                for record in caplog.records
            )

        finally:
            server_sock.close()
            client_sock.close()


class TestDaemonServer:
    """Test daemon server."""

    def test_server_initialization(self, temp_socket_path):
        """Test server can be initialized."""
        server = DaemonServer(
            socket_path=temp_socket_path,
            idle_timeout=0,  # Disable timeout for testing
        )
        assert server.socket_path == temp_socket_path
        assert server.embedder is None
        assert server.requests_served == 0

    def test_handle_health_request(self, temp_socket_path):
        """Test health check request handling."""
        import os

        server = DaemonServer(socket_path=temp_socket_path, idle_timeout=0)

        request = Request(method="health", params={})
        response = server.handle_request(request)

        assert not response.is_error()
        assert response.result["status"] == "ok"
        assert response.result["pid"] == os.getpid()

    def test_handle_unknown_method(self, temp_socket_path):
        """Test unknown method handling."""
        server = DaemonServer(socket_path=temp_socket_path, idle_timeout=0)

        request = Request(method="unknown", params={})
        response = server.handle_request(request)

        assert response.is_error()
        assert response.error["code"] == 404


class TestDaemonClient:
    """Test daemon client."""

    def test_client_initialization(self, temp_socket_path):
        """Test client can be initialized."""
        client = DaemonEmbedderClient(socket_path=temp_socket_path, fallback=False)
        assert client.socket_path == temp_socket_path
        assert not client._using_fallback

    def test_client_name_property(self, temp_socket_path):
        """Test client name property."""
        client = DaemonEmbedderClient(socket_path=temp_socket_path)
        assert "jina" in client.name.lower()

    def test_client_dim_property(self, temp_socket_path):
        """Test client dim property."""
        client = DaemonEmbedderClient(socket_path=temp_socket_path)
        assert client.dim == 768  # Jina model dimension

    def test_client_fingerprint(self, temp_socket_path):
        """Test client fingerprint."""
        client = DaemonEmbedderClient(socket_path=temp_socket_path)
        fingerprint = client.fingerprint()
        assert isinstance(fingerprint, str)
        assert "jina" in fingerprint.lower()


class TestDaemonLifecycle:
    """Test daemon lifecycle management."""

    def test_lifecycle_initialization(self, temp_socket_path, temp_pid_file):
        """Test lifecycle manager initialization."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            idle_timeout=0,
        )
        assert lifecycle.socket_path == temp_socket_path
        assert lifecycle.pid_file == temp_pid_file

    def test_is_running_no_socket(self, temp_socket_path, temp_pid_file):
        """Test is_running when daemon is not running."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )
        assert not lifecycle.is_running()

    def test_cleanup_stale_files(self, temp_socket_path, temp_pid_file):
        """Test cleaning up stale files."""
        # Create stale socket
        temp_socket_path.parent.mkdir(parents=True, exist_ok=True)
        temp_socket_path.touch()

        # Create stale PID file with invalid PID
        temp_pid_file.write_text("999999")

        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )
        lifecycle.cleanup_stale_files()

        # Files should be removed
        assert not temp_socket_path.exists()
        assert not temp_pid_file.exists()

    def test_get_pid_no_file(self, temp_socket_path, temp_pid_file):
        """Test get_pid when no PID file exists."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )
        assert lifecycle.get_pid() is None

    def test_get_pid_invalid_content(self, temp_socket_path, temp_pid_file):
        """Test get_pid with invalid PID file content."""
        temp_pid_file.parent.mkdir(parents=True, exist_ok=True)
        temp_pid_file.write_text("not a number")

        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )
        assert lifecycle.get_pid() is None

    def test_status_stopped(self, temp_socket_path, temp_pid_file):
        """Test status when daemon is stopped."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )
        status = lifecycle.status()

        assert not status["running"]
        assert status["status"] == "stopped"
        assert "not running" in status["message"].lower()

    def test_status_recovers_pid_when_pid_file_missing(
        self, temp_socket_path, temp_pid_file
    ):
        """Test status recovers PID from daemon when PID file is missing (#214).

        This tests the fix for issue #214 where status would show "PID None"
        when daemon is running but PID file was deleted.
        """
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )

        # Mock daemon running but PID file missing
        with (
            patch.object(lifecycle, "is_running", return_value=True),
            patch.object(lifecycle, "get_pid", return_value=None),  # No PID file
            patch(
                "ember.adapters.daemon.lifecycle.get_daemon_pid", return_value=12345
            ) as mock_get_pid,
        ):
            status = lifecycle.status()

            # Should have recovered PID from daemon
            mock_get_pid.assert_called_once_with(temp_socket_path)
            assert status["running"] is True
            assert status["pid"] == 12345
            assert status["status"] == "running"
            assert "PID 12345" in status["message"]

    def test_status_never_shows_pid_none_when_running(
        self, temp_socket_path, temp_pid_file
    ):
        """Test status never shows 'PID None' when daemon is actually running (#214)."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )

        # Mock daemon running but both PID file and health check fail to get PID
        with (
            patch.object(lifecycle, "is_running", return_value=True),
            patch.object(lifecycle, "get_pid", return_value=None),
            patch(
                "ember.adapters.daemon.lifecycle.get_daemon_pid", return_value=None
            ),
        ):
            status = lifecycle.status()

            # Should never show "PID None" - use "unknown" instead
            assert status["running"] is True
            assert status["pid"] is None
            assert "PID None" not in status["message"]
            assert "unknown" in status["message"].lower()

    def test_stop_sigterm_failure_falls_through_to_sigkill(
        self, temp_socket_path, temp_pid_file
    ):
        """Test that SIGTERM failure falls through to SIGKILL instead of returning False."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )

        # Create PID file with fake PID
        temp_pid_file.parent.mkdir(parents=True, exist_ok=True)
        fake_pid = 12345
        temp_pid_file.write_text(str(fake_pid))

        with patch("os.kill") as mock_kill:
            # Track call count to os.kill
            call_count = [0]

            def kill_side_effect(pid, sig):
                """Simulate SIGTERM failure, SIGKILL success."""
                call_count[0] += 1
                if sig == signal.SIGTERM:
                    # SIGTERM fails with permission error
                    raise OSError("Permission denied")
                # SIGKILL succeeds (no exception)

            mock_kill.side_effect = kill_side_effect

            # Mock is_process_alive to show process dies after SIGKILL
            with patch.object(lifecycle, "is_process_alive") as mock_alive:
                # Initial check (alive), check after SIGTERM fails (alive),
                # check after SIGKILL (dead), cleanup check (dead)
                mock_alive.side_effect = [True, True, False, False]

                result = lifecycle.stop()

                # Should succeed via SIGKILL fallback
                assert result is True

                # Verify SIGKILL was attempted (after SIGTERM failed)
                assert call_count[0] == 2  # SIGTERM + SIGKILL
                mock_kill.assert_any_call(fake_pid, signal.SIGTERM)
                mock_kill.assert_any_call(fake_pid, signal.SIGKILL)

    def test_stop_sigkill_verifies_death(self, temp_socket_path, temp_pid_file):
        """Test that SIGKILL verifies process death before returning True."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )

        # Create PID file
        temp_pid_file.parent.mkdir(parents=True, exist_ok=True)
        fake_pid = 12345
        temp_pid_file.write_text(str(fake_pid))

        with patch("os.kill") as mock_kill:
            # SIGTERM timeout (process ignores it)
            # SIGKILL succeeds but process survives (zombie)
            mock_kill.return_value = None  # No exception

            with patch.object(lifecycle, "is_process_alive") as mock_alive:
                # Process stays alive: initial, during SIGTERM wait (timeout * 2), after SIGKILL
                mock_alive.return_value = True  # Always alive (zombie!)

                result = lifecycle.stop(timeout=1)  # Short timeout for test speed

                # Should return False because process survived SIGKILL
                assert result is False

                # Verify SIGKILL was attempted
                mock_kill.assert_any_call(fake_pid, signal.SIGKILL)

                # Verify is_process_alive was checked after SIGKILL
                # (initial check + timeout checks + final verification)
                assert mock_alive.call_count > 2

    def test_stop_cleanup_only_after_verified_death(
        self, temp_socket_path, temp_pid_file
    ):
        """Test that cleanup happens only after verified death."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )

        # Create PID file and socket
        temp_pid_file.parent.mkdir(parents=True, exist_ok=True)
        fake_pid = 12345
        temp_pid_file.write_text(str(fake_pid))
        temp_socket_path.touch()

        with patch("os.kill") as mock_kill:
            mock_kill.return_value = None

            with patch.object(lifecycle, "is_process_alive") as mock_alive:
                # Initial check (alive), wait loop check (dead), cleanup check (dead)
                mock_alive.side_effect = [True, False, False]

                with patch.object(lifecycle, "cleanup_stale_files") as mock_cleanup:
                    result = lifecycle.stop()

                    # Should succeed
                    assert result is True

                    # Cleanup should be called exactly once after verification
                    mock_cleanup.assert_called_once()

    def test_stop_process_dies_before_sigterm(self, temp_socket_path, temp_pid_file):
        """Test handling when process dies between existence check and SIGTERM."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
        )

        # Create PID file
        temp_pid_file.parent.mkdir(parents=True, exist_ok=True)
        fake_pid = 12345
        temp_pid_file.write_text(str(fake_pid))

        with patch("os.kill") as mock_kill:
            # SIGTERM fails because process no longer exists
            mock_kill.side_effect = OSError("No such process")

            with patch.object(lifecycle, "is_process_alive") as mock_alive:
                # Initial check (alive), check after SIGTERM fails (dead), cleanup check (dead)
                mock_alive.side_effect = [True, False, False]

                result = lifecycle.stop()

                # Should succeed (process already dead)
                assert result is True

                # SIGTERM should have been attempted
                mock_kill.assert_called_once_with(fake_pid, signal.SIGTERM)

    def test_start_instant_failure_no_pid_file(
        self, temp_socket_path, temp_pid_file, temp_log_file
    ):
        """Test that instant daemon failure doesn't create PID file."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
        )

        # Create mock process that exits immediately with error
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = 1  # Exit code 1 (failure)
        mock_process.stderr.read.return_value = b"Model loading failed: corrupted file"

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError) as exc_info:
                lifecycle.start(foreground=False)

            # Should raise error with exit code and stderr
            error_msg = str(exc_info.value)
            assert "exit code: 1" in error_msg
            assert "Model loading failed" in error_msg

            # PID file should NOT have been created
            assert not temp_pid_file.exists()

    def test_start_failure_during_ready_wait_cleans_pid(
        self, temp_socket_path, temp_pid_file, temp_log_file
    ):
        """Test that failure during ready-wait cleans up PID file."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
        )

        # Create mock process that survives initial check but dies during ready-wait
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still alive initially
        mock_process.stderr = None  # No stderr to read

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch.object(lifecycle, "is_running", return_value=False),
            patch.object(lifecycle, "is_process_alive") as mock_alive,
            # Mock time.sleep to skip actual waits (avoids 20s timeout delay)
            patch("ember.adapters.daemon.lifecycle.time.sleep"),
        ):
            # Process dies during ready-wait
            mock_alive.return_value = False

            with pytest.raises(RuntimeError) as exc_info:
                lifecycle.start(foreground=False)

            # Should raise error about unexpected exit
            error_msg = str(exc_info.value)
            assert "exited unexpectedly" in error_msg

            # PID file should have been cleaned up
            assert not temp_pid_file.exists()

    def test_start_timeout_kills_unresponsive_process(
        self, temp_socket_path, temp_pid_file, temp_log_file
    ):
        """Test that startup timeout terminates unresponsive daemon process (#216).

        This prevents the race condition where:
        1. Daemon is spawned but takes too long to start (e.g., slow model load)
        2. Health check times out after 20s
        3. PID file is deleted but process continues in background
        4. Process eventually becomes ready
        5. Status shows "running (PID None)" because no PID file

        The fix: kill the process before deleting PID file.
        """
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
        )

        # Create mock process that stays alive but never becomes ready
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still alive
        mock_process.stderr = None

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch.object(lifecycle, "is_running", return_value=False),  # Never ready
            patch("ember.adapters.daemon.lifecycle.time.sleep"),  # Skip waits
            patch("os.kill") as mock_kill,
            # is_process_alive: True initially (for timeout handler), then False after kill
            patch.object(lifecycle, "is_process_alive", side_effect=[True, False]),
            pytest.raises(RuntimeError) as exc_info,
        ):
            lifecycle.start(foreground=False)

        # Should raise error about not responding
        error_msg = str(exc_info.value)
        assert "not responding to health checks" in error_msg
        assert "terminated" in error_msg

        # SIGTERM should have been sent to kill the process
        mock_kill.assert_any_call(12345, signal.SIGTERM)

        # PID file should have been cleaned up
        assert not temp_pid_file.exists()

    def test_start_instant_failure_closes_stderr(
        self, temp_socket_path, temp_pid_file, temp_log_file
    ):
        """Test that stderr is closed when daemon fails immediately (issue #139)."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
        )

        # Create mock process that exits immediately with error
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = 1  # Exit code 1 (failure)
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b"Model loading failed"
        mock_process.stderr = mock_stderr

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError):
                lifecycle.start(foreground=False)

            # stderr should have been closed in the finally block
            mock_stderr.close.assert_called_once()

    def test_start_pid_write_failure_terminates_process(
        self, temp_socket_path, temp_log_file, tmp_path
    ):
        """Test that PID file write failure terminates spawned process (#152)."""
        # Use a non-existent directory to cause write failure
        nonexistent_dir = tmp_path / "nonexistent_dir" / "subdir"
        pid_file = nonexistent_dir / "daemon.pid"

        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=pid_file,
            log_file=temp_log_file,
        )

        # Create mock process
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stderr = None

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError) as exc_info:
                lifecycle.start(foreground=False)

            # Should raise error about PID file
            error_msg = str(exc_info.value)
            assert "Failed to write PID file" in error_msg

            # Process should have been terminated to avoid orphan
            mock_process.terminate.assert_called_once()

    def test_start_pid_written_before_poll_check(
        self, temp_socket_path, temp_pid_file, temp_log_file
    ):
        """Test that PID is written before checking if process died (#152).

        This eliminates the race condition where process could die between
        alive check and PID write, leaving a stale PID file.
        """
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
        )

        # Track when poll() is called relative to PID file
        poll_called_pid_exists = None

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stderr = None

        def poll_side_effect():
            nonlocal poll_called_pid_exists
            # Record whether PID file existed when poll was called
            poll_called_pid_exists = temp_pid_file.exists()
            return None  # Process alive

        mock_process.poll.side_effect = poll_side_effect

        # is_running: False initially (so we enter start logic), then True (daemon ready)
        is_running_calls = [False, True]

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch.object(lifecycle, "is_running", side_effect=is_running_calls),
        ):
            lifecycle.start(foreground=False)

            # PID file should have been written BEFORE poll() was called
            assert poll_called_pid_exists is True, (
                "PID file should exist before poll() check - race condition!"
            )


class TestEndToEnd:
    """End-to-end integration tests.

    These tests actually start the daemon and test full workflow.
    They are slower and marked as integration tests.
    """

    @pytest.mark.slow
    def test_daemon_start_stop(self, temp_socket_path, temp_pid_file, temp_log_file):
        """Test starting and stopping the daemon."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
            idle_timeout=60,  # 1 minute for testing
        )

        # Should not be running initially
        assert not lifecycle.is_running()

        # Start daemon
        assert lifecycle.start(foreground=False)

        # Should now be running
        assert lifecycle.is_running()
        assert temp_socket_path.exists()
        assert temp_pid_file.exists()

        # Stop daemon
        assert lifecycle.stop()

        # Should not be running
        assert not lifecycle.is_running()

    @pytest.mark.slow
    def test_daemon_embedding_workflow(
        self, temp_socket_path, temp_pid_file, temp_log_file
    ):
        """Test full embedding workflow with daemon."""
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
            idle_timeout=60,
        )

        # Start daemon
        lifecycle.start(foreground=False)

        try:
            # Create client
            client = DaemonEmbedderClient(socket_path=temp_socket_path, fallback=False)

            # Embed some texts
            texts = ["def hello():", "class Foo:", "import numpy"]
            embeddings = client.embed_texts(texts)

            # Verify results
            assert len(embeddings) == 3
            assert len(embeddings[0]) == 768  # Jina model dimension
            assert all(isinstance(val, float) for val in embeddings[0])

            # Test empty input
            assert client.embed_texts([]) == []

        finally:
            # Clean up
            lifecycle.stop()

    @pytest.mark.slow
    def test_client_fallback_on_daemon_failure(self, temp_socket_path):
        """Test client falls back to direct mode when daemon unavailable."""
        # Create client with fallback enabled but auto_start disabled
        # This ensures the daemon won't be started, forcing fallback
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path, fallback=True, auto_start=False
        )

        # Daemon is not running, so should fallback to direct mode
        texts = ["def test():"]
        embeddings = client.embed_texts(texts)

        # Should succeed via fallback
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 768
        assert client._using_fallback  # Should have switched to fallback

    def test_is_daemon_running_helper(self, temp_socket_path):
        """Test is_daemon_running helper function."""
        # Should return False when daemon not running
        assert not is_daemon_running(temp_socket_path)

    def test_get_daemon_pid_returns_none_when_not_running(self, temp_socket_path):
        """Test get_daemon_pid returns None when daemon not running."""
        assert get_daemon_pid(temp_socket_path) is None

    def test_daemon_startup_failure_raises_before_client_embed(
        self, temp_socket_path, temp_pid_file, temp_log_file
    ):
        """Test that daemon startup failures raise RuntimeError during start().

        This ensures that failures are caught early (before TUI initialization)
        when _create_embedder() calls daemon_manager.start() in interactive search mode.
        Related to issue #126.
        """
        lifecycle = DaemonLifecycle(
            socket_path=temp_socket_path,
            pid_file=temp_pid_file,
            log_file=temp_log_file,
        )

        # Mock subprocess.Popen to simulate immediate daemon failure
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = 1  # Exit code 1 (failure)
        mock_process.stderr.read.return_value = b"Model loading failed: corrupted file"

        with patch("subprocess.Popen", return_value=mock_process):
            # start() should raise RuntimeError immediately
            with pytest.raises(RuntimeError) as exc_info:
                lifecycle.start(foreground=False)

            # Verify error message contains useful info
            error_msg = str(exc_info.value)
            assert "exit code: 1" in error_msg
            assert "Model loading failed" in error_msg

            # PID file should NOT have been created (failure was instant)
            assert not temp_pid_file.exists()


# Slow tests can be run with: pytest -m slow
# Or skipped with: pytest -m "not slow"
