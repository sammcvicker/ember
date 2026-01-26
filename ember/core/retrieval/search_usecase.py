"""Search use case implementing hybrid retrieval.

Orchestrates full-text search (BM25) and vector search (semantic similarity)
with Reciprocal Rank Fusion for optimal retrieval quality.
"""

import logging
from dataclasses import dataclass
from typing import Self

from ember.core.use_case_errors import format_error_message, log_use_case_error
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


@dataclass
class SearchRequest:
    """Request to search the code index.

    Follows the standard use case Request DTO pattern with simple types.

    Attributes:
        query_text: The search query string.
        topk: Maximum number of results to return. Default 20.
        path_filter: Optional glob pattern to filter by file path (e.g., "*.py").
        lang_filter: Optional language filter (e.g., "python").
    """

    query_text: str
    topk: int = 20
    path_filter: str | None = None
    lang_filter: str | None = None


@dataclass
class SearchResponse:
    """Response from search operation.

    Follows the standard use case Response DTO pattern with success/error fields.

    Attributes:
        result_set: The SearchResultSet containing results (None on error).
        success: Whether the search succeeded.
        error: Error message if search failed.
    """

    result_set: SearchResultSet | None = None
    success: bool = True
    error: str | None = None

    @property
    def results(self) -> list[SearchResult]:
        """Get the list of search results.

        Returns:
            List of SearchResult objects, or empty list if no results or error.
        """
        if self.result_set is None:
            return []
        return self.result_set.results

    @classmethod
    def create_success(cls, *, result_set: SearchResultSet) -> "SearchResponse":
        """Create a success response with results.

        Args:
            result_set: The SearchResultSet containing results.

        Returns:
            SearchResponse with success=True.
        """
        return cls(
            result_set=result_set,
            success=True,
            error=None,
        )

    @classmethod
    def create_error(cls, message: str) -> "SearchResponse":
        """Create an error response.

        Args:
            message: Error message describing what went wrong.

        Returns:
            SearchResponse with success=False.
        """
        return cls(
            result_set=None,
            success=False,
            error=message,
        )


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

    def close(self) -> None:
        """Close all repository connections.

        This method ensures deterministic cleanup of database connections.
        It's safe to call multiple times - each call will attempt to close
        the underlying connections.

        Dependencies without a close() method are silently skipped.
        """
        for dep_name in ("text_search", "vector_search", "chunk_repo"):
            dep = getattr(self, dep_name, None)
            if dep is not None and hasattr(dep, "close"):
                dep.close()

    def __enter__(self) -> Self:
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Exit context manager, closing all repository connections."""
        self.close()
        return False

    def execute(self, request: SearchRequest) -> SearchResponse:
        """Execute hybrid search and return ranked results.

        Follows the standard use case API pattern with Request/Response DTOs
        and proper error handling.

        Error handling contract:
            - KeyboardInterrupt/SystemExit are re-raised (user wants to exit)
            - All other exceptions are caught and converted to error responses
            - See ember.core.use_case_errors for the error handling pattern

        Args:
            request: SearchRequest with query parameters.

        Returns:
            SearchResponse with results or error information.
        """
        # Validate query text
        query_text = request.query_text.strip()
        if not query_text:
            return SearchResponse.create_error("Query text cannot be empty")

        try:
            # Convert request to domain Query entity
            query = Query.from_strings(
                text=query_text,
                topk=request.topk,
                path_filter=request.path_filter,
                lang_filter=request.lang_filter,
            )

            # Delegate to internal search implementation
            result_set = self.search(query)
            return SearchResponse.create_success(result_set=result_set)

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            log_use_case_error(e, "search")
            return SearchResponse.create_error(format_error_message(e, "search"))

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
