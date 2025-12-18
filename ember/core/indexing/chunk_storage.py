"""Chunk storage service for indexing pipeline.

Handles storing chunks, generating embeddings, and storing vectors
with transactional rollback support on failure.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from ember.domain.entities import Chunk
from ember.ports.embedders import Embedder
from ember.ports.repositories import ChunkRepository, VectorRepository

logger = logging.getLogger(__name__)


@dataclass
class StorageResult:
    """Result of storing chunks and embeddings.

    Attributes:
        chunks_created: Number of new chunks created.
        chunks_updated: Number of existing chunks updated (by content hash).
        vectors_stored: Number of vectors stored.
        failed: 1 if storage failed, 0 if successful.
    """

    chunks_created: int
    chunks_updated: int
    vectors_stored: int
    failed: int

    @classmethod
    def success(
        cls, chunks_created: int, chunks_updated: int, vectors_stored: int
    ) -> "StorageResult":
        """Create a successful result."""
        return cls(
            chunks_created=chunks_created,
            chunks_updated=chunks_updated,
            vectors_stored=vectors_stored,
            failed=0,
        )

    @classmethod
    def failure(cls) -> "StorageResult":
        """Create a failure result."""
        return cls(chunks_created=0, chunks_updated=0, vectors_stored=0, failed=1)


class ChunkStorageService:
    """Service for storing chunks and their embeddings.

    Handles:
    - Deleting old chunks for a file path
    - Storing new chunks (tracking created vs updated)
    - Batch embedding generation
    - Storing vectors
    - Rollback on failure

    This service is designed to be independently testable and
    separates storage concerns from indexing orchestration.
    """

    def __init__(
        self,
        chunk_repo: ChunkRepository,
        vector_repo: VectorRepository,
        embedder: Embedder,
    ) -> None:
        """Initialize the chunk storage service.

        Args:
            chunk_repo: Repository for storing chunks.
            vector_repo: Repository for storing vectors.
            embedder: Embedding model for generating vectors.
        """
        self.chunk_repo = chunk_repo
        self.vector_repo = vector_repo
        self.embedder = embedder

    def delete_old_chunks(self, rel_path: Path) -> bool:
        """Delete all existing chunks for a file path.

        Args:
            rel_path: Relative path of the file.

        Returns:
            True if deletion succeeded, False on error.
        """
        try:
            self.chunk_repo.delete_all_for_path(path=rel_path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete old chunks for {rel_path}: {e}", exc_info=True)
            return False

    def store_chunks_and_embeddings(
        self, chunks: list[Chunk], rel_path: Path
    ) -> StorageResult:
        """Store chunks and their embeddings with rollback on failure.

        This method:
        1. Generates embeddings in batch FIRST (before any database writes)
        2. Checks which chunks are new vs existing
        3. Stores all chunks and vectors together
        4. Rolls back both chunks AND vectors on any failure

        By generating embeddings first, we avoid orphaned chunks if embedding fails.

        Args:
            chunks: List of Chunk entities to store.
            rel_path: Relative path (for logging).

        Returns:
            StorageResult with counts and success/failure status.
        """
        if not chunks:
            return StorageResult.success(
                chunks_created=0, chunks_updated=0, vectors_stored=0
            )

        # Track chunk IDs added for potential rollback (both chunks and vectors)
        added_chunk_ids: list[str] = []

        chunks_created = 0
        chunks_updated = 0
        vectors_stored = 0

        try:
            # Step 1: Generate embeddings FIRST (before any database writes)
            # This ensures no orphaned chunks if embedding fails
            contents = [chunk.content for chunk in chunks]
            embeddings = self.embedder.embed_texts(contents)

            # Validate embedding count matches chunk count
            if len(embeddings) != len(chunks):
                raise ValueError(
                    f"Embedding count mismatch: got {len(embeddings)} embeddings "
                    f"for {len(chunks)} chunks"
                )

            # Compute fingerprint once (avoids repeated function calls)
            model_fingerprint = self.embedder.fingerprint()

            # Step 2: Check which chunks are new vs existing (read-only queries)
            is_new_chunk: list[bool] = []
            for chunk in chunks:
                existing = self.chunk_repo.find_by_content_hash(chunk.content_hash)
                is_new_chunk.append(len(existing) == 0)

            # Step 3: Store chunks and vectors together
            for chunk, embedding, is_new in zip(
                chunks, embeddings, is_new_chunk, strict=True
            ):
                # Store chunk
                self.chunk_repo.add(chunk)
                added_chunk_ids.append(chunk.id)

                if is_new:
                    chunks_created += 1
                else:
                    chunks_updated += 1

                # Store vector immediately after chunk
                self.vector_repo.add(
                    chunk_id=chunk.id,
                    embedding=embedding,
                    model_fingerprint=model_fingerprint,
                )
                vectors_stored += 1

            return StorageResult.success(
                chunks_created=chunks_created,
                chunks_updated=chunks_updated,
                vectors_stored=vectors_stored,
            )

        except Exception as e:
            # Rollback: delete any chunks and vectors we added
            logger.error(
                f"Error storing chunks for {rel_path}: {e}. Rolling back.", exc_info=True
            )
            self._rollback_chunks_and_vectors(added_chunk_ids)
            return StorageResult.failure()

    def _rollback_chunks_and_vectors(self, chunk_ids: list[str]) -> None:
        """Rollback chunks and vectors that were added during a failed operation.

        Deletes both chunks and their corresponding vectors to maintain
        consistency. Continues on individual delete failures (best-effort).

        Args:
            chunk_ids: List of chunk IDs to delete (both chunk and vector).
        """
        for chunk_id in chunk_ids:
            # Delete chunk
            try:
                self.chunk_repo.delete(chunk_id)
            except Exception as delete_err:
                logger.warning(f"Failed to rollback chunk {chunk_id}: {delete_err}")

            # Delete corresponding vector
            try:
                self.vector_repo.delete(chunk_id)
            except Exception as delete_err:
                logger.warning(f"Failed to rollback vector {chunk_id}: {delete_err}")
