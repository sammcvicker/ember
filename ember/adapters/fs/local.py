"""Local file system adapter.

Implements the FileSystem port using the standard library pathlib.
This is the default adapter for file system operations.
"""

from pathlib import Path


class LocalFileSystem:
    """Local file system implementation using pathlib.

    This adapter implements the FileSystem port protocol for standard
    local file system operations. All paths should be absolute.
    """

    def read(self, path: Path) -> bytes:
        """Read file contents.

        Args:
            path: Absolute path to file.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        return path.read_bytes()

    def write(self, path: Path, content: bytes) -> None:
        """Write content to file.

        Args:
            path: Absolute path to file.
            content: Content to write.

        Raises:
            IOError: If write fails.
        """
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def exists(self, path: Path) -> bool:
        """Check if path exists.

        Args:
            path: Path to check.

        Returns:
            True if path exists, False otherwise.
        """
        return path.exists()

    def mkdir(self, path: Path, parents: bool = True) -> None:
        """Create directory.

        Args:
            path: Directory path to create.
            parents: Create parent directories if needed.

        Raises:
            FileExistsError: If directory already exists and parents=False.
        """
        path.mkdir(parents=parents, exist_ok=True)

    def glob(self, pattern: str, root: Path) -> list[Path]:
        """Find files matching glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.py").
            root: Root directory to search from.

        Returns:
            List of matching absolute paths, sorted for consistency.
        """
        # Convert to absolute paths and sort for determinism
        matches = sorted(root.glob(pattern))
        # Ensure all paths are absolute
        return [p.resolve() for p in matches]

    def read_text_lines(self, path: Path) -> list[str] | None:
        """Read file and return lines as strings.

        Args:
            path: Absolute path to file.

        Returns:
            List of lines (without trailing newlines), or None if file
            doesn't exist or can't be read.
        """
        if not path.exists():
            return None
        try:
            return path.read_text(errors="replace").splitlines()
        except OSError:
            # File system errors: permission denied, I/O errors, etc.
            return None
