"""Editor integration for opening files at specific lines.

This module is a facade that re-exports editor utilities from the adapter layer.
It handles conversion of domain exceptions to CLI exceptions for backward
compatibility with existing code.

For new code, prefer using the adapter directly when domain exceptions
are more appropriate.
"""

from pathlib import Path

import click

from ember.adapters.editor import (
    EDITOR_PATTERNS,
    get_editor,
    get_editor_command,
)
from ember.adapters.editor import open_file_in_editor as _open_file_in_editor
from ember.ports.editor import (
    EditorError,
    EditorExecutionError,
    EditorFileNotFoundError,
    EditorNotFoundError,
)

# Re-export for backward compatibility
__all__ = [
    "get_editor",
    "get_editor_command",
    "open_file_in_editor",
    "EDITOR_PATTERNS",
]


def open_file_in_editor(file_path: Path, line_num: int) -> None:
    """Open a file in the user's editor at a specific line.

    Uses $VISUAL, then $EDITOR, then falls back to vim.

    Args:
        file_path: Absolute path to file to open.
        line_num: Line number to jump to.

    Raises:
        click.ClickException: If file not found, editor not found, or editor fails.
    """
    try:
        _open_file_in_editor(file_path, line_num)
    except EditorFileNotFoundError as e:
        raise click.ClickException(e.message) from e
    except EditorNotFoundError as e:
        msg = e.message
        if e.hint:
            msg = f"{msg}. {e.hint}"
        raise click.ClickException(msg) from e
    except EditorExecutionError as e:
        raise click.ClickException(f"Editor failed: {e.message}") from e
    except EditorError as e:
        raise click.ClickException(e.message) from e
