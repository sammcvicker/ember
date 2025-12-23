"""Search port interfaces for text and vector retrieval.

Defines abstract interfaces for full-text search (FTS), vector search, reranking, and fusion.

Note on implementation patterns:
    Search backends may use one of two approaches for data ingestion:

    1. **Push-based**: Data is explicitly added via add() calls. The add() method
       immediately indexes the data.

    2. **Sync-based**: Data is synced from another source (e.g., database triggers
       or a separate repository). The add() method is a no-op, and sync() pulls
       data from the source.

    Both patterns are valid. Sync-based implementations are common when the search
    index needs to stay in sync with a primary data store via database triggers.
"""

from typing import Protocol


class TextSearch(Protocol):
    """Full-text search interface (e.g., BM25, FTS5).

    Implementations may use push-based (add() inserts) or sync-based (add() is no-op,
    data comes from triggers/external sync) patterns. Check the specific implementation
    documentation for details.
    """

    def add(self, chunk_id: str, text: str, metadata: dict[str, str]) -> None:
        """Add a document to the text search index.

        Note: This method may be a no-op for sync-based implementations that use
        database triggers or external sync mechanisms. Such implementations keep
        the search index in sync with a primary data store automatically.

        For sync-based implementations, data added to the primary store will be
        searchable after the next sync (which may be automatic or manual).

        Args:
            chunk_id: Unique identifier for the chunk.
            text: Text content to index.
            metadata: Additional metadata (path, lang, etc.).
        """
        ...

    def query(
        self, q: str, topk: int = 100, path_filter: str | None = None
    ) -> list[tuple[str, float]]:
        """Query the text search index.

        Args:
            q: Query string (may use FTS query syntax).
            topk: Maximum number of results to return.
            path_filter: Optional glob pattern to filter results by path.

        Returns:
            List of (chunk_id, score) tuples, sorted by relevance (descending).
        """
        ...

    def sync(self) -> None:
        """Synchronize the search index with the primary data store.

        For sync-based implementations, this pulls any pending changes from the
        primary data store into the search index. For push-based implementations,
        this is typically a no-op since data is already indexed on add().

        Implementations should be idempotent - calling sync() multiple times
        without data changes should have no effect.
        """
        ...


class VectorSearch(Protocol):
    """Vector similarity search interface (e.g., FAISS, sqlite-vss).

    Implementations may use push-based (add() inserts) or sync-based (add() is no-op,
    data comes from a separate repository) patterns. Check the specific implementation
    documentation for details.
    """

    def add(self, chunk_id: str, vector: list[float]) -> None:
        """Add a vector to the index.

        Note: This method may be a no-op for sync-based implementations that sync
        vectors from a separate repository (e.g., VectorRepository). Such implementations
        keep the search index in sync with the vector store automatically.

        For sync-based implementations, vectors added to the primary store will be
        searchable after the next sync (which may be automatic or manual).

        Args:
            chunk_id: Unique identifier for the chunk.
            vector: Embedding vector.
        """
        ...

    def query(
        self,
        vector: list[float],
        topk: int = 100,
        path_filter: str | None = None,
    ) -> list[tuple[str, float]]:
        """Query for nearest neighbors.

        Args:
            vector: Query embedding vector.
            topk: Maximum number of results to return.
            path_filter: Optional glob pattern to filter results by path.

        Returns:
            List of (chunk_id, distance) tuples, sorted by distance (ascending).
        """
        ...

    def sync(self) -> None:
        """Synchronize the vector index with the primary data store.

        For sync-based implementations, this pulls any pending vectors from the
        primary data store into the search index. For push-based implementations,
        this is typically a no-op since vectors are already indexed on add().

        Implementations should be idempotent - calling sync() multiple times
        without data changes should have no effect.
        """
        ...


class Reranker(Protocol):
    """Reranking interface (e.g., cross-encoder models)."""

    def rerank(
        self,
        query: str,
        chunks: list[tuple[str, str]],
        topk: int = 20,
    ) -> list[tuple[str, float]]:
        """Rerank chunks based on query relevance.

        Args:
            query: The query string.
            chunks: List of (chunk_id, text) pairs to rerank.
            topk: Number of top results to return.

        Returns:
            List of (chunk_id, score) tuples, sorted by relevance (descending).
        """
        ...


class Fuser(Protocol):
    """Result fusion interface for combining multiple result lists."""

    def fuse(
        self,
        result_lists: list[list[tuple[str, float]]],
        topk: int = 20,
    ) -> list[tuple[str, float]]:
        """Fuse multiple ranked result lists into one.

        Args:
            result_lists: List of result lists, each containing (id, score) tuples.
            topk: Number of top results to return after fusion.

        Returns:
            Fused list of (chunk_id, score) tuples, sorted by score (descending).
        """
        ...
