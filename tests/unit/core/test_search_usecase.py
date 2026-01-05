"""Unit tests for SearchUseCase retrieval parameter configuration."""

from unittest.mock import MagicMock

import pytest

from ember.core.retrieval.search_usecase import (
    DEFAULT_RRF_K,
    MIN_RETRIEVAL_POOL,
    RETRIEVAL_POOL_MULTIPLIER,
    SearchUseCase,
)
from ember.domain.entities import Query


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for SearchUseCase."""
    text_search = MagicMock()
    vector_search = MagicMock()
    chunk_repo = MagicMock()
    embedder = MagicMock()

    # Configure embedder to return a dummy embedding
    embedder.embed_texts.return_value = [[0.1, 0.2, 0.3]]

    # Configure searches to return empty results
    text_search.query.return_value = []
    vector_search.query.return_value = []

    return {
        "text_search": text_search,
        "vector_search": vector_search,
        "chunk_repo": chunk_repo,
        "embedder": embedder,
    }


class TestSearchUseCaseModuleConstants:
    """Tests for module-level constants documentation."""

    def test_retrieval_pool_multiplier_default(self):
        """Verify RETRIEVAL_POOL_MULTIPLIER has expected default value."""
        assert RETRIEVAL_POOL_MULTIPLIER == 5

    def test_min_retrieval_pool_default(self):
        """Verify MIN_RETRIEVAL_POOL has expected default value."""
        assert MIN_RETRIEVAL_POOL == 100

    def test_default_rrf_k(self):
        """Verify DEFAULT_RRF_K has expected default value."""
        assert DEFAULT_RRF_K == 60


class TestSearchUseCaseInitialization:
    """Tests for SearchUseCase constructor with configurable parameters."""

    def test_default_parameters(self, mock_dependencies):
        """Test SearchUseCase uses module constants as defaults."""
        use_case = SearchUseCase(**mock_dependencies)

        assert use_case.rrf_k == DEFAULT_RRF_K
        assert use_case.retrieval_pool_multiplier == RETRIEVAL_POOL_MULTIPLIER
        assert use_case.min_retrieval_pool == MIN_RETRIEVAL_POOL

    def test_custom_rrf_k(self, mock_dependencies):
        """Test SearchUseCase accepts custom rrf_k."""
        use_case = SearchUseCase(**mock_dependencies, rrf_k=30)

        assert use_case.rrf_k == 30

    def test_custom_retrieval_pool_multiplier(self, mock_dependencies):
        """Test SearchUseCase accepts custom retrieval_pool_multiplier."""
        use_case = SearchUseCase(**mock_dependencies, retrieval_pool_multiplier=10)

        assert use_case.retrieval_pool_multiplier == 10

    def test_custom_min_retrieval_pool(self, mock_dependencies):
        """Test SearchUseCase accepts custom min_retrieval_pool."""
        use_case = SearchUseCase(**mock_dependencies, min_retrieval_pool=200)

        assert use_case.min_retrieval_pool == 200

    def test_all_custom_parameters(self, mock_dependencies):
        """Test SearchUseCase with all custom retrieval parameters."""
        use_case = SearchUseCase(
            **mock_dependencies,
            rrf_k=30,
            retrieval_pool_multiplier=10,
            min_retrieval_pool=50,
        )

        assert use_case.rrf_k == 30
        assert use_case.retrieval_pool_multiplier == 10
        assert use_case.min_retrieval_pool == 50


class TestRetrievalPoolCalculation:
    """Tests for retrieval pool size calculation during search."""

    def test_retrieval_pool_uses_multiplier(self, mock_dependencies):
        """Test that retrieval pool uses configured multiplier."""
        use_case = SearchUseCase(
            **mock_dependencies, retrieval_pool_multiplier=3, min_retrieval_pool=10
        )
        query = Query(text="test query", topk=50)

        use_case.search(query)

        # Expected pool: max(50 * 3, 10) = 150
        mock_dependencies["text_search"].query.assert_called_once()
        call_args = mock_dependencies["text_search"].query.call_args
        assert call_args.kwargs["topk"] == 150

    def test_retrieval_pool_respects_minimum(self, mock_dependencies):
        """Test that retrieval pool respects minimum when multiplier is too small."""
        use_case = SearchUseCase(
            **mock_dependencies, retrieval_pool_multiplier=2, min_retrieval_pool=100
        )
        query = Query(text="test query", topk=10)

        use_case.search(query)

        # Expected pool: max(10 * 2, 100) = 100 (min wins)
        mock_dependencies["text_search"].query.assert_called_once()
        call_args = mock_dependencies["text_search"].query.call_args
        assert call_args.kwargs["topk"] == 100

    def test_retrieval_pool_with_default_params(self, mock_dependencies):
        """Test retrieval pool calculation with default parameters."""
        use_case = SearchUseCase(**mock_dependencies)
        query = Query(text="test query", topk=5)

        use_case.search(query)

        # Expected pool: max(5 * 5, 100) = 100 (min wins)
        call_args = mock_dependencies["text_search"].query.call_args
        assert call_args.kwargs["topk"] == 100

    def test_retrieval_pool_large_topk(self, mock_dependencies):
        """Test retrieval pool with large topk where multiplier wins."""
        use_case = SearchUseCase(**mock_dependencies)
        query = Query(text="test query", topk=30)

        use_case.search(query)

        # Expected pool: max(30 * 5, 100) = 150 (multiplier wins)
        call_args = mock_dependencies["text_search"].query.call_args
        assert call_args.kwargs["topk"] == 150


class TestRRFFusionWithCustomK:
    """Tests for RRF fusion with different k values."""

    def test_rrf_uses_configured_k(self, mock_dependencies):
        """Test that RRF fusion uses the configured k value."""
        use_case = SearchUseCase(**mock_dependencies, rrf_k=30)

        # Create test result lists
        list1 = [("A", 1.0), ("B", 0.5)]
        list2 = [("B", 1.0), ("A", 0.5)]

        fused = use_case._reciprocal_rank_fusion([list1, list2], k=use_case.rrf_k)

        # With k=30:
        # A: 1/(30+1) + 1/(30+2) ≈ 0.0323 + 0.0313 = 0.0636
        # B: 1/(30+2) + 1/(30+1) ≈ 0.0313 + 0.0323 = 0.0636
        scores = dict(fused)
        assert abs(scores["A"] - scores["B"]) < 0.001

    def test_rrf_higher_k_reduces_top_rank_influence(self, mock_dependencies):
        """Test that higher k values reduce influence of top-ranked items."""
        use_case_low_k = SearchUseCase(**mock_dependencies, rrf_k=10)
        use_case_high_k = SearchUseCase(**mock_dependencies, rrf_k=100)

        # A is ranked 1st in one list, B is ranked 10th
        list1 = [(f"item_{i}", 1.0) for i in range(10)]  # A=item_0 ranked 1st
        list1[0] = ("A", 1.0)
        list1[9] = ("B", 0.1)

        fused_low_k = use_case_low_k._reciprocal_rank_fusion([list1], k=10)
        fused_high_k = use_case_high_k._reciprocal_rank_fusion([list1], k=100)

        scores_low_k = dict(fused_low_k)
        scores_high_k = dict(fused_high_k)

        # Ratio of A to B score should be smaller with higher k
        # (because higher k diminishes the advantage of top ranks)
        ratio_low_k = scores_low_k["A"] / scores_low_k["B"]
        ratio_high_k = scores_high_k["A"] / scores_high_k["B"]

        assert ratio_low_k > ratio_high_k
