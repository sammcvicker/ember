"""Search use case implementing hybrid retrieval.

Orchestrates full-text search (BM25) and vector search (semantic similarity)
with Reciprocal Rank Fusion for optimal retrieval quality.
"""

from ember.domain.entities import Chunk, Query, SearchResult
from ember.ports.embedders import Embedder
from ember.ports.repositories import ChunkRepository
from ember.ports.search import TextSearch, VectorSearch


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
        rrf_k: int = 60,
    ) -> None:
        """Initialize search use case.

        Args:
            text_search: Full-text search adapter (FTS5).
            vector_search: Vector search adapter.
            chunk_repo: Repository for retrieving chunk metadata.
            embedder: Embedder for query vectorization.
            rrf_k: RRF constant (default 60, higher = less weight to top ranks).
        """
        self.text_search = text_search
        self.vector_search = vector_search
        self.chunk_repo = chunk_repo
        self.embedder = embedder
        self.rrf_k = rrf_k

    def search(self, query: Query) -> list[SearchResult]:
        """Execute hybrid search and return ranked results.

        Args:
            query: Search query with parameters.

        Returns:
            List of SearchResult objects, ranked by relevance.
        """
        # 1. Embed query text
        query_embedding = self.embedder.embed_texts([query.text])[0]

        # 2. Get BM25 results from full-text search
        # Use a larger retrieval pool for fusion (e.g., 100)
        retrieval_pool = max(query.topk * 5, 100)
        fts_results = self.text_search.query(query.text, topk=retrieval_pool)

        # 3. Get vector search results
        vector_results = self.vector_search.query(query_embedding, topk=retrieval_pool)

        # 4. Fuse results using Reciprocal Rank Fusion
        fused_scores = self._reciprocal_rank_fusion(
            [fts_results, vector_results],
            k=self.rrf_k,
        )

        # 5. Get top-k chunk IDs
        top_chunk_ids = [cid for cid, _ in fused_scores[: query.topk]]

        # 6. Retrieve full chunk objects
        chunks = self._retrieve_chunks(top_chunk_ids)

        # 7. Apply filters if specified
        filtered_chunks = self._apply_filters(
            chunks,
            path_filter=query.path_filter,
            lang_filter=query.lang_filter,
        )

        # 8. Create SearchResult objects with scores
        score_map = dict(fused_scores)
        results = []
        for rank, chunk in enumerate(filtered_chunks[: query.topk], start=1):
            score = score_map.get(chunk.id, 0.0)

            # Get individual scores for explanation
            fts_score = self._get_score(fts_results, chunk.id)
            vector_score = self._get_score(vector_results, chunk.id)

            result = SearchResult(
                chunk=chunk,
                score=score,
                rank=rank,
                preview=self._generate_preview(chunk),
                explanation={
                    "fused_score": score,
                    "bm25_score": fts_score,
                    "vector_score": vector_score,
                },
            )
            results.append(result)

        return results

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

    def _retrieve_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        """Retrieve chunk objects for given IDs.

        Args:
            chunk_ids: List of chunk identifiers.

        Returns:
            List of Chunk objects in the same order as chunk_ids.
        """
        chunks = []
        for chunk_id in chunk_ids:
            chunk = self.chunk_repo.get(chunk_id)
            if chunk:
                chunks.append(chunk)
        return chunks

    def _apply_filters(
        self,
        chunks: list[Chunk],
        path_filter: str | None,
        lang_filter: str | None,
    ) -> list[Chunk]:
        """Apply path and language filters to chunks.

        Args:
            chunks: List of chunks to filter.
            path_filter: Optional glob pattern for file paths.
            lang_filter: Optional language code filter.

        Returns:
            Filtered list of chunks.
        """
        import fnmatch

        filtered = chunks

        if path_filter:
            filtered = [
                c for c in filtered if fnmatch.fnmatch(str(c.path), path_filter)
            ]

        if lang_filter:
            filtered = [c for c in filtered if c.lang == lang_filter]

        return filtered

    def _get_score(
        self, result_list: list[tuple[str, float]], chunk_id: str
    ) -> float:
        """Get score for a chunk_id from a result list.

        Args:
            result_list: List of (chunk_id, score) tuples.
            chunk_id: The chunk identifier.

        Returns:
            Score if found, 0.0 otherwise.
        """
        for cid, score in result_list:
            if cid == chunk_id:
                return score
        return 0.0

    def _generate_preview(self, chunk: Chunk, max_lines: int = 3) -> str:
        """Generate a preview of chunk content.

        Args:
            chunk: The chunk to preview.
            max_lines: Maximum number of lines to include.

        Returns:
            Preview string.
        """
        lines = chunk.content.split("\n")
        preview_lines = lines[:max_lines]
        if len(lines) > max_lines:
            preview_lines.append("...")
        return "\n".join(preview_lines)
