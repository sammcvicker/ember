"""Progress reporting utilities for CLI commands.

Provides Rich-based progress bars and context managers for visual feedback
during long-running operations.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

if TYPE_CHECKING:
    from ember.ports.daemon import DaemonManager

logger = logging.getLogger(__name__)


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
        except (OSError, RuntimeError):
            # OS-level errors or daemon startup failures
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
                progress.update(task, description="Daemon started")
            return result
        except (OSError, RuntimeError) as e:
            # OSError: socket/process failures, RuntimeError: daemon startup failures
            logger.warning("Failed to start daemon", exc_info=True)
            progress.update(task, description=f"Failed to start daemon: {e}")
            return False
