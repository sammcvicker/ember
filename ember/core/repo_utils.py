"""Repository discovery utilities.

Functions for finding the ember repository root from any subdirectory.
"""

import subprocess
from pathlib import Path


def find_ember_root(start_path: Path | None = None) -> Path | None:
    """Find the ember repository root by walking up directories.

    Searches for .ember/ directory starting from start_path and walking
    up to filesystem root, similar to how git finds .git/.

    Args:
        start_path: Directory to start searching from. Defaults to CWD.

    Returns:
        Absolute path to repository root (directory containing .ember/),
        or None if not found.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    # Walk up directory tree until we find .ember/ or reach root
    while True:
        ember_dir = current / ".ember"
        if ember_dir.exists() and ember_dir.is_dir():
            return current

        # Check if we've reached the filesystem root
        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding .ember/
            return None

        current = parent


def find_git_root(start_path: Path | None = None) -> Path | None:
    """Find git repository root using git rev-parse.

    Args:
        start_path: Directory to start searching from. Defaults to CWD.

    Returns:
        Absolute path to git repository root, or None if not in a git repo.
    """
    if start_path is None:
        start_path = Path.cwd()

    try:
        result = subprocess.run(
            ["git", "-C", str(start_path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            text=True,
        )
        git_root = Path(result.stdout.strip())
        return git_root.resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def find_repo_root(start_path: Path | None = None) -> tuple[Path, Path]:
    """Find ember repository root and .ember directory.

    This is the main entry point for repository discovery. It:
    1. Searches for .ember/ by walking up directories
    2. Falls back to finding git root if needed (for init command)

    Args:
        start_path: Directory to start searching from. Defaults to CWD.

    Returns:
        Tuple of (repo_root, ember_dir) where:
        - repo_root: Absolute path to repository root
        - ember_dir: Absolute path to .ember/ directory

    Raises:
        RuntimeError: If not in an ember repository
    """
    if start_path is None:
        start_path = Path.cwd()

    # First, try to find .ember/ by walking up
    repo_root = find_ember_root(start_path)
    if repo_root:
        return repo_root, repo_root / ".ember"

    # Not found - raise clear error
    raise RuntimeError(
        "Not in an ember repository (or any parent directory)\n"
        "Run 'ember init' from your repository root first"
    )


def find_repo_root_for_init(start_path: Path | None = None) -> Path:
    """Find repository root for initialization.

    For the init command, we want to find the git root (if in a git repo)
    or use the current directory (if not in a git repo).

    Args:
        start_path: Directory to start searching from. Defaults to CWD.

    Returns:
        Absolute path to repository root where .ember/ should be created.
    """
    if start_path is None:
        start_path = Path.cwd()

    # Try to find git root first
    git_root = find_git_root(start_path)
    if git_root:
        return git_root

    # Not in a git repo - use current directory
    return start_path.resolve()
