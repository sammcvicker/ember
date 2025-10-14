"""Integration tests for JinaCodeEmbedder.

Note: These tests download the model on first run (~600MB).
Subsequent runs use cached model from ~/.cache/huggingface/
"""

import pytest

from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder


class TestJinaCodeEmbedder:
    """Test JinaCodeEmbedder implementation of Embedder protocol."""

    def test_embedder_initialization(self):
        """Test embedder can be initialized with default params."""
        embedder = JinaCodeEmbedder()
        assert embedder is not None
        # Model should not be loaded until first use
        assert embedder._model is None

    def test_embedder_properties(self):
        """Test name and dim properties."""
        embedder = JinaCodeEmbedder()
        assert embedder.name == "jinaai/jina-embeddings-v2-base-code"
        assert embedder.dim == 768

    def test_fingerprint_is_stable(self):
        """Test fingerprint is deterministic."""
        embedder1 = JinaCodeEmbedder(max_seq_length=512)
        embedder2 = JinaCodeEmbedder(max_seq_length=512)
        assert embedder1.fingerprint() == embedder2.fingerprint()

    def test_fingerprint_changes_with_config(self):
        """Test fingerprint differs when config changes."""
        embedder1 = JinaCodeEmbedder(max_seq_length=512)
        embedder2 = JinaCodeEmbedder(max_seq_length=1024)
        assert embedder1.fingerprint() != embedder2.fingerprint()

    def test_fingerprint_format(self):
        """Test fingerprint has expected format."""
        embedder = JinaCodeEmbedder()
        fp = embedder.fingerprint()
        assert fp.startswith("jinaai/jina-embeddings-v2-base-code:v2:")
        # Should have 16-char hash suffix
        parts = fp.split(":")
        assert len(parts) == 3
        assert len(parts[2]) == 16

    def test_embed_empty_list(self):
        """Test embedding empty list returns empty list."""
        embedder = JinaCodeEmbedder()
        result = embedder.embed_texts([])
        assert result == []

    @pytest.mark.slow
    def test_embed_single_text(self):
        """Test embedding a single text.

        Note: Downloads model on first run (~600MB).
        """
        embedder = JinaCodeEmbedder()
        texts = ["def hello(): return 'world'"]
        embeddings = embedder.embed_texts(texts)

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 768
        # Should be normalized (L2 norm ~1.0)
        import math

        norm = math.sqrt(sum(x * x for x in embeddings[0]))
        assert 0.99 < norm < 1.01

    @pytest.mark.slow
    def test_embed_multiple_texts(self):
        """Test embedding multiple texts in batch."""
        embedder = JinaCodeEmbedder(batch_size=2)
        texts = [
            "def add(a, b): return a + b",
            "function multiply(x, y) { return x * y; }",
            "public int subtract(int a, int b) { return a - b; }",
        ]
        embeddings = embedder.embed_texts(texts)

        assert len(embeddings) == 3
        assert all(len(emb) == 768 for emb in embeddings)

        # Different texts should have different embeddings
        assert embeddings[0] != embeddings[1]
        assert embeddings[1] != embeddings[2]

    @pytest.mark.slow
    def test_embed_code_samples(self):
        """Test embedding realistic code samples."""
        embedder = JinaCodeEmbedder()
        texts = [
            """
def fibonacci(n: int) -> int:
    '''Calculate the nth Fibonacci number.'''
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
            """.strip(),
            """
class Stack:
    '''A simple stack data structure.'''
    def __init__(self):
        self.items = []

    def push(self, item):
        self.items.append(item)

    def pop(self):
        return self.items.pop()
            """.strip(),
        ]
        embeddings = embedder.embed_texts(texts)

        assert len(embeddings) == 2
        assert all(len(emb) == 768 for emb in embeddings)

        # Similar code should have similar embeddings (cosine similarity)
        def cosine_sim(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            return dot  # Already normalized, so dot product = cosine

        similarity = cosine_sim(embeddings[0], embeddings[1])
        # Both are Python code, but different algorithms/structures
        # Similarity will be relatively low (different semantics)
        # Just verify it's positive and not identical
        assert 0.0 < similarity < 0.99

    @pytest.mark.slow
    def test_model_lazy_loads(self):
        """Test model is lazy-loaded on first embed call."""
        embedder = JinaCodeEmbedder()
        assert embedder._model is None

        embedder.embed_texts(["test"])
        assert embedder._model is not None

    @pytest.mark.slow
    def test_model_reused_across_calls(self):
        """Test model is reused across multiple embed calls."""
        embedder = JinaCodeEmbedder()

        embedder.embed_texts(["first call"])
        model1 = embedder._model

        embedder.embed_texts(["second call"])
        model2 = embedder._model

        assert model1 is model2  # Same object

    def test_custom_max_seq_length(self):
        """Test custom max sequence length is set."""
        embedder = JinaCodeEmbedder(max_seq_length=1024)
        assert embedder._max_seq_length == 1024

    def test_custom_batch_size(self):
        """Test custom batch size is set."""
        embedder = JinaCodeEmbedder(batch_size=64)
        assert embedder._batch_size == 64
