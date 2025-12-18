"""MiniLM embedder adapter for lightweight embedding.

Uses sentence-transformers/all-MiniLM-L6-v2 via sentence-transformers.
Designed for resource-constrained systems (~100MB RAM, 22M params).
"""

import hashlib
from typing import TYPE_CHECKING

# Lazy import - only load when actually needed
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class MiniLMEmbedder:
    """Embedder using all-MiniLM-L6-v2 model.

    Implements the Embedder protocol for lightweight text embedding.
    Uses sentence-transformers/all-MiniLM-L6-v2 (22M params, 384 dims).

    Features:
    - 384-dimensional embeddings
    - 256 token context length
    - Very fast inference (~5x faster than larger models)
    - Minimal memory footprint (~100MB)
    - General-purpose text embeddings (not code-specific)
    """

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    MODEL_DIM = 384
    DEFAULT_MAX_SEQ_LENGTH = 256  # MiniLM has shorter context
    DEFAULT_BATCH_SIZE = 32

    def __init__(
        self,
        max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH,
        batch_size: int = DEFAULT_BATCH_SIZE,
        device: str | None = None,
    ):
        """Initialize the MiniLM Embedder.

        Args:
            max_seq_length: Maximum sequence length for tokenization (1-256).
            batch_size: Batch size for encoding.
            device: Device to run on ('cpu', 'cuda', 'mps', or None for auto).
        """
        self._max_seq_length = max_seq_length
        self._batch_size = batch_size
        self._device = device
        self._model: SentenceTransformer | None = None

    def _ensure_model_loaded(self) -> "SentenceTransformer":
        """Lazy-load the model on first use.

        Returns:
            Loaded SentenceTransformer model.

        Raises:
            RuntimeError: If model fails to load.
        """
        if self._model is None:
            # Disable tokenizers parallelism before import to prevent fork warning
            # when daemon spawns a subprocess. The warning occurs because tokenizers
            # initializes thread pools which don't survive fork() properly.
            # Using setdefault allows users to override if needed.
            import os

            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

            # Import here to avoid loading heavy dependencies at module import time
            from sentence_transformers import SentenceTransformer

            try:
                # Try to load from local cache first to avoid network calls
                # This prevents timeouts when HuggingFace is slow/unreachable
                try:
                    self._model = SentenceTransformer(
                        self.MODEL_NAME,
                        device=self._device,
                        local_files_only=True,  # Use cached model, no network
                    )
                except (OSError, ValueError):
                    # Model not cached yet, download from HuggingFace
                    self._model = SentenceTransformer(
                        self.MODEL_NAME,
                        device=self._device,
                    )

                self._model.max_seq_length = self._max_seq_length
            except Exception as e:
                raise RuntimeError(f"Failed to load {self.MODEL_NAME}: {e}") from e
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

        Format: {model_name}:v1:sha256({config_json})

        Returns:
            Stable fingerprint string.
        """
        # Include all config that affects embeddings
        config_parts = [
            self.MODEL_NAME,
            str(self.MODEL_DIM),
            str(self._max_seq_length),
            "mean_pooling",  # MiniLM uses mean pooling
            "normalize",  # Normalized embeddings
        ]
        config_str = "|".join(config_parts)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
        return f"{self.MODEL_NAME}:v1:{config_hash}"

    def ensure_loaded(self) -> None:
        """Ensure the model is loaded into memory.

        This method can be called proactively to load the model before
        the first embedding call, making the first embedding faster.
        If the model is already loaded, this is a no-op.

        Useful for showing explicit loading progress to users.
        """
        self._ensure_model_loaded()

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
            raise RuntimeError(f"Failed to embed {len(texts)} texts: {e}") from e
