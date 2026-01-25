"""Shared utilities for extracting context lines around search results.

This module provides a single implementation of context extraction logic
used by multiple presentation components (JsonResultFormatter, ResultPresenter).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class FileSystemReader(Protocol):
    """Protocol for file system read operations."""

    def read_text_lines(self, path: Path) -> list[str] | None:
        """Read file and return lines.

        Args:
            path: Path to file to read.

        Returns:
            List of lines, or None if file doesn't exist or can't be read.
        """
        ...


@dataclass
class ContextLine:
    """A single line of context with its line number.

    Attributes:
        line: 1-based line number in the file.
        content: The text content of the line.
    """

    line: int
    content: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with 'line' and 'content' keys.
        """
        return {"line": self.line, "content": self.content}


@dataclass
class ContextData:
    """Context lines partitioned around a search result chunk.

    Attributes:
        before: Lines before the chunk.
        chunk: Lines within the chunk.
        after: Lines after the chunk.
        start_line: First line number in the context range (1-based).
        end_line: Last line number in the context range (1-based).
    """

    before: list[ContextLine]
    chunk: list[ContextLine]
    after: list[ContextLine]
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with 'before', 'chunk', 'after', 'start_line', 'end_line' keys.
        """
        return {
            "before": [line.to_dict() for line in self.before],
            "chunk": [line.to_dict() for line in self.chunk],
            "after": [line.to_dict() for line in self.after],
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


def get_context_for_result(
    result: Any,
    context_lines: int,
    repo_root: Path,
    fs: FileSystemReader | None = None,
    file_reader: Callable[[Path], list[str] | None] | None = None,
) -> ContextData | None:
    """Extract context lines around a search result.

    Reads the file containing the search result and partitions lines into
    before/chunk/after segments based on the chunk's line range.

    Args:
        result: SearchResult object with a chunk attribute containing path,
                start_line, and end_line.
        context_lines: Number of lines of context to include before and after
                       the chunk.
        repo_root: Repository root path for resolving relative file paths.
        fs: FileSystem port for reading file contents. Required if file_reader
            is not provided.
        file_reader: Optional custom function to read file lines. If provided,
                     takes precedence over fs. Should return list of lines or None.

    Returns:
        ContextData with partitioned lines, or None if file not readable.

    Raises:
        ValueError: If neither fs nor file_reader is provided.
    """
    # Determine how to read the file
    if file_reader is not None:
        file_lines = file_reader(repo_root / result.chunk.path)
    elif fs is not None:
        file_lines = fs.read_text_lines(repo_root / result.chunk.path)
    else:
        raise ValueError("Either fs or file_reader must be provided")

    if file_lines is None:
        return None

    start_line = result.chunk.start_line
    end_line = result.chunk.end_line

    # Calculate context range (1-based line numbers)
    context_start = max(1, start_line - context_lines)
    context_end = min(len(file_lines), end_line + context_lines)

    # Collect context lines
    before_lines: list[ContextLine] = []
    chunk_lines: list[ContextLine] = []
    after_lines: list[ContextLine] = []

    for line_num in range(context_start, context_end + 1):
        line_content = file_lines[line_num - 1]  # Convert to 0-based
        context_line = ContextLine(line=line_num, content=line_content)

        if line_num < start_line:
            before_lines.append(context_line)
        elif line_num > end_line:
            after_lines.append(context_line)
        else:
            chunk_lines.append(context_line)

    return ContextData(
        before=before_lines,
        chunk=chunk_lines,
        after=after_lines,
        start_line=context_start,
        end_line=context_end,
    )
