"""Repository port interfaces for data persistence.

These protocols define abstract interfaces for storing and retrieving domain entities.
Implementations should be in adapters/ layer.
"""

from pathlib import Path
from typing import Protocol

from ember.domain.entities import Chunk


class ChunkRepository(Protocol):
    """Repository for storing and retrieving code chunks."""

    def add(self, chunk: Chunk) -> None:
        """Add or update a chunk in the repository.

        Args:
            chunk: The chunk to store. Uses UPSERT semantics.
        """
        ...

    def get(self, chunk_id: str) -> Chunk | None:
        """Retrieve a chunk by its ID.

        Args:
            chunk_id: The unique identifier for the chunk.

        Returns:
            The chunk if found, None otherwise.
        """
        ...

    def find_by_content_hash(self, content_hash: str) -> list[Chunk]:
        """Find chunks with matching content hash.

        Args:
            content_hash: blake3 hash of chunk content.

        Returns:
            List of chunks with matching hash (typically 0 or 1).
        """
        ...

    def delete(self, chunk_id: str) -> None:
        """Delete a chunk by ID.

        Args:
            chunk_id: The chunk identifier to delete.
        """
        ...

    def list_all(
        self,
        path_filter: str | None = None,
        lang_filter: str | None = None,
    ) -> list[Chunk]:
        """List all chunks, optionally filtered.

        Args:
            path_filter: Optional glob pattern to filter by file path.
            lang_filter: Optional language code to filter by.

        Returns:
            List of matching chunks.
        """
        ...


class MetaRepository(Protocol):
    """Repository for storing metadata (state, config, etc.)."""

    def get(self, key: str) -> str | None:
        """Get a metadata value by key.

        Args:
            key: The metadata key.

        Returns:
            The value if found, None otherwise.
        """
        ...

    def set(self, key: str, value: str) -> None:
        """Set a metadata key-value pair.

        Args:
            key: The metadata key.
            value: The value to store.
        """
        ...

    def delete(self, key: str) -> None:
        """Delete a metadata key.

        Args:
            key: The metadata key to delete.
        """
        ...


class VectorRepository(Protocol):
    """Repository for storing and retrieving vector embeddings."""

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
        """
        ...

    def get(self, chunk_id: str) -> list[float] | None:
        """Retrieve an embedding vector for a chunk.

        Args:
            chunk_id: The chunk identifier.

        Returns:
            The embedding vector if found, None otherwise.
        """
        ...

    def delete(self, chunk_id: str) -> None:
        """Delete an embedding vector.

        Args:
            chunk_id: The chunk identifier.
        """
        ...


class FileRepository(Protocol):
    """Repository for tracking indexed file state."""

    def track_file(
        self,
        path: Path,
        file_hash: str,
        size: int,
        mtime: float,
    ) -> None:
        """Track state of an indexed file.

        Args:
            path: Absolute path to the file.
            file_hash: Hash of file content (blake3).
            size: File size in bytes.
            mtime: File modification timestamp.
        """
        ...

    def get_file_state(self, path: Path) -> dict[str, str | int | float] | None:
        """Get tracked state for a file.

        Args:
            path: Absolute path to the file.

        Returns:
            Dict with keys: file_hash, size, mtime, or None if not tracked.
        """
        ...

    def get_all_tracked_files(self) -> list[Path]:
        """Get list of all tracked file paths.

        Returns:
            List of absolute paths for all tracked files.
        """
        ...
