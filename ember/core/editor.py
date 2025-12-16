"""Editor integration for opening files at specific lines.

Provides cross-editor support for opening files at specific line numbers,
with automatic detection of editor command syntax.
"""

import os
import shutil
import subprocess
from pathlib import Path

import click


def get_editor() -> str:
    """Get the user's preferred editor command.

    Checks environment variables in order of preference:
    1. $VISUAL - for visual/graphical editors
    2. $EDITOR - for terminal editors
    3. 'vim' - default fallback

    Returns:
        The editor command string to use.

    Example:
        >>> editor = get_editor()
        >>> print(f"Opening in {editor}...")
    """
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"


# Editor command patterns for opening files at specific line numbers
EDITOR_PATTERNS = {
    # Editors that use +line syntax (vim, emacs, nano)
    "vim-style": {
        "editors": ["vim", "vi", "nvim", "emacs", "emacsclient", "nano"],
        "build": lambda ed, fp, ln: [ed, f"+{ln}", str(fp)],
    },
    # VS Code: --goto file:line
    "vscode-style": {
        "editors": ["code", "vscode"],
        "build": lambda ed, fp, ln: [ed, "--goto", f"{fp}:{ln}"],
    },
    # Sublime Text and Atom: file:line
    "colon-style": {
        "editors": ["subl", "atom"],
        "build": lambda ed, fp, ln: [ed, f"{fp}:{ln}"],
    },
}


def get_editor_command(editor: str, file_path: Path, line_num: int) -> list[str]:
    """Build editor command with line number support.

    Args:
        editor: Editor executable name or path.
        file_path: Path to file to open.
        line_num: Line number to jump to.

    Returns:
        Command list for subprocess.run().

    Note:
        Falls back to vim-style +line syntax for unknown editors.
    """
    editor_name = Path(editor).name.lower()

    # Find matching pattern
    for pattern in EDITOR_PATTERNS.values():
        if editor_name in pattern["editors"]:
            return pattern["build"](editor, file_path, line_num)

    # Default: vim-style +line syntax (most widely supported)
    return [editor, f"+{line_num}", str(file_path)]


def open_file_in_editor(file_path: Path, line_num: int) -> None:
    """Open a file in the user's editor at a specific line.

    Uses $VISUAL, then $EDITOR, then falls back to vim.

    Args:
        file_path: Absolute path to file to open.
        line_num: Line number to jump to.

    Raises:
        click.ClickException: If file not found, editor not found, or editor fails.
    """
    # Check file exists
    if not file_path.exists():
        raise click.ClickException(f"File not found: {file_path}")

    # Determine editor (priority: $VISUAL > $EDITOR > vim)
    editor = get_editor()

    # Check editor is available
    if not shutil.which(editor):
        raise click.ClickException(
            f"Editor '{editor}' not found. Set $EDITOR or $VISUAL environment variable"
        )

    # Build and execute command
    cmd = get_editor_command(editor, file_path, line_num)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"Editor failed: {e}") from e
