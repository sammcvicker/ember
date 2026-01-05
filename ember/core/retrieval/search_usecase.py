"""Search use case implementing hybrid retrieval.

Orchestrates full-text search (BM25) and vector search (semantic similarity)
with Reciprocal Rank Fusion for optimal retrieval quality.
"""

import logging
from dataclasses import dataclass

from ember.domain.entities import (
    Chunk,
    Query,
    SearchExplanation,
    SearchResult,
    SearchResultSet,
)
from ember.ports.embedders import Embedder
from ember.ports.repositories import ChunkRepository
from ember.ports.search import TextSearch, VectorSearch

logger = logging.getLogger(__name__)

# =============================================================================
# Retrieval Parameters
# =============================================================================
# These parameters control the hybrid search retrieval behavior.
# They can be configured via SearchConfig for advanced tuning.

# Multiplier for retrieval pool size relative to topk.
# Larger pool = better fusion quality but slower retrieval.
# Set to 5x to ensure enough candidates for effective RRF fusion across
# both BM25 and vector results. Lower values may miss relevant results
# that rank highly in only one retrieval method.
RETRIEVAL_POOL_MULTIPLIER: int = 5

# Minimum retrieval pool size regardless of topk.
# Ensures enough candidates for fusion even with small topk values.
# 100 provides a reasonable baseline for most use cases.
MIN_RETRIEVAL_POOL: int = 100

# Reciprocal Rank Fusion constant (k parameter).
# Higher values reduce the influence of top-ranked items.
# Standard value of 60 balances top-rank importance with tail distribution.
# See: Cormack et al. "Reciprocal Rank Fusion outperforms Condorcet and
# individual Rank Learning Methods" (SIGIR 2009)
DEFAULT_RRF_K: int = 60


@dataclass
class _RetrievalResult:
    """Internal result from chunk retrieval with metadata."""

    chunks: list[Chunk]
    missing_count: int


class SearchUseCase:
    """Orchestrates hybrid search combining BM25 and vector retrieval.

    Uses Reciprocal Rank Fusion (RRF) to combine results from:
    1. Full-text search (BM25 via FTS5)
    2. Vector search (cosine similarity)

    RRF formula: score(d) = sum over all rankers of 1 / (k + rank(d))
    where k is typically 60 (balances importance of top results).
    """

    def __init__(
        self,
        text_search: TextSearch,
        vector_search: VectorSearch,
        chunk_repo: ChunkRepository,
        embedder: Embedder,
        rrf_k: int = DEFAULT_RRF_K,
        retrieval_pool_multiplier: int = RETRIEVAL_POOL_MULTIPLIER,
        min_retrieval_pool: int = MIN_RETRIEVAL_POOL,
    ) -> None:
        """Initialize search use case.

        Args:
            text_search: Full-text search adapter (FTS5).
            vector_search: Vector search adapter.
            chunk_repo: Repository for retrieving chunk metadata.
            embedder: Embedder for query vectorization.
            rrf_k: RRF constant (default 60, higher = less weight to top ranks).
            retrieval_pool_multiplier: Multiplier for pool size vs topk (default 5).
            min_retrieval_pool: Minimum retrieval pool size (default 100).
        """
        self.text_search = text_search
        self.vector_search = vector_search
        self.chunk_repo = chunk_repo
        self.embedder = embedder
        self.rrf_k = rrf_k
        self.retrieval_pool_multiplier = retrieval_pool_multiplier
        self.min_retrieval_pool = min_retrieval_pool

    def search(self, query: Query) -> SearchResultSet:
        """Execute hybrid search and return ranked results.

        Args:
            query: Search query with parameters.

        Returns:
            SearchResultSet with results and metadata about retrieval quality.
        """
        # 1. Embed query text
        query_embedding = self.embedder.embed_texts([query.text])[0]

        # 2. Get BM25 results from full-text search
        # Use a larger retrieval pool for fusion to ensure quality ranking
        # Pass path_filter to filter during SQL query (not after)
        retrieval_pool = max(
            query.topk * self.retrieval_pool_multiplier,
            self.min_retrieval_pool,
        )
        fts_results = self.text_search.query(
            query.text, topk=retrieval_pool, path_filter=query.path_filter_str
        )

        # 3. Get vector search results
        vector_results = self.vector_search.query(
            query_embedding, topk=retrieval_pool, path_filter=query.path_filter_str
        )

        # 4. Fuse results using Reciprocal Rank Fusion
        fused_scores = self._reciprocal_rank_fusion(
            [fts_results, vector_results],
            k=self.rrf_k,
        )

        # 5. Get top-k chunk IDs
        top_chunk_ids = [cid for cid, _ in fused_scores[: query.topk]]

        # 6. Retrieve full chunk objects (with metadata)
        retrieval = self._retrieve_chunks(top_chunk_ids)

        # 7. Apply language filter using domain method
        filtered_chunks = [
            c for c in retrieval.chunks if c.matches_language(query.lang_filter_str)
        ]

        # 8. Create SearchResult objects with scores
        score_map = dict(fused_scores)
        fts_score_map = dict(fts_results)
        vector_score_map = dict(vector_results)
        results = []
        for rank, chunk in enumerate(filtered_chunks[: query.topk], start=1):
            score = score_map.get(chunk.id, 0.0)

            result = SearchResult(
                chunk=chunk,
                score=score,
                rank=rank,
                preview=chunk.generate_preview(),
                explanation=SearchExplanation(
                    fused_score=score,
                    bm25_score=fts_score_map.get(chunk.id, 0.0),
                    vector_score=vector_score_map.get(chunk.id, 0.0),
                ),
            )
            results.append(result)

        # 9. Build result set with metadata
        warning = None
        if retrieval.missing_count > 0:
            warning = (
                f"Warning: {retrieval.missing_count} chunks could not be retrieved. "
                f"Index may be corrupted or stale. Run 'ember sync --force' to rebuild."
            )

        return SearchResultSet(
            results=results,
            requested_count=query.topk,
            missing_chunks=retrieval.missing_count,
            warning=warning,
        )

    def _reciprocal_rank_fusion(
        self,
        result_lists: list[list[tuple[str, float]]],
        k: int = 60,
    ) -> list[tuple[str, float]]:
        """Fuse multiple ranked result lists using Reciprocal Rank Fusion.

        Args:
            result_lists: List of result lists, each containing (id, score) tuples.
            k: RRF constant (default 60).

        Returns:
            Fused list of (chunk_id, score) tuples, sorted by score (descending).
        """
        # Accumulate RRF scores
        rrf_scores: dict[str, float] = {}

        for result_list in result_lists:
            for rank, (chunk_id, _score) in enumerate(result_list, start=1):
                # RRF formula: 1 / (k + rank)
                rrf_score = 1.0 / (k + rank)
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + rrf_score

        # Sort by combined score (descending)
        fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return fused

    def _retrieve_chunks(self, chunk_ids: list[str]) -> _RetrievalResult:
        """Retrieve chunk objects for given IDs.

        Args:
            chunk_ids: List of chunk identifiers.

        Returns:
            _RetrievalResult with chunks and count of missing chunks.
        """
        chunks = []
        missing_ids = []

        for chunk_id in chunk_ids:
            chunk = self.chunk_repo.get(chunk_id)
            if chunk:
                chunks.append(chunk)
            else:
                missing_ids.append(chunk_id)

        # Log warning if chunks are missing with recovery guidance
        if missing_ids:
            sample_ids = missing_ids[:5]  # Show first 5 for brevity
            logger.warning(
                f"Missing {len(missing_ids)} chunks during retrieval. "
                f"This may indicate index corruption or stale data. "
                f"Try running 'ember sync --force' to rebuild the index. "
                f"If the problem persists, please report an issue. "
                f"Missing IDs: {sample_ids}"
                + ("..." if len(missing_ids) > 5 else "")
            )

        return _RetrievalResult(chunks=chunks, missing_count=len(missing_ids))
