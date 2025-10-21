"""Daemon-based embedding service for instant model loading.

This package implements a persistent daemon process that keeps the embedding
model loaded in memory, providing near-instant embeddings for CLI commands.

Architecture:
- protocol.py: JSON-RPC communication protocol
- server.py: Daemon server process (keeps model loaded)
- client.py: Client adapter (implements Embedder protocol)
- lifecycle.py: Daemon lifecycle management (start/stop/status)
"""

from ember.adapters.daemon.client import DaemonEmbedderClient

__all__ = ["DaemonEmbedderClient"]
