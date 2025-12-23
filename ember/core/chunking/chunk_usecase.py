"""Chunking use case - orchestrates code-aware and fallback chunking.

This module provides the business logic for chunking files using tree-sitter
when available, falling back to line-based chunking for unsupported languages.
"""

from dataclasses import dataclass
from pathlib import Path

from ember.ports.chunkers import ChunkData, Chunker


@dataclass
class ChunkFileRequest:
    """Request to chunk a file.

    Attributes:
        content: File content as string.
        path: File path (relative to project root).
        lang: Language identifier (py, ts, go, rs, txt, etc.).
    """

    content: str
    path: Path
    lang: str


@dataclass
class ChunkFileResponse:
    """Response from chunking operation.

    Attributes:
        chunks: List of extracted chunks.
        strategy: Strategy used ("tree-sitter" or "line-based").
        success: Whether chunking succeeded.
        error: Error message if chunking failed.
    """

    chunks: list[ChunkData]
    strategy: str
    success: bool = True
    error: str | None = None

    @classmethod
    def create_success(
        cls, *, chunks: list[ChunkData], strategy: str
    ) -> "ChunkFileResponse":
        """Create a success response with chunks.

        Args:
            chunks: List of extracted chunks.
            strategy: Strategy used ("tree-sitter", "line-based", or "none").

        Returns:
            ChunkFileResponse with success=True and chunks.
        """
        return cls(
            chunks=chunks,
            strategy=strategy,
            success=True,
            error=None,
        )

    @classmethod
    def create_error(cls, message: str) -> "ChunkFileResponse":
        """Create an error response.

        Args:
            message: Error message describing what went wrong.

        Returns:
            ChunkFileResponse with success=False and empty chunks.
        """
        return cls(
            chunks=[],
            strategy="",
            success=False,
            error=message,
        )


class ChunkFileUseCase:
    """Use case for chunking files with automatic fallback.

    Tries tree-sitter code-aware chunking first for supported languages,
    then falls back to line-based chunking for unsupported languages or
    if tree-sitter parsing fails.
    """

    def __init__(
        self,
        tree_sitter_chunker: Chunker,
        line_chunker: Chunker,
    ) -> None:
        """Initialize chunking use case.

        Args:
            tree_sitter_chunker: Tree-sitter based code-aware chunker.
            line_chunker: Line-based fallback chunker.
        """
        self.tree_sitter = tree_sitter_chunker
        self.line_chunker = line_chunker

    def execute(self, request: ChunkFileRequest) -> ChunkFileResponse:
        """Execute chunking on a file with automatic fallback.

        Args:
            request: Chunking request with file content and metadata.

        Returns:
            Response with chunks and strategy used.
        """
        # Validate input
        if not request.content.strip():
            return ChunkFileResponse.create_success(chunks=[], strategy="none")

        # Try tree-sitter first for supported languages
        if request.lang in self.tree_sitter.supported_languages:
            chunks = self.tree_sitter.chunk_file(
                content=request.content,
                path=request.path,
                lang=request.lang,
            )

            # If tree-sitter succeeded and returned chunks, use them
            if chunks:
                return ChunkFileResponse.create_success(
                    chunks=chunks, strategy="tree-sitter"
                )

            # Tree-sitter failed or returned no chunks, fall back to line-based

        # Fall back to line-based chunking
        chunks = self.line_chunker.chunk_file(
            content=request.content,
            path=request.path,
            lang=request.lang,
        )

        return ChunkFileResponse.create_success(chunks=chunks, strategy="line-based")
