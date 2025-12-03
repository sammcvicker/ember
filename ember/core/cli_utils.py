"""CLI utility functions for command-line interface.

Shared utilities to reduce duplication across CLI commands.
"""

import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from ember.core.presentation.colors import EmberColors, highlight_symbol

if TYPE_CHECKING:
    from ember.domain.entities import Chunk
    from ember.ports.chunk_repository import ChunkRepository
    from ember.ports.daemon import DaemonManager


# Re-export highlight_symbol for backward compatibility
__all__ = ["RichProgressCallback", "progress_context", "load_cached_results",
           "validate_result_index", "highlight_symbol", "format_result_header",
           "ensure_daemon_with_progress", "lookup_result_from_cache",
           "lookup_result_by_hash", "display_content_with_context",
           "display_content_with_highlighting"]


class RichProgressCallback:
    """Rich-based progress callback for visual progress reporting.

    Uses Rich library to display a progress bar that updates as indexing progresses.
    """

    def __init__(self, progress: Progress) -> None:
        """Initialize with a Rich Progress instance.

        Args:
            progress: Rich Progress instance to use for display.
        """
        self.progress = progress
        self.task_id: int | None = None

    def on_start(self, total: int, description: str) -> None:
        """Create progress bar when operation starts."""
        # Use transient=True to auto-hide when complete
        # Initialize with empty current_file field
        self.task_id = self.progress.add_task(description, total=total, current_file="")

    def on_progress(self, current: int, item_description: str | None = None) -> None:
        """Update progress bar with current item."""
        if self.task_id is not None:
            # Update progress and current file using task fields
            # This keeps the progress bar position stable
            self.progress.update(
                self.task_id, completed=current, current_file=item_description or ""
            )

    def on_complete(self) -> None:
        """Mark progress as complete and hide it."""
        if self.task_id is not None:
            # Remove the task to hide the progress bar
            self.progress.remove_task(self.task_id)


@contextmanager
def progress_context(
    quiet_mode: bool = False,
) -> Generator[RichProgressCallback | None, None, None]:
    """Context manager for creating progress bars.

    Args:
        quiet_mode: If True, returns None (no progress reporting).

    Yields:
        RichProgressCallback if not quiet, None otherwise.

    Example:
        with progress_context(quiet=False) as progress:
            if progress:
                usecase.execute(request, progress=progress)
            else:
                usecase.execute(request)
    """
    if quiet_mode:
        yield None
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[cyan]{task.fields[current_file]}"),
            transient=True,
        ) as progress:
            yield RichProgressCallback(progress)


def load_cached_results(cache_path: Path) -> dict[str, Any]:
    """Load cached search results from JSON file.

    Args:
        cache_path: Path to .last_search.json cache file.

    Returns:
        Dictionary with 'query' and 'results' keys.

    Raises:
        SystemExit: If cache doesn't exist or is corrupted.
    """
    # Check if cache exists
    if not cache_path.exists():
        click.echo("Error: No recent search results found", err=True)
        click.echo("Run 'ember find <query>' first", err=True)
        sys.exit(1)

    try:
        cache_data = json.loads(cache_path.read_text())
        results = cache_data.get("results", [])

        if not results:
            click.echo("Error: No results in cache", err=True)
            sys.exit(1)

        return cache_data

    except json.JSONDecodeError:
        click.echo("Error: Corrupted search cache", err=True)
        sys.exit(1)


def validate_result_index(index: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate result index and return the corresponding result.

    Args:
        index: 1-based index from user.
        results: List of result dictionaries.

    Returns:
        The result dictionary at the given index.

    Raises:
        SystemExit: If index is out of range.
    """
    # Validate index (1-based)
    if index < 1 or index > len(results):
        click.echo(f"Error: Index {index} out of range (1-{len(results)})", err=True)
        sys.exit(1)

    # Get the result (convert to 0-based)
    return results[index - 1]


def format_result_header(
    result: dict[str, Any], index: int | None = None, show_symbol: bool = True
) -> None:
    """Print result header in consistent ripgrep-style format.

    Args:
        result: Result dictionary with path, start_line, symbol fields.
        index: Optional 1-based result index (rank). If None, rank is not shown.
        show_symbol: Whether to display symbol in header.
    """
    # Filename using centralized color
    click.echo(EmberColors.click_path(str(result["path"])))

    # Build second line: optional rank, line number, optional symbol
    line_num = EmberColors.click_line_number(f"{result['start_line']}")

    # Symbol using centralized color (inline)
    symbol_display = ""
    if show_symbol and result.get("symbol"):
        symbol_display = " " + EmberColors.click_symbol(f"({result['symbol']})")

    if index is not None:
        # Show rank when index is provided
        rank = EmberColors.click_rank(f"[{index}]")
        click.echo(f"{rank} {line_num}:{symbol_display}")
    else:
        # No rank for hash-based lookups
        click.echo(f"{line_num}:{symbol_display}")


def ensure_daemon_with_progress(
    daemon_manager: "DaemonManager", quiet: bool = False
) -> bool:
    """Ensure daemon is running, showing progress during startup.

    Args:
        daemon_manager: Daemon manager instance (injected dependency)
        quiet: Suppress progress output

    Returns:
        True if daemon is running, False if failed to start
    """
    # If already running, nothing to do
    if daemon_manager.is_running():
        return True

    if quiet:
        # No progress, just start
        try:
            return daemon_manager.ensure_running()
        except Exception:
            return False

    # Show progress during startup
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Starting embedding daemon...", total=None)

        try:
            # Start daemon
            result = daemon_manager.start(foreground=False)

            if result:
                progress.update(task, description="✓ Daemon started")
            return result
        except Exception as e:
            progress.update(task, description=f"✗ Failed to start daemon: {e}")
            return False


def lookup_result_from_cache(
    identifier: str, cache_path: Path
) -> dict[str, Any]:
    """Look up a result from the search cache by numeric index.

    Args:
        identifier: Numeric string index (1-based).
        cache_path: Path to .last_search.json cache file.

    Returns:
        Result dictionary with path, start_line, end_line, content, lang, symbol.

    Raises:
        SystemExit: If cache doesn't exist, is corrupted, or index is out of range.
    """
    cache_data = load_cached_results(cache_path)
    results = cache_data.get("results", [])
    return validate_result_index(int(identifier), results)


def lookup_result_by_hash(
    identifier: str, chunk_repo: "ChunkRepository"
) -> dict[str, Any]:
    """Look up a result by chunk ID hash prefix.

    Args:
        identifier: Hash prefix (or full hash) to search for.
        chunk_repo: Repository for chunk lookups.

    Returns:
        Result dictionary with path, start_line, end_line, content, lang, symbol.

    Raises:
        SystemExit: If no chunk found or multiple chunks match the prefix.
    """
    matches: list[Chunk] = chunk_repo.find_by_id_prefix(identifier)

    if len(matches) == 0:
        click.echo(f"Error: No chunk found with ID prefix '{identifier}'", err=True)
        sys.exit(1)
    elif len(matches) > 1:
        click.echo(
            f"Error: Ambiguous chunk ID prefix '{identifier}' matches {len(matches)} chunks:",
            err=True,
        )
        for chunk in matches[:5]:  # Show first 5 matches
            click.echo(f"  {chunk.id}", err=True)
        if len(matches) > 5:
            click.echo(f"  ... and {len(matches) - 5} more", err=True)
        click.echo("\nUse a longer prefix to uniquely identify the chunk", err=True)
        sys.exit(1)

    # Found exactly one match - convert to result format
    chunk = matches[0]
    return {
        "path": str(chunk.path),
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "content": chunk.content,
        "lang": chunk.lang,
        "symbol": chunk.symbol,
    }


def display_content_with_context(
    result: dict[str, Any],
    context: int,
    repo_root: Path,
) -> bool:
    """Display chunk content with surrounding context lines.

    Args:
        result: Result dictionary with path, start_line, end_line, content.
        context: Number of lines to show before and after the chunk.
        repo_root: Repository root for resolving file paths.

    Returns:
        True if content was displayed successfully, False if fallback needed.
    """
    file_path = repo_root / result["path"]
    if not file_path.exists():
        click.echo(
            f"Warning: File {result['path']} not found, showing chunk only", err=True
        )
        return False

    try:
        file_lines = file_path.read_text(errors="replace").splitlines()
        start_line = result["start_line"]
        end_line = result["end_line"]

        # Calculate context range (1-based line numbers)
        context_start = max(1, start_line - context)
        context_end = min(len(file_lines), end_line + context)

        # Display with line numbers
        for line_num in range(context_start, context_end + 1):
            line_content = file_lines[line_num - 1]  # Convert to 0-based
            # Highlight the chunk lines
            if start_line <= line_num <= end_line:
                click.echo(f"{line_num:5} | {line_content}")
            else:
                click.echo(click.style(f"{line_num:5} | {line_content}", dim=True))
        return True
    except Exception as e:
        click.echo(
            f"Warning: Could not read context from {result['path']}: {e}", err=True
        )
        return False


def display_content_with_highlighting(
    result: dict[str, Any],
    config: Any,
    verbose: bool = False,
) -> None:
    """Display chunk content with optional syntax highlighting.

    Args:
        result: Result dictionary with path, start_line, content.
        config: EmberConfig with display settings.
        verbose: Whether to show warning messages on highlighting failure.
    """
    from ember.core.presentation.colors import render_syntax_highlighted

    content = result["content"]

    if config.display.syntax_highlighting:
        try:
            highlighted = render_syntax_highlighted(
                code=content,
                file_path=Path(result["path"]),
                start_line=result["start_line"],
                theme=config.display.theme,
            )
            click.echo(highlighted)
        except Exception as e:
            # Fallback to plain text if highlighting fails
            if verbose:
                click.echo(f"Warning: Syntax highlighting failed: {e}", err=True)
            click.echo(content)
    else:
        # Just display plain content
        click.echo(content)
