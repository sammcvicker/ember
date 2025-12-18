"""Daemon client adapter for embedding requests.

Implements the Embedder protocol by communicating with a daemon server.
Falls back to direct mode if daemon is unavailable.
"""

import contextlib
import logging
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ember.adapters.daemon.protocol import (
    ProtocolError,
    Request,
    Response,
    receive_message,
    send_message,
)

if TYPE_CHECKING:
    from ember.ports.embedders import Embedder

logger = logging.getLogger(__name__)


# ============================================================================
# Socket Connection Management
# ============================================================================


@contextmanager
def daemon_socket_connection(
    socket_path: Path,
    timeout: float = 5.0,
) -> Iterator[socket.socket]:
    """Context manager for daemon socket connections.

    Provides consistent socket setup, timeout configuration, and cleanup
    for all daemon communication. Handles connection lifecycle automatically.

    Args:
        socket_path: Path to the Unix domain socket.
        timeout: Socket operation timeout in seconds.

    Yields:
        Connected socket ready for communication.

    Raises:
        ConnectionRefusedError: If daemon is not accepting connections.
        FileNotFoundError: If socket file doesn't exist.
        TimeoutError: If connection times out.
        OSError: For other socket-related errors.

    Example:
        with daemon_socket_connection(socket_path) as sock:
            send_message(sock, request)
            response = receive_message(sock, Response)
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(socket_path))
        yield sock
    finally:
        with contextlib.suppress(OSError):
            sock.close()


class DaemonError(Exception):
    """Base exception for daemon-related errors."""

    pass


class DaemonEmbedderClient:
    """Embedder client that communicates with daemon server.

    Implements the Embedder protocol. Connects to daemon via Unix socket
    and sends embed_texts requests. Auto-starts daemon if needed. Falls
    back to direct mode on errors.
    """

    def __init__(
        self,
        socket_path: Path | None = None,
        fallback: bool = True,
        auto_start: bool = True,
        max_seq_length: int = 512,
        batch_size: int = 32,
        daemon_timeout: int = 900,
        model_name: str | None = None,
    ):
        """Initialize daemon client.

        Args:
            socket_path: Path to daemon socket (default: ~/.ember/daemon.sock)
            fallback: Enable fallback to direct mode on errors
            auto_start: Auto-start daemon if not running
            max_seq_length: Max sequence length for fallback embedder
            batch_size: Batch size for fallback embedder
            daemon_timeout: Daemon idle timeout in seconds
            model_name: Embedding model preset or HuggingFace ID
        """
        self.socket_path = socket_path or (Path.home() / ".ember" / "daemon.sock")
        self.fallback_enabled = fallback
        self.auto_start = auto_start
        self.max_seq_length = max_seq_length
        self.batch_size = batch_size
        self.daemon_timeout = daemon_timeout
        self.model_name = model_name

        # Lazy-loaded fallback embedder
        self._fallback_embedder: Embedder | None = None
        self._using_fallback = False
        self._daemon_start_attempted = False

        # Cached model info from daemon health check
        self._cached_model_name: str | None = None
        self._cached_model_dim: int | None = None

    @property
    def name(self) -> str:
        """Model name."""
        # Use fallback embedder if we've switched to it
        if self._using_fallback and self._fallback_embedder:
            return self._fallback_embedder.name
        # Use cached value from daemon if available
        if self._cached_model_name:
            return self._cached_model_name
        # Otherwise use model info from registry
        from ember.adapters.local_models.registry import get_model_info

        info = get_model_info(self.model_name or "jina-code-v2")
        return info["name"]

    @property
    def dim(self) -> int:
        """Embedding dimension."""
        if self._using_fallback and self._fallback_embedder:
            return self._fallback_embedder.dim
        # Use cached value from daemon if available
        if self._cached_model_dim:
            return self._cached_model_dim
        # Otherwise use model info from registry
        from ember.adapters.local_models.registry import get_model_info

        info = get_model_info(self.model_name or "jina-code-v2")
        return info["dim"]

    def fingerprint(self) -> str:
        """Unique fingerprint identifying model + config."""
        if self._using_fallback and self._fallback_embedder:
            return self._fallback_embedder.fingerprint()

        # Generate fingerprint matching direct mode using registry
        from ember.adapters.local_models.registry import create_embedder

        # Use a temporary embedder just for fingerprint (doesn't load model)
        temp_embedder = create_embedder(
            model_name=self.model_name,
            max_seq_length=self.max_seq_length,
            batch_size=self.batch_size,
        )
        return temp_embedder.fingerprint()

    def _get_fallback_embedder(self) -> "Embedder":
        """Get or create fallback embedder.

        Returns:
            Embedder instance for direct mode
        """
        if self._fallback_embedder is None:
            from ember.adapters.local_models.registry import create_embedder

            logger.info(
                f"Creating fallback embedder (direct mode): "
                f"{self.model_name or 'default'}"
            )
            self._fallback_embedder = create_embedder(
                model_name=self.model_name,
                max_seq_length=self.max_seq_length,
                batch_size=self.batch_size,
            )
        return self._fallback_embedder

    def _ensure_daemon_running(self) -> bool:
        """Ensure daemon is running, start if needed.

        Returns:
            True if daemon is running, False otherwise
        """
        if not self.auto_start:
            return is_daemon_running(self.socket_path)

        if is_daemon_running(self.socket_path):
            return True

        if self._daemon_start_attempted:
            return False  # Already tried, don't retry

        # Try to start daemon
        try:
            from ember.adapters.daemon.lifecycle import DaemonLifecycle

            logger.info("Daemon not running, starting...")
            lifecycle = DaemonLifecycle(
                socket_path=self.socket_path,
                idle_timeout=self.daemon_timeout,
                model_name=self.model_name,
                batch_size=self.batch_size,
            )
            self._daemon_start_attempted = True
            return lifecycle.ensure_running()
        except (OSError, RuntimeError) as e:
            # OSError: process/socket errors, RuntimeError: daemon startup failures
            logger.error(f"Failed to start daemon: {e}", exc_info=True)
            return False

    def _daemon_embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using daemon.

        Args:
            texts: Texts to embed

        Returns:
            List of embedding vectors

        Raises:
            DaemonError: If daemon request fails
        """
        # Ensure daemon is running (auto-start if needed)
        if not self._ensure_daemon_running():
            raise DaemonError("Daemon is not running and failed to start")

        if not self.socket_path.exists():
            raise DaemonError(f"Daemon socket not found: {self.socket_path}")

        try:
            with daemon_socket_connection(self.socket_path, timeout=5.0) as sock:
                # Send request
                request = Request(method="embed_texts", params={"texts": texts})
                send_message(sock, request)

                # Receive response
                response = receive_message(sock, Response)

                # Check for errors
                if response.is_error():
                    error_msg = response.error.get("message", "Unknown error")
                    raise DaemonError(f"Daemon error: {error_msg}")

                return response.result

        except (ProtocolError, OSError) as e:
            raise DaemonError(f"Daemon communication failed: {e}") from e

    def ensure_loaded(self) -> None:
        """Ensure the model is loaded.

        For daemon mode, this is a no-op (daemon loads on startup).
        For fallback mode, loads the fallback embedder.
        """
        if self._using_fallback:
            self._get_fallback_embedder().ensure_loaded()
        # Otherwise, daemon handles loading

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using daemon or fallback.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (one per input text)

        Raises:
            RuntimeError: If both daemon and fallback fail
        """
        if not texts:
            return []

        # If already using fallback, go straight there
        if self._using_fallback:
            return self._get_fallback_embedder().embed_texts(texts)

        # Try daemon first
        try:
            return self._daemon_embed(texts)
        except DaemonError as e:
            # Daemon failed - fallback if enabled
            if not self.fallback_enabled:
                raise RuntimeError(f"Daemon failed and fallback disabled: {e}") from e

            logger.warning(f"Daemon failed, falling back to direct mode: {e}")
            self._using_fallback = True
            return self._get_fallback_embedder().embed_texts(texts)


def is_daemon_running(socket_path: Path | None = None) -> bool:
    """Check if daemon is running.

    Args:
        socket_path: Path to daemon socket (default: ~/.ember/daemon.sock)

    Returns:
        True if daemon is running and responding
    """
    socket_path = socket_path or (Path.home() / ".ember" / "daemon.sock")

    if not socket_path.exists():
        return False

    try:
        with daemon_socket_connection(socket_path, timeout=2.0) as sock:
            request = Request(method="health", params={})
            send_message(sock, request)
            response = receive_message(sock, Response)
            return not response.is_error()
    except (OSError, TimeoutError, ProtocolError):
        # Connection errors, timeouts, or protocol issues mean daemon is not available
        return False


def get_daemon_pid(socket_path: Path | None = None) -> int | None:
    """Get daemon PID via health check.

    This allows recovering the daemon PID even if the PID file is missing,
    by querying the daemon directly (#214).

    Args:
        socket_path: Path to daemon socket (default: ~/.ember/daemon.sock)

    Returns:
        Daemon PID if running and responding, None otherwise
    """
    socket_path = socket_path or (Path.home() / ".ember" / "daemon.sock")

    if not socket_path.exists():
        return None

    try:
        with daemon_socket_connection(socket_path, timeout=2.0) as sock:
            request = Request(method="health", params={})
            send_message(sock, request)
            response = receive_message(sock, Response)

            if response.is_error():
                return None

            # Extract PID from health response
            result = response.result
            if isinstance(result, dict) and "pid" in result:
                pid = result["pid"]
                if isinstance(pid, int):
                    return pid

            return None
    except (OSError, TimeoutError, ProtocolError):
        # Connection errors, timeouts, or protocol issues mean daemon is not available
        return None
