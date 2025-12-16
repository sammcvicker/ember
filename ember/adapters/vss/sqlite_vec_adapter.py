"""SQLite-vec adapter for efficient vector similarity search.

This adapter uses the sqlite-vec extension for optimized vector search.
sqlite-vec provides much better performance than brute-force methods,
especially for larger datasets.
"""

import re
import sqlite3
import struct
import threading
from pathlib import Path

import sqlite_vec


class DimensionMismatchError(Exception):
    """Raised when query vector dimension doesn't match stored vectors.

    This typically happens when the embedding model changes without reindexing.
    """

    def __init__(self, expected: int, received: int) -> None:
        self.expected = expected
        self.received = received
        super().__init__(
            f"Vector dimension mismatch: index expects {expected} dimensions "
            f"but received {received}. This usually means the embedding model changed. "
            f"Run 'ember sync --force' to rebuild the index with the current model."
        )


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
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()
        self._ensure_vec_table()

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SqliteVecAdapter":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit context manager."""
        self.close()
        return False

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with sqlite-vec extension loaded.

        Reuses an existing connection if available, otherwise creates a new one.
        The sqlite-vec extension is loaded only once when the connection is created.
        Uses check_same_thread=False to allow use from different threads, which
        is required for interactive search where queries run in a thread executor.

        Thread-safe: Uses double-checked locking to prevent race conditions
        where multiple threads could create separate connections simultaneously.

        Returns:
            SQLite connection object with vec extension enabled.
        """
        if self._conn is None:
            with self._conn_lock:
                # Double-check pattern: re-check after acquiring lock
                if self._conn is None:
                    self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                    self._conn.enable_load_extension(True)
                    sqlite_vec.load(self._conn)
                    self._conn.enable_load_extension(False)
        return self._conn

    def _ensure_vec_table(self) -> None:
        """Ensure the vec0 virtual table exists and is populated.

        Creates the vec_chunks virtual table if it doesn't exist.
        This table stores vectors and chunk metadata for efficient similarity search.

        Also syncs vectors from the vectors table on first use.
        """
        conn = self._get_connection()
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

    def _sync_vectors(self) -> None:
        """Sync vectors from the vectors table to vec_chunks.

        This is called to populate vec_chunks with all vectors from the
        existing vectors table. New vectors added via VectorRepository will
        be picked up on the next sync.

        Uses batch inserts with executemany() for significantly better performance
        when syncing large numbers of vectors. For 1000 vectors, this reduces
        database calls from 2000 individual executes to 2 batch operations.
        """
        conn = self._get_connection()
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

        if not vectors_to_add:
            return

        # Get the current max rowid to calculate new rowids after batch insert
        cursor.execute("SELECT COALESCE(MAX(rowid), 0) FROM vec_chunks")
        base_rowid = cursor.fetchone()[0]

        # Batch insert vectors using executemany()
        # Serialize all vectors first
        vec_data = [
            (sqlite_vec.serialize_float32(vector),)
            for vector, *_ in vectors_to_add
        ]
        cursor.executemany("INSERT INTO vec_chunks(embedding) VALUES (?)", vec_data)

        # Build mapping data with calculated rowids
        # SQLite AUTOINCREMENT guarantees sequential rowids for batch inserts
        mapping_data = [
            (
                base_rowid + i + 1,  # vec_rowid (1-indexed from base)
                project_id,
                path,
                start_line,
                end_line,
                chunk_db_id,
            )
            for i, (_, project_id, path, start_line, end_line, chunk_db_id) in enumerate(
                vectors_to_add
            )
        ]

        # Batch insert mappings
        cursor.executemany(
            """
            INSERT INTO vec_chunk_mapping(vec_rowid, project_id, path, start_line, end_line, chunk_db_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            mapping_data,
        )

        conn.commit()

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

        Raises:
            DimensionMismatchError: If query vector dimension doesn't match index.
        """
        # Sync any new vectors before querying
        self._sync_vectors()

        conn = self._get_connection()
        cursor = conn.cursor()

        # Serialize query vector for sqlite-vec
        serialized_vector = sqlite_vec.serialize_float32(vector)

        try:
            # Query vec0 table for nearest neighbors
            # sqlite-vec returns distance, we need to convert to similarity
            # Add path filtering if specified
            # Join with chunks table to get the stored chunk_id
            if path_filter:
                cursor.execute(
                    """
                    SELECT
                        c.chunk_id,
                        v.distance
                    FROM vec_chunks v
                    JOIN vec_chunk_mapping m ON v.rowid = m.vec_rowid
                    JOIN chunks c ON m.chunk_db_id = c.id
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
                        c.chunk_id,
                        v.distance
                    FROM vec_chunks v
                    JOIN vec_chunk_mapping m ON v.rowid = m.vec_rowid
                    JOIN chunks c ON m.chunk_db_id = c.id
                    WHERE v.embedding MATCH ?
                      AND k = ?
                    ORDER BY v.distance
                    LIMIT ?
                    """,
                    (serialized_vector, topk, topk),
                )
        except sqlite3.OperationalError as e:
            # Catch dimension mismatch error from sqlite-vec and provide helpful message
            error_msg = str(e)
            if "Dimension mismatch" in error_msg:
                # Parse dimensions from error message:
                # "Dimension mismatch for ... Expected 768 dimensions but received 384."
                match = re.search(r"Expected (\d+) dimensions but received (\d+)", error_msg)
                if match:
                    expected = int(match.group(1))
                    received = int(match.group(2))
                    raise DimensionMismatchError(expected, received) from e
            raise

        rows = cursor.fetchall()
        results = []

        for row in rows:
            # Use the stored chunk_id from database instead of computing it
            chunk_id = row[0]
            distance = row[1]

            # Convert distance to similarity
            # For cosine distance: similarity = 1 - distance
            # This makes it compatible with the existing API where higher = more similar
            similarity = 1.0 - distance

            results.append((chunk_id, similarity))

        return results
