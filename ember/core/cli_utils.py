"""CLI utility functions for command-line interface.

Shared utilities to reduce duplication across CLI commands.
"""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import click
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn


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
        self.task_id = self.progress.add_task(description, total=total)

    def on_progress(self, current: int, item_description: str | None = None) -> None:
        """Update progress bar with current item."""
        if self.task_id is not None:
            # Update the task description to show current file
            if item_description:
                self.progress.update(
                    self.task_id, completed=current, description=f"[cyan]{item_description}"
                )
            else:
                self.progress.update(self.task_id, completed=current)

    def on_complete(self) -> None:
        """Mark progress as complete and hide it."""
        if self.task_id is not None:
            # Remove the task to hide the progress bar
            self.progress.remove_task(self.task_id)


@contextmanager
def progress_context(quiet_mode: bool = False) -> Generator[RichProgressCallback | None, None, None]:
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
        click.echo(
            f"Error: Index {index} out of range (1-{len(results)})", err=True
        )
        sys.exit(1)

    # Get the result (convert to 0-based)
    return results[index - 1]


def highlight_symbol(text: str, symbol: str | None) -> str:
    """Highlight all occurrences of symbol in text.

    Args:
        text: Text to search for symbol.
        symbol: Symbol to highlight (or None).

    Returns:
        Text with symbol highlighted in red bold.
    """
    if not symbol or symbol not in text:
        return text

    # Find and highlight all occurrences of the symbol
    parts = []
    remaining = text
    while symbol in remaining:
        idx = remaining.index(symbol)
        # Add text before symbol
        parts.append(remaining[:idx])
        # Add highlighted symbol
        parts.append(click.style(symbol, fg="red", bold=True))
        # Continue with text after symbol
        remaining = remaining[idx + len(symbol) :]
    # Add any remaining text
    parts.append(remaining)
    return "".join(parts)


def format_result_header(
    result: dict[str, Any], index: int, show_symbol: bool = True
) -> None:
    """Print result header in consistent ripgrep-style format.

    Args:
        result: Result dictionary with path, start_line, symbol fields.
        index: 1-based result index (rank).
        show_symbol: Whether to display symbol in header.
    """
    # Filename in magenta bold
    click.echo(click.style(str(result["path"]), fg="magenta", bold=True))

    # Rank in green bold, line number dimmed
    rank = click.style(f"[{index}]", fg="green", bold=True)
    line_num = click.style(f"{result['start_line']}", dim=True)

    # Symbol in red bold (inline)
    symbol_display = ""
    if show_symbol and result.get("symbol"):
        symbol_display = " " + click.style(
            f"({result['symbol']})", fg="red", bold=True
        )

    click.echo(f"{rank} {line_num}:{symbol_display}")
