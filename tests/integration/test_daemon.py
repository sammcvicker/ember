"""Integration tests for daemon-based embedding service.

Tests the daemon server, client, and lifecycle management.
"""


import pytest

from ember.adapters.daemon.client import DaemonEmbedderClient, is_daemon_running
from ember.adapters.daemon.lifecycle import DaemonLifecycle
from ember.adapters.daemon.protocol import ProtocolError, Request, Response
from ember.adapters.daemon.server import DaemonServer


@pytest.fixture
def temp_socket_path(tmp_path):
    """Temporary socket path for testing."""
    return tmp_path / "test-daemon.sock"


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
        server = DaemonServer(socket_path=temp_socket_path, idle_timeout=0)

        request = Request(method="health", params={})
        response = server.handle_request(request)

        assert not response.is_error()
        assert response.result == {"status": "ok"}

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
        # Create client with fallback enabled
        client = DaemonEmbedderClient(socket_path=temp_socket_path, fallback=True)

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


# Slow tests can be run with: pytest -m slow
# Or skipped with: pytest -m "not slow"
