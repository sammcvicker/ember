"""Line-based fallback chunker.

Simple sliding window chunker for files where tree-sitter is unavailable
or for unknown/unsupported file types.
"""

from pathlib import Path

from ember.ports.chunkers import ChunkData


class LineChunker:
    """Line-based sliding window chunker.

    Uses fixed window size with configurable stride to create overlapping chunks.
    Suitable for text files, unknown languages, or as a fallback.
    """

    def __init__(
        self,
        window_size: int = 120,
        stride: int = 100,
    ) -> None:
        """Initialize line chunker.

        Args:
            window_size: Number of lines per chunk (default 120).
            stride: Number of lines to advance between chunks (default 100).
                   Overlap = window_size - stride (default 20 lines).
        """
        # Note: These validations mirror IndexConfig domain constraints.
        # When instantiated via IndexConfig (production path), values are
        # pre-validated. These checks provide defense for direct usage.
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        if stride <= 0:
            raise ValueError("stride must be positive")
        if stride > window_size:
            raise ValueError("stride cannot exceed window_size")

        self.window_size = window_size
        self.stride = stride

    @property
    def supported_languages(self) -> set[str]:
        """Return set of supported language identifiers.

        Line chunker supports all languages as a fallback.
        Returns empty set to indicate universal support.
        """
        return set()  # Universal fallback - supports everything

    def chunk_file(self, content: str, path: Path, lang: str) -> list[ChunkData]:
        """Chunk file using line-based sliding windows.

        Args:
            content: File content as string.
            path: File path (for context).
            lang: Language identifier (passed through to ChunkData).

        Returns:
            List of ChunkData with line-based chunks.
            Empty list if content is empty.
        """
        if not content.strip():
            return []

        lines = content.split("\n")
        total_lines = len(lines)

        # If file is smaller than window, return single chunk
        if total_lines <= self.window_size:
            return [
                ChunkData(
                    start_line=1,
                    end_line=total_lines,
                    content=content,
                    symbol=None,  # No symbol for line-based chunks
                    lang=lang,
                )
            ]

        chunks: list[ChunkData] = []
        start = 0

        while start < total_lines:
            end = min(start + self.window_size, total_lines)

            # Extract chunk content
            chunk_lines = lines[start:end]
            chunk_content = "\n".join(chunk_lines)

            # Create chunk (1-indexed line numbers)
            chunks.append(
                ChunkData(
                    start_line=start + 1,
                    end_line=end,
                    content=chunk_content,
                    symbol=None,
                    lang=lang,
                )
            )

            # Move to next window
            start += self.stride

            # If we're at or past the end, break
            if end >= total_lines:
                break

        return chunks
