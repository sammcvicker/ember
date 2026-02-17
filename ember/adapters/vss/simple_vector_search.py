"""Simple vector search adapter using brute-force cosine similarity.

This is a fallback implementation that streams vectors in batches and uses a
min-heap to keep only the top-K results in memory. For production workloads,
prefer sqlite-vec which provides efficient approximate nearest neighbor search.
"""

import heapq
import logging
import struct
from pathlib import Path

from ember.adapters.sqlite.base_repository import SQLiteBaseRepository

logger = logging.getLogger(__name__)

# Number of rows to fetch per batch from the database cursor.
# This bounds peak memory usage: at most BATCH_SIZE vectors are held
# in memory at any time (plus the top-K heap).
BATCH_SIZE: int = 1000

# Log a warning when the corpus exceeds this many vectors, recommending
# that the user install sqlite-vec for better performance.
_LARGE_CORPUS_THRESHOLD: int = 10_000


class SimpleVectorSearch(SQLiteBaseRepository):
    """Simple brute-force vector search using cosine similarity.

    This adapter streams vectors from the database in batches and maintains
    a bounded min-heap of size topk, so memory usage is O(topk + BATCH_SIZE)
    regardless of corpus size.

    For larger datasets, consider using sqlite-vec which provides efficient
    approximate nearest neighbor search with O(1) memory per query.

    Inherits from SQLiteBaseRepository to get:
    - Thread-safe connection initialization
    - Context manager protocol (__enter__/__exit__)
    - Connection reuse across queries
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize simple vector search adapter.

        Args:
            db_path: Path to SQLite database file.
        """
        super().__init__(db_path)
        self._warned_large_corpus: bool = False

    def _decode_vector(self, blob: bytes, dim: int) -> list[float]:
        """Decode a vector from binary BLOB.

        Args:
            blob: Binary BLOB data.
            dim: Expected vector dimension.

        Returns:
            List of floats.
        """
        return list(struct.unpack(f"{dim}d", blob))

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Assumes vectors are already L2 normalized (as from Jina embedder).
        If normalized, cosine similarity = dot product.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            Cosine similarity in range [-1, 1] (higher = more similar).
        """
        # Since vectors from Jina are L2 normalized, cosine similarity = dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        return dot_product

    def add(self, chunk_id: str, vector: list[float]) -> None:
        """Add a vector to the index.

        This is a no-op because vectors are managed by VectorRepository.
        The VectorSearch adapter only reads from the vectors table.

        Args:
            chunk_id: Unique identifier for the chunk (unused).
            vector: Embedding vector (unused).
        """
        # No-op: vectors are managed by VectorRepository
        pass

    def query(
        self,
        vector: list[float],
        topk: int = 100,
    ) -> list[tuple[str, float]]:
        """Query for nearest neighbors using brute-force cosine similarity.

        Streams vectors from the database in batches of BATCH_SIZE and
        maintains a min-heap of size topk, so only the top-K best results
        are kept in memory at any time.

        Args:
            vector: Query embedding vector.
            topk: Maximum number of results to return.

        Returns:
            List of (chunk_id, similarity) tuples, sorted by similarity (descending).
            Similarity is cosine similarity in range [-1, 1].
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Execute query but do not fetch all rows
        cursor.execute(
            """
            SELECT
                c.chunk_id,
                v.embedding,
                v.dim
            FROM vectors v
            JOIN chunks c ON v.chunk_id = c.id
            """
        )

        # Use a min-heap of size topk to keep only the best results.
        # heapq is a min-heap, so we push (similarity, chunk_id) and the
        # smallest similarity sits at the top. When the heap is full, we
        # only push if the new similarity exceeds the current minimum.
        heap: list[tuple[float, str]] = []
        rows_processed = 0

        while True:
            batch = cursor.fetchmany(BATCH_SIZE)
            if not batch:
                break

            for row in batch:
                chunk_id = row[0]
                embedding_blob = row[1]
                dim = row[2]

                chunk_vector = self._decode_vector(embedding_blob, dim)
                similarity = self._cosine_similarity(vector, chunk_vector)

                if len(heap) < topk:
                    heapq.heappush(heap, (similarity, chunk_id))
                elif similarity > heap[0][0]:
                    heapq.heapreplace(heap, (similarity, chunk_id))

                rows_processed += 1

        # Warn once if the corpus is large and the user should consider sqlite-vec
        if rows_processed > _LARGE_CORPUS_THRESHOLD and not self._warned_large_corpus:
            self._warned_large_corpus = True
            logger.warning(
                "SimpleVectorSearch scanned %d vectors using brute-force search. "
                "For better performance, install sqlite-vec: pip install sqlite-vec",
                rows_processed,
            )

        # Extract results from the heap, sorted by similarity descending
        results = [(chunk_id, sim) for sim, chunk_id in heap]
        results.sort(key=lambda x: x[1], reverse=True)
        return results
