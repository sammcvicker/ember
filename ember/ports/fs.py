"""File System port interface.

Defines abstract interface for file system operations.
Enables testing and potential alternative storage backends.
"""

from pathlib import Path
from typing import Protocol


class FileSystem(Protocol):
    """Protocol for file system operations."""

    def read(self, path: Path) -> bytes:
        """Read file contents.

        Args:
            path: Absolute path to file.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        ...

    def write(self, path: Path, content: bytes) -> None:
        """Write content to file.

        Args:
            path: Absolute path to file.
            content: Content to write.

        Raises:
            IOError: If write fails.
        """
        ...

    def exists(self, path: Path) -> bool:
        """Check if path exists.

        Args:
            path: Path to check.

        Returns:
            True if path exists, False otherwise.
        """
        ...

    def mkdir(self, path: Path, parents: bool = True) -> None:
        """Create directory.

        Args:
            path: Directory path to create.
            parents: Create parent directories if needed.

        Raises:
            FileExistsError: If directory already exists and parents=False.
        """
        ...

    def glob(self, pattern: str, root: Path) -> list[Path]:
        """Find files matching glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.py").
            root: Root directory to search from.

        Returns:
            List of matching absolute paths.
        """
        ...

    def read_text_lines(self, path: Path) -> list[str] | None:
        """Read file and return lines as strings.

        Args:
            path: Absolute path to file.

        Returns:
            List of lines (without trailing newlines), or None if file
            doesn't exist or can't be read.
        """
        ...
