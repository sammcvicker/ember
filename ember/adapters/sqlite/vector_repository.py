"""SQLite adapter implementing VectorRepository protocol for embedding storage."""

import logging
import struct
from pathlib import Path

from ember.adapters.sqlite.base_repository import SQLiteBaseRepository

logger = logging.getLogger(__name__)


class CorruptedVectorError(Exception):
    """Raised when a vector BLOB cannot be decoded due to corruption.

    This typically happens from interrupted writes, database corruption,
    or dimension mismatch after an embedding model change without reindexing.

    Attributes:
        chunk_id: The chunk identifier associated with the corrupted vector.
        expected_bytes: The number of bytes expected for the given dimension.
        actual_bytes: The actual number of bytes in the BLOB.
    """

    def __init__(
        self,
        chunk_id: str | None,
        expected_bytes: int,
        actual_bytes: int,
    ) -> None:
        self.chunk_id = chunk_id
        self.expected_bytes = expected_bytes
        self.actual_bytes = actual_bytes
        chunk_desc = chunk_id if chunk_id else "unknown chunk"
        super().__init__(
            f"Corrupted vector BLOB for chunk '{chunk_desc}': "
            f"expected {expected_bytes} bytes (dim={expected_bytes // 4}) "
            f"but got {actual_bytes} bytes. "
            f"This may indicate database corruption or a model change. "
            f"Run 'ember sync --force' to rebuild the index."
        )


class SQLiteVectorRepository(SQLiteBaseRepository):
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
        super().__init__(db_path, foreign_keys=True)
        self.expected_dim = expected_dim

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

    def _decode_vector(
        self, blob: bytes, dim: int, chunk_id: str | None = None
    ) -> list[float]:
        """Decode a vector from binary BLOB.

        Validates BLOB size before decoding and provides informative error
        messages including chunk context when available.

        Args:
            blob: Binary BLOB data.
            dim: Expected vector dimension.
            chunk_id: Optional chunk identifier for error context.

        Returns:
            List of floats.

        Raises:
            CorruptedVectorError: If BLOB size doesn't match expected dimension.
        """
        expected_bytes = dim * 4  # float32 = 4 bytes
        actual_bytes = len(blob)

        if actual_bytes != expected_bytes:
            raise CorruptedVectorError(
                chunk_id=chunk_id,
                expected_bytes=expected_bytes,
                actual_bytes=actual_bytes,
            )

        try:
            return list(struct.unpack(f"{dim}f", blob))
        except struct.error as e:
            raise CorruptedVectorError(
                chunk_id=chunk_id,
                expected_bytes=expected_bytes,
                actual_bytes=actual_bytes,
            ) from e

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

    def get(self, chunk_id: str) -> list[float] | None:
        """Retrieve an embedding vector for a chunk.

        Uses graceful degradation: if the stored vector BLOB is corrupted,
        returns None and logs a warning instead of raising an exception.

        Args:
            chunk_id: The chunk identifier.

        Returns:
            The embedding vector if found and valid, None otherwise.
        """
        # Get the DB's internal chunk id
        db_chunk_id = self._get_db_chunk_id(chunk_id)
        if db_chunk_id is None:
            return None

        conn = self._get_connection()
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

        try:
            return self._decode_vector(blob, dim, chunk_id=chunk_id)
        except CorruptedVectorError:
            logger.warning(
                "Skipping corrupted vector for chunk '%s': "
                "expected %d bytes but got %d bytes. "
                "Run 'ember sync --force' to rebuild the index.",
                chunk_id,
                dim * 4,
                len(blob),
            )
            return None

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
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM vectors WHERE chunk_id = ?",
            (db_chunk_id,),
        )
        conn.commit()
