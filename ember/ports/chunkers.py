"""Chunker port for code parsing and chunking strategies.

This module defines the protocol for chunking code into semantic units.
Chunkers take file content and return structured chunk data.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ChunkData:
    """Raw chunk data before creating a Chunk entity.

    Attributes:
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (inclusive).
        content: The chunk content (code text).
        symbol: Symbol name (function/class) or None for line-based chunks.
        lang: Language identifier (py, ts, go, rs, txt, etc.).
    """

    start_line: int
    end_line: int
    content: str
    symbol: str | None
    lang: str


class Chunker(Protocol):
    """Port for code chunking strategies.

    Chunkers parse file content and extract meaningful code units
    (functions, classes, methods) or fall back to line-based windows.
    """

    def chunk_file(self, content: str, path: Path, lang: str) -> list[ChunkData]:
        """Chunk file content into semantic or line-based units.

        Args:
            content: File content as string.
            path: File path (for context/debugging).
            lang: Language identifier (py, ts, go, rs, etc.).

        Returns:
            List of ChunkData objects representing extracted chunks.
            Returns empty list if file cannot be chunked.

        Raises:
            ChunkingError: If chunking fails unexpectedly.
        """
        ...

    @property
    def supported_languages(self) -> set[str]:
        """Return set of supported language identifiers.

        Returns:
            Set of language codes this chunker supports (e.g., {"py", "ts"}).
        """
        ...
