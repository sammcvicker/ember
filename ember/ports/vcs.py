"""Version Control System (VCS) port interface.

Defines abstract interface for interacting with Git repositories.
"""

from pathlib import Path
from typing import Literal, Protocol

FileStatus = Literal["added", "modified", "deleted", "renamed"]


class VCS(Protocol):
    """Protocol for version control system operations (Git)."""

    def get_tree_sha(self, ref: str = "HEAD") -> str:
        """Get the tree SHA for a given ref.

        Args:
            ref: Git ref (commit SHA, branch name, tag, etc.). Default: HEAD.

        Returns:
            Tree SHA (40-char hex string).

        Raises:
            RuntimeError: If ref is invalid or not a git repository.
        """
        ...

    def get_worktree_tree_sha(self) -> str:
        """Get tree SHA representing current worktree state.

        This hashes the actual file contents (including unstaged changes),
        not just what's in Git's index.

        Returns:
            Tree SHA representing current worktree.

        Raises:
            RuntimeError: If not a git repository.
        """
        ...

    def diff_files(
        self,
        from_sha: str | None,
        to_sha: str,
    ) -> list[tuple[FileStatus, Path]]:
        """Get list of changed files between two tree SHAs.

        Args:
            from_sha: Starting tree SHA (None for empty tree).
            to_sha: Ending tree SHA.

        Returns:
            List of (status, path) tuples for changed files.
            Paths are relative to repository root.
        """
        ...

    def get_file_content(self, path: Path, ref: str = "HEAD") -> bytes:
        """Get file content at a specific ref.

        Args:
            path: Path relative to repository root.
            ref: Git ref. Default: HEAD.

        Returns:
            File content as bytes.

        Raises:
            FileNotFoundError: If file doesn't exist at ref.
            RuntimeError: If ref is invalid.
        """
        ...
