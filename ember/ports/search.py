"""Search port interfaces for text and vector retrieval.

Defines abstract interfaces for full-text search (FTS), vector search, reranking, and fusion.
"""

from typing import Protocol


class TextSearch(Protocol):
    """Full-text search interface (e.g., BM25, FTS5)."""

    def add(self, chunk_id: str, text: str, metadata: dict[str, str]) -> None:
        """Add a document to the text search index.

        Args:
            chunk_id: Unique identifier for the chunk.
            text: Text content to index.
            metadata: Additional metadata (path, lang, etc.).
        """
        ...

    def query(self, q: str, topk: int = 100) -> list[tuple[str, float]]:
        """Query the text search index.

        Args:
            q: Query string (may use FTS query syntax).
            topk: Maximum number of results to return.

        Returns:
            List of (chunk_id, score) tuples, sorted by relevance (descending).
        """
        ...


class VectorSearch(Protocol):
    """Vector similarity search interface (e.g., FAISS, sqlite-vss)."""

    def add(self, chunk_id: str, vector: list[float]) -> None:
        """Add a vector to the index.

        Args:
            chunk_id: Unique identifier for the chunk.
            vector: Embedding vector.
        """
        ...

    def query(
        self,
        vector: list[float],
        topk: int = 100,
    ) -> list[tuple[str, float]]:
        """Query for nearest neighbors.

        Args:
            vector: Query embedding vector.
            topk: Maximum number of results to return.

        Returns:
            List of (chunk_id, distance) tuples, sorted by distance (ascending).
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
