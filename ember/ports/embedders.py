"""Embedder port interface for text embedding models.

Defines abstract interface for embedding text into vector representations.
"""

from typing import Protocol


class Embedder(Protocol):
    """Protocol for text embedding models."""

    @property
    def name(self) -> str:
        """Model name (e.g., 'bge-small-en-v1.5')."""
        ...

    @property
    def dim(self) -> int:
        """Embedding dimension (e.g., 384, 768)."""
        ...

    def fingerprint(self) -> str:
        """Unique fingerprint identifying model + config.

        Format: {name}:{version}:{config_hash}
        Used to detect index incompatibility.

        Returns:
            Stable fingerprint string.
        """
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (one per input text).
            Each vector is a list of floats of length self.dim.

        Raises:
            RuntimeError: If model fails to load or embed.
        """
        ...
