"""Unit tests for embedder CUDA OOM retry logic."""

import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestOOMRetryLogic:
    """Tests for OOM retry with automatic batch size reduction."""

    def test_successful_embed_no_retry(self) -> None:
        """Test embedding succeeds on first try with no OOM."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        with patch(
            "ember.adapters.local_models.jina_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            # Mock model that succeeds immediately
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1] * 768, [0.2] * 768])
            mock_st.return_value = mock_model

            embedder = JinaCodeEmbedder(batch_size=32)
            embedder._model = mock_model

            result = embedder.embed_texts(["text1", "text2"])

            assert len(result) == 2
            # Should only call encode once
            assert mock_model.encode.call_count == 1
            # Should use original batch size
            call_args = mock_model.encode.call_args
            assert call_args.kwargs.get("batch_size") == 32

    def test_oom_triggers_batch_size_reduction(self) -> None:
        """Test CUDA OOM triggers automatic batch size halving."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        with patch(
            "ember.adapters.local_models.jina_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            # First call fails with OOM, second succeeds
            oom_error = RuntimeError("CUDA out of memory")
            mock_model.encode.side_effect = [
                oom_error,  # First attempt fails
                np.array([[0.1] * 768, [0.2] * 768]),  # Second attempt succeeds
            ]
            mock_st.return_value = mock_model

            embedder = JinaCodeEmbedder(batch_size=32)
            embedder._model = mock_model

            # Patch torch.cuda.empty_cache
            with patch("torch.cuda.empty_cache"):
                result = embedder.embed_texts(["text1", "text2"])

            assert len(result) == 2
            # Should have called encode twice
            assert mock_model.encode.call_count == 2
            # Second call should have reduced batch size
            second_call_args = mock_model.encode.call_args_list[1]
            assert second_call_args.kwargs.get("batch_size") == 16

    def test_multiple_oom_retries_halve_batch_each_time(self) -> None:
        """Test multiple OOM errors keep halving batch size."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        with patch(
            "ember.adapters.local_models.jina_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            # Multiple OOM failures before success
            oom_error = RuntimeError("CUDA out of memory")
            mock_model.encode.side_effect = [
                oom_error,  # 32 -> 16
                oom_error,  # 16 -> 8
                np.array([[0.1] * 768, [0.2] * 768]),  # Success at batch_size=8
            ]
            mock_st.return_value = mock_model

            embedder = JinaCodeEmbedder(batch_size=32)
            embedder._model = mock_model

            with patch("torch.cuda.empty_cache"):
                result = embedder.embed_texts(["text1", "text2"])

            assert len(result) == 2
            # Should have called encode 3 times
            assert mock_model.encode.call_count == 3
            # Final call should have batch_size=8
            final_call_args = mock_model.encode.call_args_list[2]
            assert final_call_args.kwargs.get("batch_size") == 8

    def test_oom_at_batch_size_one_raises_error(self) -> None:
        """Test OOM at batch_size=1 raises RuntimeError."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        with patch(
            "ember.adapters.local_models.jina_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            # Always fail with OOM
            oom_error = RuntimeError("CUDA out of memory")
            mock_model.encode.side_effect = oom_error
            mock_st.return_value = mock_model

            embedder = JinaCodeEmbedder(batch_size=1)
            embedder._model = mock_model

            with (
                patch("torch.cuda.empty_cache"),
                pytest.raises(RuntimeError, match="CUDA out of memory"),
            ):
                embedder.embed_texts(["text1", "text2"])

    def test_non_oom_error_propagates_immediately(self) -> None:
        """Test non-OOM errors are raised without retry."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        with patch(
            "ember.adapters.local_models.jina_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            # Non-OOM error
            mock_model.encode.side_effect = ValueError("Some other error")
            mock_st.return_value = mock_model

            embedder = JinaCodeEmbedder(batch_size=32)
            embedder._model = mock_model

            with pytest.raises(RuntimeError, match="Some other error"):
                embedder.embed_texts(["text1", "text2"])

            # Should only call encode once (no retry for non-OOM)
            assert mock_model.encode.call_count == 1

    def test_oom_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test OOM retry logs helpful message."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        with patch(
            "ember.adapters.local_models.jina_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            oom_error = RuntimeError("CUDA out of memory")
            mock_model.encode.side_effect = [
                oom_error,
                np.array([[0.1] * 768, [0.2] * 768]),
            ]
            mock_st.return_value = mock_model

            embedder = JinaCodeEmbedder(batch_size=32)
            embedder._model = mock_model

            with patch("torch.cuda.empty_cache"), caplog.at_level(logging.WARNING):
                embedder.embed_texts(["text1", "text2"])

            # Check log message
            assert any("CUDA out of memory" in record.message for record in caplog.records)
            assert any("batch size" in record.message.lower() for record in caplog.records)

    def test_empty_cache_called_on_oom(self) -> None:
        """Test torch.cuda.empty_cache is called on OOM."""
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        with patch(
            "ember.adapters.local_models.jina_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            oom_error = RuntimeError("CUDA out of memory")
            mock_model.encode.side_effect = [
                oom_error,
                np.array([[0.1] * 768, [0.2] * 768]),
            ]
            mock_st.return_value = mock_model

            embedder = JinaCodeEmbedder(batch_size=32)
            embedder._model = mock_model

            with patch("torch.cuda.empty_cache") as mock_empty_cache:
                embedder.embed_texts(["text1", "text2"])
                mock_empty_cache.assert_called_once()


class TestMiniLMOOMRetry:
    """Tests for OOM retry in MiniLM embedder."""

    def test_oom_triggers_batch_size_reduction(self) -> None:
        """Test CUDA OOM triggers automatic batch size halving for MiniLM."""
        from ember.adapters.local_models.minilm_embedder import MiniLMEmbedder

        with patch(
            "ember.adapters.local_models.minilm_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            oom_error = RuntimeError("CUDA out of memory")
            mock_model.encode.side_effect = [
                oom_error,
                np.array([[0.1] * 384, [0.2] * 384]),
            ]
            mock_st.return_value = mock_model

            embedder = MiniLMEmbedder(batch_size=32)
            embedder._model = mock_model

            with patch("torch.cuda.empty_cache"):
                result = embedder.embed_texts(["text1", "text2"])

            assert len(result) == 2
            assert mock_model.encode.call_count == 2
            second_call_args = mock_model.encode.call_args_list[1]
            assert second_call_args.kwargs.get("batch_size") == 16


class TestBGEOOMRetry:
    """Tests for OOM retry in BGE embedder."""

    def test_oom_triggers_batch_size_reduction(self) -> None:
        """Test CUDA OOM triggers automatic batch size halving for BGE."""
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        with patch(
            "ember.adapters.local_models.bge_embedder.SentenceTransformer",
            create=True,
        ) as mock_st:
            mock_model = MagicMock()

            oom_error = RuntimeError("CUDA out of memory")
            mock_model.encode.side_effect = [
                oom_error,
                np.array([[0.1] * 384, [0.2] * 384]),
            ]
            mock_st.return_value = mock_model

            embedder = BGESmallEmbedder(batch_size=32)
            embedder._model = mock_model

            with patch("torch.cuda.empty_cache"):
                result = embedder.embed_texts(["text1", "text2"])

            assert len(result) == 2
            assert mock_model.encode.call_count == 2
            second_call_args = mock_model.encode.call_args_list[1]
            assert second_call_args.kwargs.get("batch_size") == 16
