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
    from ember.ports.daemon import DaemonManager


# Re-export highlight_symbol for backward compatibility
__all__ = ["RichProgressCallback", "progress_context", "load_cached_results",
           "validate_result_index", "highlight_symbol", "format_result_header",
           "ensure_daemon_with_progress"]


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


def format_result_header(result: dict[str, Any], index: int, show_symbol: bool = True) -> None:
    """Print result header in consistent ripgrep-style format.

    Args:
        result: Result dictionary with path, start_line, symbol fields.
        index: 1-based result index (rank).
        show_symbol: Whether to display symbol in header.
    """
    # Filename using centralized color
    click.echo(EmberColors.click_path(str(result["path"])))

    # Rank and line number using centralized colors
    rank = EmberColors.click_rank(f"[{index}]")
    line_num = EmberColors.click_line_number(f"{result['start_line']}")

    # Symbol using centralized color (inline)
    symbol_display = ""
    if show_symbol and result.get("symbol"):
        symbol_display = " " + EmberColors.click_symbol(f"({result['symbol']})")

    click.echo(f"{rank} {line_num}:{symbol_display}")


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
