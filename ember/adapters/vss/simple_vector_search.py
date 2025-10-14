"""Simple vector search adapter using brute-force cosine similarity.

This is an MVP implementation that loads all vectors and computes similarity in memory.
For production, consider migrating to FAISS or sqlite-vss for better performance.
"""

import sqlite3
import struct
from pathlib import Path

from ember.domain.entities import Chunk


class SimpleVectorSearch:
    """Simple brute-force vector search using cosine similarity.

    This adapter loads all vectors from the database and computes cosine
    similarity in memory. It's suitable for MVP with <100k chunks.

    For larger datasets, consider:
    - FAISS (Facebook AI Similarity Search)
    - sqlite-vss (SQLite vector search extension)
    - Approximate Nearest Neighbor (ANN) indexes
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize simple vector search adapter.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection.

        Returns:
            SQLite connection object.
        """
        return sqlite3.connect(self.db_path)

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
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
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

        Args:
            vector: Query embedding vector.
            topk: Maximum number of results to return.

        Returns:
            List of (chunk_id, similarity) tuples, sorted by similarity (descending).
            Similarity is cosine similarity in range [-1, 1].
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Load all vectors with their chunk metadata
            cursor.execute(
                """
                SELECT
                    c.project_id,
                    c.path,
                    c.start_line,
                    c.end_line,
                    v.embedding,
                    v.dim
                FROM vectors v
                JOIN chunks c ON v.chunk_id = c.id
                """
            )

            rows = cursor.fetchall()
            results = []

            for row in rows:
                # Decode chunk metadata
                project_id = row[0]
                path = Path(row[1])
                start_line = row[2]
                end_line = row[3]
                embedding_blob = row[4]
                dim = row[5]

                # Decode vector
                chunk_vector = self._decode_vector(embedding_blob, dim)

                # Compute cosine similarity
                similarity = self._cosine_similarity(vector, chunk_vector)

                # Compute chunk_id
                chunk_id = Chunk.compute_id(project_id, path, start_line, end_line)

                results.append((chunk_id, similarity))

            # Sort by similarity (descending) and return top-k
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:topk]

        finally:
            conn.close()
