"""Path normalization utilities for CLI commands.

Handles conversion of path arguments to repository-relative glob patterns.
"""

from pathlib import Path

from ember.domain.exceptions import ConflictingFiltersError, PathNotInRepositoryError


def normalize_path_filter(
    path: str | None,
    existing_filter: str | None,
    repo_root: Path,
    cwd: Path,
) -> str | None:
    """Normalize path argument and existing filter into a unified path filter.

    Handles conversion of PATH argument to repo-relative glob pattern, checks
    for mutual exclusivity with existing filter, and validates path is within
    repository.

    Args:
        path: Optional PATH argument from CLI (relative to cwd or absolute).
        existing_filter: Optional existing --in filter pattern.
        repo_root: Repository root directory (absolute path).
        cwd: Current working directory (absolute path).

    Returns:
        Normalized path filter glob pattern, or None if no path filtering.

    Raises:
        PathNotInRepositoryError: If path is outside the repository.
        ConflictingFiltersError: If both path and existing_filter are provided.
    """
    if path is None:
        return existing_filter

    # Convert path argument to absolute, then to relative from repo root
    path_abs = (cwd / path).resolve()

    # Check if path is within repo
    try:
        path_rel_to_repo = path_abs.relative_to(repo_root)
    except ValueError:
        raise PathNotInRepositoryError(
            f"Path '{path}' is not within repository",
            hint="Specify a path relative to or within the repository root",
        ) from None

    # Check for mutually exclusive filter options
    if existing_filter:
        raise ConflictingFiltersError(
            f"Cannot use both PATH argument ('{path}') and --in filter ('{existing_filter}')",
            hint="Use PATH to search a directory subtree, OR --in for glob patterns, but not both",
        )

    # Create glob pattern for this path subtree
    if path_rel_to_repo == Path("."):
        return "*/**"
    return f"{path_rel_to_repo}/**"
