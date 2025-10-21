"""Daemon client adapter for embedding requests.

Implements the Embedder protocol by communicating with a daemon server.
Falls back to direct mode if daemon is unavailable.
"""

import logging
import socket
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
    from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

logger = logging.getLogger(__name__)


class DaemonError(Exception):
    """Base exception for daemon-related errors."""

    pass


class DaemonEmbedderClient:
    """Embedder client that communicates with daemon server.

    Implements the Embedder protocol. Connects to daemon via Unix socket
    and sends embed_texts requests. Falls back to direct mode on errors.
    """

    def __init__(
        self,
        socket_path: Path | None = None,
        fallback: bool = True,
        max_seq_length: int = 512,
        batch_size: int = 32,
    ):
        """Initialize daemon client.

        Args:
            socket_path: Path to daemon socket (default: ~/.ember/daemon.sock)
            fallback: Enable fallback to direct mode on errors
            max_seq_length: Max sequence length for fallback embedder
            batch_size: Batch size for fallback embedder
        """
        self.socket_path = socket_path or (Path.home() / ".ember" / "daemon.sock")
        self.fallback_enabled = fallback
        self.max_seq_length = max_seq_length
        self.batch_size = batch_size

        # Lazy-loaded fallback embedder
        self._fallback_embedder: JinaCodeEmbedder | None = None
        self._using_fallback = False

    @property
    def name(self) -> str:
        """Model name."""
        # Use fallback embedder if we've switched to it
        if self._using_fallback and self._fallback_embedder:
            return self._fallback_embedder.name
        # Otherwise return the Jina model name (same as direct mode)
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        return JinaCodeEmbedder.MODEL_NAME

    @property
    def dim(self) -> int:
        """Embedding dimension."""
        if self._using_fallback and self._fallback_embedder:
            return self._fallback_embedder.dim
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        return JinaCodeEmbedder.MODEL_DIM

    def fingerprint(self) -> str:
        """Unique fingerprint identifying model + config."""
        if self._using_fallback and self._fallback_embedder:
            return self._fallback_embedder.fingerprint()

        # Generate fingerprint matching direct mode
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        # Use a temporary embedder just for fingerprint (doesn't load model)
        temp_embedder = JinaCodeEmbedder(
            max_seq_length=self.max_seq_length, batch_size=self.batch_size
        )
        return temp_embedder.fingerprint()

    def _get_fallback_embedder(self) -> "JinaCodeEmbedder":
        """Get or create fallback embedder.

        Returns:
            JinaCodeEmbedder instance for direct mode
        """
        if self._fallback_embedder is None:
            from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

            logger.info("Creating fallback embedder (direct mode)")
            self._fallback_embedder = JinaCodeEmbedder(
                max_seq_length=self.max_seq_length, batch_size=self.batch_size
            )
        return self._fallback_embedder

    def _connect(self) -> socket.socket:
        """Connect to daemon socket.

        Returns:
            Connected socket

        Raises:
            DaemonError: If connection fails
        """
        if not self.socket_path.exists():
            raise DaemonError(f"Daemon socket not found: {self.socket_path}")

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5.0)  # 5 second timeout
            sock.connect(str(self.socket_path))
            return sock
        except Exception as e:
            raise DaemonError(f"Failed to connect to daemon: {e}") from e

    def _daemon_embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using daemon.

        Args:
            texts: Texts to embed

        Returns:
            List of embedding vectors

        Raises:
            DaemonError: If daemon request fails
        """
        sock = None
        try:
            # Connect to daemon
            sock = self._connect()

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
        finally:
            if sock:
                sock.close()

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
        # Try to connect and send health check
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(str(socket_path))

        request = Request(method="health", params={})
        send_message(sock, request)

        response = receive_message(sock, Response)
        sock.close()

        return not response.is_error()
    except Exception:
        return False
