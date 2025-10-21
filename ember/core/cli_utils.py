"""CLI utility functions for command-line interface.

Shared utilities to reduce duplication across CLI commands.
"""

import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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


def format_result_header(result: dict[str, Any], index: int, show_symbol: bool = True) -> None:
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
        symbol_display = " " + click.style(f"({result['symbol']})", fg="red", bold=True)

    click.echo(f"{rank} {line_num}:{symbol_display}")


def check_and_auto_sync(
    repo_root: Path,
    db_path: Path,
    config,
    quiet_mode: bool = False,
    verbose: bool = False,
) -> None:
    """Check if index is stale and auto-sync if needed.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        config: Configuration object.
        quiet_mode: If True, suppress progress and messages.
        verbose: If True, show warnings on errors.

    Note:
        If staleness check fails, continues silently to allow search to proceed.
    """
    try:
        # Import dependencies lazily
        from ember.adapters.git_cmd.git_adapter import GitAdapter
        from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
        from ember.core.indexing.index_usecase import IndexRequest

        # Import the usecase creation helper (avoid circular import)
        from ember.entrypoints.cli import _create_indexing_usecase

        vcs = GitAdapter(repo_root)
        meta_repo = SQLiteMetaRepository(db_path)

        # Get current worktree tree SHA
        current_tree_sha = vcs.get_worktree_tree_sha()

        # Get last indexed tree SHA
        last_tree_sha = meta_repo.get("last_tree_sha")

        # If tree SHAs differ, index is stale - auto-sync
        if last_tree_sha != current_tree_sha:
            # Create indexing use case with all dependencies
            indexing_usecase = _create_indexing_usecase(repo_root, db_path, config)

            # Execute incremental sync
            request = IndexRequest(
                repo_root=repo_root,
                sync_mode="worktree",
                path_filters=[],
                force_reindex=False,
            )

            # Use progress bars unless in quiet mode
            with progress_context(quiet_mode=quiet_mode) as progress:
                if progress:
                    response = indexing_usecase.execute(request, progress=progress)
                else:
                    # Silent mode
                    response = indexing_usecase.execute(request)

            # Show completion message AFTER progress context exits (ensures progress bar is cleared)
            if not quiet_mode:
                if response.success:
                    if response.files_indexed > 0:
                        click.echo(
                            f"✓ Synced {response.files_indexed} file(s)",
                            err=True,
                        )
                    else:
                        click.echo("✓ Index up to date", err=True)

    except Exception as e:
        # If staleness check fails, continue with search anyway
        if verbose:
            click.echo(f"Warning: Could not check index staleness: {e}", err=True)


def ensure_daemon_with_progress(
    daemon_timeout: int = 900, quiet: bool = False, startup_timeout: int = 10
) -> bool:
    """Ensure daemon is running, showing progress during startup.

    Args:
        daemon_timeout: Daemon idle timeout in seconds
        quiet: Suppress progress output
        startup_timeout: Seconds to wait for daemon to start

    Returns:
        True if daemon is running, False if failed to start
    """
    from ember.adapters.daemon.client import is_daemon_running
    from ember.adapters.daemon.lifecycle import DaemonLifecycle

    socket_path = Path.home() / ".ember" / "daemon.sock"

    # If already running, nothing to do
    if is_daemon_running(socket_path):
        return True

    # Start daemon with progress feedback
    lifecycle = DaemonLifecycle(
        socket_path=socket_path, idle_timeout=daemon_timeout
    )

    if quiet:
        # No progress, just start
        try:
            return lifecycle.ensure_running()
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
            result = lifecycle.start(foreground=False)

            if result:
                progress.update(task, description="✓ Daemon started")
            return result
        except Exception as e:
            progress.update(task, description=f"✗ Failed to start daemon: {e}")
            return False
