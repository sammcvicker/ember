"""Tests for daemon client and server thread safety (issue #439).

Tests cover:
1. Fallback flag race condition - only one fallback embedder created
2. Request counter atomicity - accurate stats under concurrent access
3. Fallback embedder cleanup - close() releases resources
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ember.adapters.daemon.client import DaemonEmbedderClient
from ember.adapters.daemon.server import DaemonServer

# ============================================================================
# 1. Fallback transition thread safety
# ============================================================================


class TestFallbackThreadSafety:
    """Test that fallback transition is thread-safe."""

    @pytest.fixture
    def temp_socket_path(self, tmp_path: Path) -> Path:
        """Temporary socket path for testing."""
        return tmp_path / "test.sock"

    def test_concurrent_fallback_creates_single_embedder(
        self, temp_socket_path: Path
    ) -> None:
        """Multiple threads hitting daemon errors should create only one fallback embedder.

        This is the core race condition from issue #439: two threads hitting a daemon
        error simultaneously could both enter the fallback creation path and create
        duplicate embedders, wasting GPU memory.
        """
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=True,
            auto_start=False,
        )

        # Track how many times create_embedder is called
        create_count = 0
        create_lock = threading.Lock()

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1, 0.2, 0.3]]
        mock_embedder.name = "test-model"
        mock_embedder.dim = 3

        def counting_create_embedder(**kwargs):
            nonlocal create_count
            with create_lock:
                create_count += 1
            # Simulate slow model loading to widen the race window
            time.sleep(0.05)
            return mock_embedder

        # Barrier to synchronize thread start
        barrier = threading.Barrier(10)
        errors: list[Exception] = []

        def thread_func():
            try:
                barrier.wait(timeout=5)
                client.embed_texts(["test"])
            except Exception as e:
                errors.append(e)

        with patch(
            "ember.adapters.local_models.registry.create_embedder",
            side_effect=counting_create_embedder,
        ):
            threads = [threading.Thread(target=thread_func) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert not errors, f"Threads raised errors: {errors}"
        # Only one fallback embedder should have been created
        assert create_count == 1, (
            f"Expected exactly 1 call to create_embedder, got {create_count}. "
            f"Race condition: multiple threads created fallback embedders."
        )

    def test_fallback_transition_sets_flag_atomically(
        self, temp_socket_path: Path
    ) -> None:
        """After fallback transition, all subsequent calls use fallback directly.

        The _using_fallback flag and _fallback_embedder should be set together
        under lock protection so no thread sees an inconsistent state.
        """
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=True,
            auto_start=False,
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1, 0.2, 0.3]]
        mock_embedder.name = "test-model"
        mock_embedder.dim = 3

        with patch(
            "ember.adapters.local_models.registry.create_embedder",
            return_value=mock_embedder,
        ):
            # First call triggers fallback
            client.embed_texts(["trigger fallback"])

        assert client._using_fallback is True
        assert client._fallback_embedder is not None

        # Subsequent calls should go straight to fallback (no daemon attempt)
        mock_embedder.embed_texts.return_value = [[0.4, 0.5, 0.6]]
        result = client.embed_texts(["already in fallback"])
        assert result == [[0.4, 0.5, 0.6]]

    def test_embed_texts_without_fallback_raises_on_daemon_failure(
        self, temp_socket_path: Path
    ) -> None:
        """When fallback is disabled, daemon failure should raise RuntimeError."""
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=False,
            auto_start=False,
        )

        with pytest.raises(RuntimeError, match="Daemon failed and fallback disabled"):
            client.embed_texts(["test"])


# ============================================================================
# 2. Request counter thread safety
# ============================================================================


class TestRequestCounterThreadSafety:
    """Test that request counters are thread-safe."""

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

    def test_concurrent_request_counting(self, server: DaemonServer) -> None:
        """Concurrent handle_client calls should produce accurate request count.

        Without a lock, `self.requests_served += 1` can lose increments under
        concurrent access because read-modify-write is not atomic at the bytecode level.
        """
        # Set up a mock embedder for embed_texts requests
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1, 0.2]]
        server.embedder = mock_embedder

        num_threads = 50
        barrier = threading.Barrier(num_threads)
        errors: list[Exception] = []

        def thread_func():
            try:
                barrier.wait(timeout=5)
                # Call update_stats directly to test the counter
                server.update_stats()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=thread_func) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Threads raised errors: {errors}"
        assert server.requests_served == num_threads, (
            f"Expected {num_threads} requests_served, got {server.requests_served}. "
            f"Race condition: lost counter increments."
        )

    def test_last_request_time_updated_under_lock(
        self, server: DaemonServer
    ) -> None:
        """last_request_time should be updated atomically with requests_served."""
        initial_time = server.last_request_time

        # Small delay to ensure time difference
        time.sleep(0.01)
        server.update_stats()

        assert server.requests_served == 1
        assert server.last_request_time > initial_time

    def test_stats_endpoint_reads_consistent_values(
        self, server: DaemonServer
    ) -> None:
        """Stats endpoint should read consistent counter values."""
        from ember.adapters.daemon.protocol import Request

        # Simulate some requests
        for _ in range(5):
            server.update_stats()

        request = Request(method="stats", params={})
        response = server.handle_request(request)

        assert not response.is_error()
        assert response.result["requests_served"] == 5


# ============================================================================
# 3. Fallback embedder cleanup
# ============================================================================


class TestFallbackEmbedderCleanup:
    """Test that fallback embedder is properly cleaned up."""

    @pytest.fixture
    def temp_socket_path(self, tmp_path: Path) -> Path:
        """Temporary socket path for testing."""
        return tmp_path / "test.sock"

    def test_close_releases_fallback_embedder(
        self, temp_socket_path: Path
    ) -> None:
        """close() should release the fallback embedder reference."""
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=True,
            auto_start=False,
        )

        # Manually set a fallback embedder
        mock_embedder = MagicMock()
        client._fallback_embedder = mock_embedder
        client._using_fallback = True

        # Close should release it
        client.close()

        assert client._fallback_embedder is None
        assert client._using_fallback is False

    def test_close_is_idempotent(self, temp_socket_path: Path) -> None:
        """Calling close() multiple times should not raise errors."""
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=True,
            auto_start=False,
        )

        # Close with no fallback embedder created
        client.close()
        client.close()  # Should not raise

        # Close after setting a fallback embedder
        client._fallback_embedder = MagicMock()
        client._using_fallback = True
        client.close()
        client.close()  # Should not raise

    def test_close_resets_state_for_potential_reuse(
        self, temp_socket_path: Path
    ) -> None:
        """After close(), client should be in a clean state.

        If the client is reused after close(), it should try the daemon
        again before falling back.
        """
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=True,
            auto_start=False,
        )

        client._fallback_embedder = MagicMock()
        client._using_fallback = True

        client.close()

        assert client._using_fallback is False
        assert client._fallback_embedder is None

    def test_context_manager_support(self, temp_socket_path: Path) -> None:
        """Client should support context manager protocol for automatic cleanup."""
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=True,
            auto_start=False,
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1, 0.2, 0.3]]

        with (
            patch(
                "ember.adapters.local_models.registry.create_embedder",
                return_value=mock_embedder,
            ),
            client,
        ):
            client.embed_texts(["test"])
            assert client._using_fallback is True
            assert client._fallback_embedder is not None

        # After exiting context, fallback should be cleaned up
        assert client._fallback_embedder is None
        assert client._using_fallback is False

    def test_context_manager_cleans_up_on_exception(
        self, temp_socket_path: Path
    ) -> None:
        """Context manager should clean up even if an exception occurs."""
        client = DaemonEmbedderClient(
            socket_path=temp_socket_path,
            fallback=True,
            auto_start=False,
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.side_effect = RuntimeError("embedding failed")

        with pytest.raises(RuntimeError, match="embedding failed"), patch(
            "ember.adapters.local_models.registry.create_embedder",
            return_value=mock_embedder,
        ), client:
            # First call triggers fallback and creates embedder
            client._fallback_embedder = mock_embedder
            client._using_fallback = True
            # This call raises
            client.embed_texts(["test"])

        # Should still be cleaned up
        assert client._fallback_embedder is None
        assert client._using_fallback is False
