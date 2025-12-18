"""Jina Embeddings v2 adapter for code embedding.

Uses jinaai/jina-embeddings-v2-base-code via sentence-transformers.
"""

import hashlib
import logging
import warnings
from typing import TYPE_CHECKING

from ember.adapters.local_models.oom_retry import embed_with_oom_retry

logger = logging.getLogger(__name__)

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
                # Suppress the optimum warning when loading Jina model
                # (optimum is optional, provides ONNX optimization)
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=".*optimum is not installed.*",
                        category=UserWarning,
                    )

                    # Try to load from local cache first to avoid network calls
                    # This prevents timeouts when HuggingFace is slow/unreachable
                    try:
                        self._model = SentenceTransformer(
                            self.MODEL_NAME,
                            trust_remote_code=True,
                            device=self._device,
                            local_files_only=True,  # Use cached model, no network
                        )
                    except (OSError, ValueError):
                        # Model not cached yet, download from HuggingFace
                        self._model = SentenceTransformer(
                            self.MODEL_NAME,
                            trust_remote_code=True,
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

        Automatically retries with smaller batch sizes on CUDA OOM errors.

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

            def encode_with_batch_size(batch_size: int) -> list[list[float]]:
                """Inner function for OOM retry wrapper."""
                embeddings = model.encode(
                    texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True,  # L2 normalization
                )
                return [emb.tolist() for emb in embeddings]

            # Use OOM retry wrapper for automatic batch size reduction
            return embed_with_oom_retry(encode_with_batch_size, self._batch_size)

        except Exception as e:
            raise RuntimeError(f"Failed to embed {len(texts)} texts: {e}") from e
