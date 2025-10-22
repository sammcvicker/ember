"""SQLite-vec adapter for efficient vector similarity search.

This adapter uses the sqlite-vec extension for optimized vector search.
sqlite-vec provides much better performance than brute-force methods,
especially for larger datasets.
"""

import sqlite3
import struct
from pathlib import Path

import sqlite_vec

from ember.domain.entities import Chunk


class SqliteVecAdapter:
    """Vector search adapter using sqlite-vec extension.

    This adapter uses the sqlite-vec extension (https://github.com/asg017/sqlite-vec)
    for efficient vector similarity search. It's significantly faster than brute-force
    methods and works well for datasets of any size.

    The adapter creates a vec0 virtual table that stores vectors and provides
    fast k-nearest-neighbors search using cosine similarity.
    """

    def __init__(self, db_path: Path, vector_dim: int = 768) -> None:
        """Initialize sqlite-vec adapter.

        Args:
            db_path: Path to SQLite database file.
            vector_dim: Dimension of embedding vectors (default 768 for Jina v2 Code).
        """
        self.db_path = db_path
        self.vector_dim = vector_dim
        self._ensure_vec_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with sqlite-vec extension loaded.

        Returns:
            SQLite connection object with vec extension enabled.
        """
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def _ensure_vec_table(self) -> None:
        """Ensure the vec0 virtual table exists and is populated.

        Creates the vec_chunks virtual table if it doesn't exist.
        This table stores vectors and chunk metadata for efficient similarity search.

        Also syncs vectors from the vectors table on first use.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Create vec0 virtual table for vector similarity search
            # Using cosine distance metric (best for normalized embeddings like Jina)
            cursor.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
                    embedding float[{self.vector_dim}] distance_metric=cosine
                )
            """)

            # Create mapping table to link vec0 rowids to chunk metadata
            # vec0 uses integer rowids, but we need to map back to our chunk identifiers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vec_chunk_mapping (
                    vec_rowid INTEGER PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    chunk_db_id INTEGER NOT NULL UNIQUE
                )
            """)

            conn.commit()

            # Sync vectors from vectors table if vec_chunks is empty
            self._sync_vectors()

        finally:
            conn.close()

    def _sync_vectors(self) -> None:
        """Sync vectors from the vectors table to vec_chunks.

        This is called to populate vec_chunks with all vectors from the
        existing vectors table. New vectors added via VectorRepository will
        be picked up on the next sync.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Get all chunk_db_ids that are already in vec_chunks
            cursor.execute("SELECT chunk_db_id FROM vec_chunk_mapping")
            existing_ids = {row[0] for row in cursor.fetchall()}

            # Get all vectors from the vectors table that aren't yet in vec_chunks
            cursor.execute("""
                SELECT
                    v.chunk_id,
                    v.embedding,
                    v.dim,
                    c.project_id,
                    c.path,
                    c.start_line,
                    c.end_line
                FROM vectors v
                JOIN chunks c ON v.chunk_id = c.id
            """)

            rows = cursor.fetchall()
            vectors_to_add = []

            for row in rows:
                chunk_db_id = row[0]
                if chunk_db_id in existing_ids:
                    continue  # Already synced

                embedding_blob = row[1]
                dim = row[2]
                project_id = row[3]
                path = row[4]
                start_line = row[5]
                end_line = row[6]

                # Decode vector from BLOB (stored as float32)
                vector = list(struct.unpack(f"{dim}f", embedding_blob))

                vectors_to_add.append((vector, project_id, path, start_line, end_line, chunk_db_id))

            # Batch insert new vectors
            for vector, project_id, path, start_line, end_line, chunk_db_id in vectors_to_add:
                # Insert into vec_chunks (serialize to float32 for sqlite-vec)
                serialized_vector = sqlite_vec.serialize_float32(vector)
                cursor.execute("INSERT INTO vec_chunks(embedding) VALUES (?)", (serialized_vector,))
                vec_rowid = cursor.lastrowid

                # Insert mapping
                cursor.execute(
                    """
                    INSERT INTO vec_chunk_mapping(vec_rowid, project_id, path, start_line, end_line, chunk_db_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (vec_rowid, project_id, path, start_line, end_line, chunk_db_id),
                )

            if vectors_to_add:
                conn.commit()

        finally:
            conn.close()

    def _encode_vector(self, vector: list[float]) -> bytes:
        """Encode a vector to binary format for sqlite-vec.

        Args:
            vector: List of floats to encode.

        Returns:
            Binary representation suitable for sqlite-vec.
        """
        # sqlite-vec accepts float32 format
        return struct.pack(f"{len(vector)}f", *vector)

    def add(self, chunk_id: str, vector: list[float]) -> None:
        """Add a vector to the index.

        This is a no-op because vectors are managed by VectorRepository.
        The SqliteVecAdapter syncs from the vectors table automatically.

        Args:
            chunk_id: Unique identifier for the chunk (unused).
            vector: Embedding vector (unused).
        """
        # No-op: vectors are synced from VectorRepository's vectors table
        # The _sync_vectors method handles populating vec_chunks
        pass

    def query(
        self,
        vector: list[float],
        topk: int = 100,
        path_filter: str | None = None,
    ) -> list[tuple[str, float]]:
        """Query for nearest neighbors using sqlite-vec.

        Automatically syncs any new vectors from the vectors table before querying.

        Args:
            vector: Query embedding vector.
            topk: Maximum number of results to return.
            path_filter: Optional glob pattern to filter results by path.

        Returns:
            List of (chunk_id, similarity) tuples, sorted by similarity (descending).
            For cosine distance, similarity = 1 - distance.
        """
        # Sync any new vectors before querying
        self._sync_vectors()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Serialize query vector for sqlite-vec
            serialized_vector = sqlite_vec.serialize_float32(vector)

            # Query vec0 table for nearest neighbors
            # sqlite-vec returns distance, we need to convert to similarity
            # Add path filtering if specified
            if path_filter:
                cursor.execute(
                    """
                    SELECT
                        m.project_id,
                        m.path,
                        m.start_line,
                        m.end_line,
                        v.distance
                    FROM vec_chunks v
                    JOIN vec_chunk_mapping m ON v.rowid = m.vec_rowid
                    WHERE v.embedding MATCH ?
                      AND k = ?
                      AND m.path GLOB ?
                    ORDER BY v.distance
                    LIMIT ?
                    """,
                    (serialized_vector, topk, path_filter, topk),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        m.project_id,
                        m.path,
                        m.start_line,
                        m.end_line,
                        v.distance
                    FROM vec_chunks v
                    JOIN vec_chunk_mapping m ON v.rowid = m.vec_rowid
                    WHERE v.embedding MATCH ?
                      AND k = ?
                    ORDER BY v.distance
                    LIMIT ?
                    """,
                    (serialized_vector, topk, topk),
                )

            rows = cursor.fetchall()
            results = []

            for row in rows:
                project_id = row[0]
                path = Path(row[1])
                start_line = row[2]
                end_line = row[3]
                distance = row[4]

                # Compute chunk_id
                chunk_id = Chunk.compute_id(project_id, path, start_line, end_line)

                # Convert distance to similarity
                # For cosine distance: similarity = 1 - distance
                # This makes it compatible with the existing API where higher = more similar
                similarity = 1.0 - distance

                results.append((chunk_id, similarity))

            return results

        finally:
            conn.close()
