"""Daemon server that keeps embedding model loaded in memory.

The server:
1. Loads the embedding model on startup (one-time ~3s cost)
2. Listens on a Unix socket for embedding requests
3. Serves embedding requests using the pre-loaded model
4. Auto-shuts down after idle timeout (default 15 minutes)
"""

import logging
import signal
import socket
import sys
import time
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


class DaemonServer:
    """Embedding daemon server."""

    def __init__(
        self,
        socket_path: Path,
        idle_timeout: int = 900,
        model_name: str | None = None,
        model_max_seq_length: int | None = None,
        model_batch_size: int = 32,
    ):
        """Initialize daemon server.

        Args:
            socket_path: Path to Unix socket
            idle_timeout: Seconds of inactivity before shutdown (0 = never)
            model_name: Embedding model name (preset or HuggingFace ID)
            model_max_seq_length: Max sequence length for embedder
            model_batch_size: Batch size for embedder
        """
        self.socket_path = socket_path
        self.idle_timeout = idle_timeout
        self.model_name = model_name
        self.model_max_seq_length = model_max_seq_length
        self.model_batch_size = model_batch_size

        self.embedder: Embedder | None = None
        self.server_socket: socket.socket | None = None
        self.last_request_time = time.time()
        self.running = False
        self.requests_served = 0

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def load_model(self) -> None:
        """Load the embedding model (one-time cost)."""
        from ember.adapters.local_models.registry import create_embedder

        model_display = self.model_name or "default (jina-code-v2)"
        logger.info(f"Loading embedding model: {model_display}...")
        start = time.time()

        self.embedder = create_embedder(
            model_name=self.model_name,
            max_seq_length=self.model_max_seq_length,
            batch_size=self.model_batch_size,
        )
        # Force model loading now
        self.embedder.ensure_loaded()

        elapsed = time.time() - start
        logger.info(f"Model {self.embedder.name} loaded in {elapsed:.2f}s")

    def create_socket(self) -> None:
        """Create and bind Unix socket.

        Raises:
            RuntimeError: If socket creation fails
        """
        # Remove stale socket if it exists
        if self.socket_path.exists():
            logger.warning(f"Removing stale socket: {self.socket_path}")
            self.socket_path.unlink()

        # Create socket directory if needed
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Create Unix socket
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(str(self.socket_path))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)  # Allow periodic timeout checks

        logger.info(f"Listening on {self.socket_path}")

    def handle_request(self, request: Request) -> Response:
        """Handle a single request.

        Args:
            request: Request to handle

        Returns:
            Response with result or error
        """
        try:
            if request.method == "embed_texts":
                return self._handle_embed_texts(request)
            elif request.method == "health":
                return self._handle_health(request)
            elif request.method == "stats":
                return self._handle_stats(request)
            else:
                return Response.error(
                    code=404,
                    message=f"Unknown method: {request.method}",
                    request_id=request.id,
                )
        except Exception as e:
            logger.exception(f"Error handling request: {e}")
            return Response.error(
                code=500, message=f"Internal error: {e}", request_id=request.id
            )

    def _handle_embed_texts(self, request: Request) -> Response:
        """Handle embed_texts request."""
        if self.embedder is None:
            return Response.error(
                code=500, message="Model not loaded", request_id=request.id
            )

        texts = request.params.get("texts")
        if not texts or not isinstance(texts, list):
            return Response.error(
                code=400,
                message="Missing or invalid 'texts' parameter",
                request_id=request.id,
            )

        try:
            embeddings = self.embedder.embed_texts(texts)
            return Response.success(embeddings, request_id=request.id)
        except Exception as e:
            return Response.error(
                code=500, message=f"Embedding failed: {e}", request_id=request.id
            )

    def _handle_health(self, request: Request) -> Response:
        """Handle health check request.

        Returns status and the daemon's PID, which allows clients to recover
        the PID even if the PID file is missing (#214).
        """
        import os

        return Response.success(
            {
                "status": "ok",
                "pid": os.getpid(),
                "model": self.embedder.name if self.embedder else None,
                "dim": self.embedder.dim if self.embedder else None,
            },
            request_id=request.id,
        )

    def _handle_stats(self, request: Request) -> Response:
        """Handle stats request."""
        uptime = time.time() - (self.last_request_time - self.idle_timeout)
        return Response.success(
            {
                "uptime": uptime,
                "requests_served": self.requests_served,
                "model_loaded": self.embedder is not None,
            },
            request_id=request.id,
        )

    def handle_client(self, client_socket: socket.socket) -> None:
        """Handle a single client connection.

        Args:
            client_socket: Connected client socket
        """
        try:
            # Receive request
            request = receive_message(client_socket, Request)
            logger.debug(f"Received request: {request.method}")

            # Update activity time
            self.last_request_time = time.time()
            self.requests_served += 1

            # Handle request
            response = self.handle_request(request)

            # Send response
            send_message(client_socket, response)
            logger.debug(f"Sent response: {'error' if response.is_error() else 'success'}")

        except ProtocolError as e:
            logger.error(f"Protocol error: {e}")
            try:
                error_response = Response.error(code=400, message=str(e))
                send_message(client_socket, error_response)
            except Exception:
                pass  # Failed to send error response
        except Exception as e:
            logger.exception(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def check_idle_timeout(self) -> bool:
        """Check if idle timeout has been reached.

        Returns:
            True if should shut down due to idle timeout
        """
        if self.idle_timeout <= 0:
            return False  # Timeout disabled

        idle_time = time.time() - self.last_request_time
        if idle_time >= self.idle_timeout:
            logger.info(
                f"Idle timeout reached ({idle_time:.0f}s >= {self.idle_timeout}s)"
            )
            return True
        return False

    def serve_forever(self) -> None:
        """Main server loop.

        Handles client connections and idle timeout checking.
        """
        logger.info("Daemon server started")
        self.running = True

        while self.running:
            try:
                # Accept connection (with timeout to allow periodic checks)
                try:
                    client_socket, _ = self.server_socket.accept()
                    self.handle_client(client_socket)
                except TimeoutError:
                    # No connection, check idle timeout
                    if self.check_idle_timeout():
                        logger.info("Shutting down due to idle timeout")
                        break
                    continue

            except Exception as e:
                if self.running:
                    logger.exception(f"Error in server loop: {e}")
                    # Add backoff to prevent tight loop on persistent errors
                    time.sleep(0.1)

        logger.info("Daemon server stopped")

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.server_socket:
            self.server_socket.close()

        if self.socket_path.exists():
            self.socket_path.unlink()

        # Release model resources
        if self.embedder is not None:
            self.embedder = None
            logger.debug("Released embedder model reference")

        logger.info(f"Cleaned up socket: {self.socket_path}")

    def run(self) -> None:
        """Run the daemon server.

        This is the main entry point for the daemon process.
        """
        try:
            self.setup_signal_handlers()
            self.load_model()
            self.create_socket()
            self.serve_forever()
        except Exception as e:
            logger.exception(f"Fatal error: {e}")
            sys.exit(1)
        finally:
            self.cleanup()


def main() -> None:
    """Main entry point for daemon process.

    Can be run directly or via CLI command.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Ember embedding daemon")
    parser.add_argument(
        "--socket",
        type=Path,
        default=Path.home() / ".ember" / "daemon.sock",
        help="Unix socket path",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=900,
        help="Idle timeout in seconds (0 = never)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Embedding model preset or HuggingFace ID",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding (lower values use less GPU memory)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level",
    )
    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(Path.home() / ".ember" / "daemon.log"),
            logging.StreamHandler(),
        ],
    )

    # Create and run server
    server = DaemonServer(
        socket_path=args.socket,
        idle_timeout=args.idle_timeout,
        model_name=args.model,
        model_batch_size=args.batch_size,
    )
    server.run()


if __name__ == "__main__":
    main()
