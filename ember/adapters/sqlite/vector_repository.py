"""SQLite adapter implementing VectorRepository protocol for embedding storage."""

import sqlite3
import struct
from pathlib import Path

from ember.domain.entities import Chunk


class SQLiteVectorRepository:
    """SQLite implementation of VectorRepository for storing embeddings.

    Stores vectors as BLOBs using simple binary encoding (array of floats).
    The vectors table uses the DB's internal chunk id (INTEGER), so we need
    to map from Chunk.id (string hash) to the DB id when storing/retrieving.
    """

    def __init__(self, db_path: Path, expected_dim: int | None = None) -> None:
        """Initialize vector repository.

        Args:
            db_path: Path to SQLite database file.
            expected_dim: Expected embedding dimension for validation (e.g., 768 for Jina v2).
                         If provided, validates that all embeddings have this dimension.
        """
        self.db_path = db_path
        self.expected_dim = expected_dim

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with foreign keys enabled.

        Returns:
            SQLite connection object.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _encode_vector(self, vector: list[float]) -> bytes:
        """Encode a vector as binary BLOB.

        Uses simple struct packing: array of float32 in native byte order.

        Args:
            vector: List of floats to encode.

        Returns:
            Binary BLOB representation.
        """
        # Pack as array of float32 (4 bytes each)
        return struct.pack(f"{len(vector)}f", *vector)

    def _decode_vector(self, blob: bytes, dim: int) -> list[float]:
        """Decode a vector from binary BLOB.

        Args:
            blob: Binary BLOB data.
            dim: Expected vector dimension.

        Returns:
            List of floats.
        """
        # Unpack array of float32
        return list(struct.unpack(f"{dim}f", blob))

    def _get_db_chunk_id(self, chunk_id: str) -> int | None:
        """Get the DB's internal integer id for a chunk.

        Maps from Chunk.id (blake3 hash) to the DB's autoincrement id.
        This is needed because the vectors table uses INTEGER FK.

        Args:
            chunk_id: The chunk identifier (blake3 hash).

        Returns:
            The DB integer id if found, None otherwise.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Use chunk_id column for O(1) lookup
            cursor.execute(
                """
                SELECT id FROM chunks WHERE chunk_id = ?
                """,
                (chunk_id,)
            )

            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def add(
        self,
        chunk_id: str,
        embedding: list[float],
        model_fingerprint: str,
    ) -> None:
        """Store an embedding vector for a chunk.

        Args:
            chunk_id: The chunk identifier (blake3 hash).
            embedding: The embedding vector.
            model_fingerprint: Fingerprint of the model that generated this embedding.

        Raises:
            ValueError: If embedding dimension doesn't match expected dimension.
        """
        # Validate embedding dimension if expected_dim is configured
        if self.expected_dim is not None:
            actual_dim = len(embedding)
            if actual_dim != self.expected_dim:
                raise ValueError(
                    f"Invalid embedding dimension for chunk {chunk_id}: "
                    f"expected {self.expected_dim}, got {actual_dim}"
                )

        # Get the DB's internal chunk id
        db_chunk_id = self._get_db_chunk_id(chunk_id)
        if db_chunk_id is None:
            raise ValueError(f"Chunk not found: {chunk_id}")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Encode vector as BLOB
            blob = self._encode_vector(embedding)
            dim = len(embedding)

            # UPSERT: insert or update if chunk_id exists
            cursor.execute(
                """
                INSERT INTO vectors (chunk_id, embedding, dim, model_fingerprint)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    embedding = excluded.embedding,
                    dim = excluded.dim,
                    model_fingerprint = excluded.model_fingerprint
                """,
                (db_chunk_id, blob, dim, model_fingerprint),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, chunk_id: str) -> list[float] | None:
        """Retrieve an embedding vector for a chunk.

        Args:
            chunk_id: The chunk identifier.

        Returns:
            The embedding vector if found, None otherwise.
        """
        # Get the DB's internal chunk id
        db_chunk_id = self._get_db_chunk_id(chunk_id)
        if db_chunk_id is None:
            return None

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT embedding, dim
                FROM vectors
                WHERE chunk_id = ?
                """,
                (db_chunk_id,),
            )

            row = cursor.fetchone()
            if row is None:
                return None

            blob = row[0]
            dim = row[1]

            return self._decode_vector(blob, dim)
        finally:
            conn.close()

    def delete(self, chunk_id: str) -> None:
        """Delete an embedding vector.

        Args:
            chunk_id: The chunk identifier.
        """
        # Get the DB's internal chunk id
        db_chunk_id = self._get_db_chunk_id(chunk_id)
        if db_chunk_id is None:
            return  # Already deleted or doesn't exist

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM vectors WHERE chunk_id = ?",
                (db_chunk_id,),
            )
            conn.commit()
        finally:
            conn.close()
