"""Unit tests for BGESmallEmbedder (no model loading required)."""

import contextlib
import os
from unittest.mock import MagicMock, patch


class TestTokenizersParallelismEnvVar:
    """Tests for TOKENIZERS_PARALLELISM environment variable fix."""

    def test_ensure_model_loaded_sets_tokenizers_parallelism(self) -> None:
        """Test _ensure_model_loaded sets TOKENIZERS_PARALLELISM before import."""
        # Clean state - remove any existing value
        original_value = os.environ.pop("TOKENIZERS_PARALLELISM", None)
        try:
            with patch(
                "ember.adapters.local_models.bge_embedder.SentenceTransformer",
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
                from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

                embedder = BGESmallEmbedder()
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
                "ember.adapters.local_models.bge_embedder.SentenceTransformer",
                create=True,
            ) as mock_st:
                mock_st.return_value = MagicMock()

                from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

                embedder = BGESmallEmbedder()
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
    """Tests for BGESmallEmbedder configuration (no model loading)."""

    def test_default_configuration(self) -> None:
        """Test embedder uses correct default values."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder = BGESmallEmbedder()

        assert embedder._max_seq_length == 512
        assert embedder._batch_size == 32
        assert embedder._device is None
        assert embedder._model is None

    def test_custom_configuration(self) -> None:
        """Test embedder accepts custom configuration."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder = BGESmallEmbedder(
            max_seq_length=256,
            batch_size=64,
            device="cpu",
        )

        assert embedder._max_seq_length == 256
        assert embedder._batch_size == 64
        assert embedder._device == "cpu"

    def test_model_constants(self) -> None:
        """Test model constants are correct."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        assert BGESmallEmbedder.MODEL_NAME == "BAAI/bge-small-en-v1.5"
        assert BGESmallEmbedder.MODEL_DIM == 384
        assert BGESmallEmbedder.DEFAULT_MAX_SEQ_LENGTH == 512
        assert BGESmallEmbedder.DEFAULT_BATCH_SIZE == 32


class TestEmbedderProperties:
    """Tests for BGESmallEmbedder protocol properties."""

    def test_name_property(self) -> None:
        """Test name property returns model name."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder = BGESmallEmbedder()
        assert embedder.name == "BAAI/bge-small-en-v1.5"

    def test_dim_property(self) -> None:
        """Test dim property returns embedding dimension."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder = BGESmallEmbedder()
        assert embedder.dim == 384

    def test_fingerprint_format(self) -> None:
        """Test fingerprint has correct format."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder = BGESmallEmbedder()
        fingerprint = embedder.fingerprint()

        # Should be model_name:version:hash
        parts = fingerprint.split(":")
        assert len(parts) == 3
        assert parts[0] == "BAAI/bge-small-en-v1.5"
        assert parts[1] == "v1"
        assert len(parts[2]) == 16  # SHA256 truncated to 16 chars

    def test_fingerprint_changes_with_config(self) -> None:
        """Test fingerprint changes when config changes."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder1 = BGESmallEmbedder(max_seq_length=512)
        embedder2 = BGESmallEmbedder(max_seq_length=256)

        assert embedder1.fingerprint() != embedder2.fingerprint()

    def test_fingerprint_is_deterministic(self) -> None:
        """Test fingerprint is deterministic for same config."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder1 = BGESmallEmbedder()
        embedder2 = BGESmallEmbedder()

        assert embedder1.fingerprint() == embedder2.fingerprint()


class TestEmbedTextsWithMock:
    """Tests for embed_texts using mocked model."""

    def test_embed_texts_empty_list(self) -> None:
        """Test embed_texts returns empty list for empty input."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        embedder = BGESmallEmbedder()
        result = embedder.embed_texts([])
        assert result == []

    def test_embed_texts_calls_model_encode(self) -> None:
        """Test embed_texts calls model.encode with correct parameters."""
        import numpy as np

        with patch(
            "sentence_transformers.SentenceTransformer"
        ) as mock_st:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384])
            mock_st.return_value = mock_model

            from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

            embedder = BGESmallEmbedder(batch_size=16)
            embedder._model = None  # Force fresh load

            result = embedder.embed_texts(["text1", "text2"])

            mock_model.encode.assert_called_once_with(
                ["text1", "text2"],
                batch_size=16,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            assert len(result) == 2
            assert len(result[0]) == 384

    def test_embed_texts_error_handling(self) -> None:
        """Test embed_texts wraps model errors in RuntimeError."""
        import pytest

        with patch(
            "sentence_transformers.SentenceTransformer"
        ) as mock_st:
            mock_model = MagicMock()
            mock_model.encode.side_effect = Exception("Model error")
            mock_st.return_value = mock_model

            from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

            embedder = BGESmallEmbedder()
            embedder._model = None

            with pytest.raises(RuntimeError, match="Failed to embed 2 texts"):
                embedder.embed_texts(["text1", "text2"])


class TestEnsureLoaded:
    """Tests for ensure_loaded method."""

    def test_ensure_loaded_loads_model(self) -> None:
        """Test ensure_loaded triggers model loading."""
        with patch(
            "sentence_transformers.SentenceTransformer"
        ) as mock_st:
            mock_st.return_value = MagicMock()

            from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

            embedder = BGESmallEmbedder()
            embedder._model = None

            embedder.ensure_loaded()

            mock_st.assert_called()

    def test_ensure_loaded_idempotent(self) -> None:
        """Test ensure_loaded only loads model once."""
        with patch(
            "sentence_transformers.SentenceTransformer"
        ) as mock_st:
            mock_model = MagicMock()
            mock_st.return_value = mock_model

            from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

            embedder = BGESmallEmbedder()
            embedder._model = None

            embedder.ensure_loaded()
            embedder.ensure_loaded()
            embedder.ensure_loaded()

            # Should only create model once
            assert mock_st.call_count == 1


class TestModelLoading:
    """Tests for model loading behavior."""

    def test_local_files_only_tried_first(self) -> None:
        """Test that local_files_only=True is tried first."""
        with patch(
            "sentence_transformers.SentenceTransformer"
        ) as mock_st:
            mock_st.return_value = MagicMock()

            from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

            embedder = BGESmallEmbedder(device="cpu")
            embedder._model = None
            embedder._ensure_model_loaded()

            # First call should have local_files_only=True
            first_call = mock_st.call_args_list[0]
            assert first_call.kwargs.get("local_files_only") is True

    def test_fallback_to_download_on_cache_miss(self) -> None:
        """Test fallback to download when model not cached."""
        with patch(
            "sentence_transformers.SentenceTransformer"
        ) as mock_st:
            # First call raises OSError (not cached), second succeeds
            mock_st.side_effect = [OSError("Not found"), MagicMock()]

            from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

            embedder = BGESmallEmbedder()
            embedder._model = None
            embedder._ensure_model_loaded()

            # Should have been called twice
            assert mock_st.call_count == 2
            # Second call should not have local_files_only
            second_call = mock_st.call_args_list[1]
            assert "local_files_only" not in second_call.kwargs

    def test_model_load_failure_raises_runtime_error(self) -> None:
        """Test that model load failure raises RuntimeError."""
        import pytest

        with patch(
            "sentence_transformers.SentenceTransformer"
        ) as mock_st:
            mock_st.side_effect = Exception("Download failed")

            from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

            embedder = BGESmallEmbedder()
            embedder._model = None

            with pytest.raises(RuntimeError, match="Failed to load"):
                embedder._ensure_model_loaded()
