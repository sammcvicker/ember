"""Jina Embeddings v2 adapter for code embedding.

Uses jinaai/jina-embeddings-v2-base-code via sentence-transformers.
"""

import hashlib
import warnings
from typing import TYPE_CHECKING, Any

# Lazy import - only load when actually needed
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class JinaCodeEmbedder:
    """Embedder using Jina Embeddings v2 Base Code model.

    Implements the Embedder protocol for code-aware text embedding.
    Uses jinaai/jina-embeddings-v2-base-code (161M params, 768 dims).

    Features:
    - 768-dimensional embeddings
    - 8192 token context length
    - Supports 30+ programming languages
    - CPU-friendly (161M parameters)
    - Mean pooling
    """

    MODEL_NAME = "jinaai/jina-embeddings-v2-base-code"
    MODEL_DIM = 768
    DEFAULT_MAX_SEQ_LENGTH = 512  # Conservative default for chunking
    DEFAULT_BATCH_SIZE = 32

    def __init__(
        self,
        max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH,
        batch_size: int = DEFAULT_BATCH_SIZE,
        device: str | None = None,
    ):
        """Initialize the Jina Code Embedder.

        Args:
            max_seq_length: Maximum sequence length for tokenization (1-8192).
            batch_size: Batch size for encoding.
            device: Device to run on ('cpu', 'cuda', 'mps', or None for auto).
        """
        self._max_seq_length = max_seq_length
        self._batch_size = batch_size
        self._device = device
        self._model: "SentenceTransformer | None" = None

    def _ensure_model_loaded(self) -> "SentenceTransformer":
        """Lazy-load the model on first use.

        Returns:
            Loaded SentenceTransformer model.

        Raises:
            RuntimeError: If model fails to load.
        """
        if self._model is None:
            # Import here to avoid loading heavy dependencies at module import time
            from sentence_transformers import SentenceTransformer

            try:
                # Suppress the optimum warning when loading Jina model
                # (optimum is optional, provides ONNX optimization)
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=".*optimum is not installed.*",
                        category=UserWarning,
                    )
                    self._model = SentenceTransformer(
                        self.MODEL_NAME,
                        trust_remote_code=True,
                        device=self._device,
                    )
                self._model.max_seq_length = self._max_seq_length
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load {self.MODEL_NAME}: {e}"
                ) from e
        return self._model

    @property
    def name(self) -> str:
        """Model name."""
        return self.MODEL_NAME

    @property
    def dim(self) -> int:
        """Embedding dimension."""
        return self.MODEL_DIM

    def fingerprint(self) -> str:
        """Generate deterministic fingerprint for this model configuration.

        Format: {model_name}:v2:sha256({config_json})

        Returns:
            Stable fingerprint string.
        """
        # Include all config that affects embeddings
        config_parts = [
            self.MODEL_NAME,
            str(self.MODEL_DIM),
            str(self._max_seq_length),
            "mean_pooling",  # Jina v2 uses mean pooling
            "normalize",  # Jina models normalize by default
        ]
        config_str = "|".join(config_parts)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
        return f"{self.MODEL_NAME}:v2:{config_hash}"

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
        if not texts:
            return []

        try:
            model = self._ensure_model_loaded()

            # sentence-transformers handles batching internally
            # but we can specify batch_size for control
            embeddings = model.encode(
                texts,
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,  # L2 normalization
            )

            # Convert numpy arrays to lists
            return [emb.tolist() for emb in embeddings]

        except Exception as e:
            raise RuntimeError(
                f"Failed to embed {len(texts)} texts: {e}"
            ) from e
