"""Unit tests for JinaCodeEmbedder (no model loading required)."""

import contextlib
import os
from unittest.mock import MagicMock, patch


class TestTokenizersParallelismEnvVar:
    """Tests for TOKENIZERS_PARALLELISM environment variable fix (#215)."""

    def test_ensure_model_loaded_sets_tokenizers_parallelism(self) -> None:
        """Test _ensure_model_loaded sets TOKENIZERS_PARALLELISM before import."""
        # Clean state - remove any existing value
        original_value = os.environ.pop("TOKENIZERS_PARALLELISM", None)
        try:
            with patch(
                "ember.adapters.local_models.jina_embedder.SentenceTransformer",
                create=True,
            ) as mock_st:
                # Set up mock to capture env var at import time
                env_at_import_time = {}

                def capture_env(*args, **kwargs):
                    env_at_import_time["TOKENIZERS_PARALLELISM"] = os.environ.get(
                        "TOKENIZERS_PARALLELISM"
                    )
                    return MagicMock()

                mock_st.side_effect = capture_env

                # Import after patching
                from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

                embedder = JinaCodeEmbedder()
                embedder._model = None  # Force re-initialization

                # Trigger model loading (this will call our mock)
                with contextlib.suppress(Exception):
                    embedder._ensure_model_loaded()

                # Verify env var was set before import
                assert os.environ.get("TOKENIZERS_PARALLELISM") == "false"
        finally:
            # Restore original value
            if original_value is not None:
                os.environ["TOKENIZERS_PARALLELISM"] = original_value
            else:
                os.environ.pop("TOKENIZERS_PARALLELISM", None)

    def test_ensure_model_loaded_does_not_override_user_setting(self) -> None:
        """Test _ensure_model_loaded doesn't override user's TOKENIZERS_PARALLELISM."""
        original_value = os.environ.get("TOKENIZERS_PARALLELISM")
        try:
            # User has explicitly set TOKENIZERS_PARALLELISM=true
            os.environ["TOKENIZERS_PARALLELISM"] = "true"

            with patch(
                "ember.adapters.local_models.jina_embedder.SentenceTransformer",
                create=True,
            ) as mock_st:
                mock_st.return_value = MagicMock()

                from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

                embedder = JinaCodeEmbedder()
                embedder._model = None  # Force re-initialization

                with contextlib.suppress(Exception):
                    embedder._ensure_model_loaded()

                # Verify user's setting is preserved (setdefault doesn't override)
                assert os.environ.get("TOKENIZERS_PARALLELISM") == "true"
        finally:
            # Restore original value
            if original_value is not None:
                os.environ["TOKENIZERS_PARALLELISM"] = original_value
            else:
                os.environ.pop("TOKENIZERS_PARALLELISM", None)


class TestEmbedderConfiguration:
    """Tests for JinaCodeEmbedder configuration (no model loading)."""

    def test_default_configuration(self) -> None:
        """Test embedder uses correct default values."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        embedder = JinaCodeEmbedder()

        assert embedder._max_seq_length == 512
        assert embedder._batch_size == 32
        assert embedder._device is None
        assert embedder._model is None

    def test_custom_configuration(self) -> None:
        """Test embedder accepts custom configuration."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        embedder = JinaCodeEmbedder(
            max_seq_length=1024,
            batch_size=64,
            device="cpu",
        )

        assert embedder._max_seq_length == 1024
        assert embedder._batch_size == 64
        assert embedder._device == "cpu"
