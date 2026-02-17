"""Chunking use case - orchestrates code-aware and fallback chunking.

This module provides the business logic for chunking files using tree-sitter
when available, falling back to line-based chunking for unsupported languages.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ember.core.use_case_errors import format_error_message, log_use_case_error
from ember.ports.chunkers import ChunkData, Chunker, ParseError, ParseWarning


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
        parse_warnings: List of parse warnings (e.g., tree-sitter fallback).
    """

    chunks: list[ChunkData]
    strategy: str
    success: bool = True
    error: str | None = None
    parse_warnings: list[ParseWarning] = field(default_factory=list)

    @classmethod
    def create_success(
        cls,
        *,
        chunks: list[ChunkData],
        strategy: str,
        parse_warnings: list[ParseWarning] | None = None,
    ) -> "ChunkFileResponse":
        """Create a success response with chunks.

        Args:
            chunks: List of extracted chunks.
            strategy: Strategy used ("tree-sitter", "line-based", or "none").
            parse_warnings: Optional list of parse warnings.

        Returns:
            ChunkFileResponse with success=True and chunks.
        """
        return cls(
            chunks=chunks,
            strategy=strategy,
            success=True,
            error=None,
            parse_warnings=parse_warnings or [],
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

        Error handling contract:
            - KeyboardInterrupt/SystemExit are re-raised (user wants to exit)
            - ParseError from tree-sitter triggers fallback with a warning
            - All other exceptions are caught and converted to error responses
            - See ember.core.use_case_errors for the error handling pattern

        Args:
            request: Chunking request with file content and metadata.

        Returns:
            Response with chunks and strategy used.
        """
        try:
            # Validate input
            if not request.content.strip():
                return ChunkFileResponse.create_success(chunks=[], strategy="none")

            parse_warnings: list[ParseWarning] = []

            # Try tree-sitter first for supported languages
            if request.lang in self.tree_sitter.supported_languages:
                try:
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

                    # Tree-sitter returned no chunks (no definitions found),
                    # fall back to line-based without a warning
                except ParseError as e:
                    # Tree-sitter failed to parse - record warning and fall back
                    parse_warnings.append(
                        ParseWarning(
                            path=request.path,
                            language=request.lang,
                            reason=str(e),
                        )
                    )

            # Fall back to line-based chunking
            chunks = self.line_chunker.chunk_file(
                content=request.content,
                path=request.path,
                lang=request.lang,
            )

            return ChunkFileResponse.create_success(
                chunks=chunks,
                strategy="line-based",
                parse_warnings=parse_warnings,
            )

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            log_use_case_error(e, "chunking")
            return ChunkFileResponse.create_error(format_error_message(e, "chunking"))
