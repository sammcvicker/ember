"""Editor adapter for opening files in external editors.

Provides implementation of the Editor port using subprocess for
editor integration with support for line number navigation.
"""

import os
import shutil
import subprocess
from pathlib import Path

from ember.ports.editor import (
    EditorExecutionError,
    EditorFileNotFoundError,
    EditorNotFoundError,
)


def get_editor() -> str:
    """Get the user's preferred editor command.

    Checks environment variables in order of preference:
    1. $VISUAL - for visual/graphical editors
    2. $EDITOR - for terminal editors
    3. 'vim' - default fallback

    Returns:
        The editor command string to use.
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


class SubprocessEditor:
    """Editor implementation using subprocess for external editor integration.

    This is the default implementation of the Editor port, using
    subprocess to launch the user's preferred editor.
    """

    def __init__(self, editor: str | None = None) -> None:
        """Initialize the editor adapter.

        Args:
            editor: Optional explicit editor command. If not provided,
                uses $VISUAL, $EDITOR, or falls back to 'vim'.
        """
        self._editor = editor or get_editor()

    def get_editor_name(self) -> str:
        """Get the name of the configured editor.

        Returns:
            Editor name (e.g., "vim", "code").
        """
        return Path(self._editor).name

    def open_file(self, file_path: Path, line_num: int) -> None:
        """Open a file in the editor at a specific line.

        Args:
            file_path: Absolute path to file to open.
            line_num: Line number to jump to.

        Raises:
            FileNotFoundError: If file doesn't exist.
            EditorNotFoundError: If editor is not available.
            EditorExecutionError: If editor fails to execute.
        """
        # Check file exists
        if not file_path.exists():
            raise EditorFileNotFoundError(
                f"File not found: {file_path}",
                hint="Verify the file path and try again",
            )

        # Check editor is available
        if not shutil.which(self._editor):
            raise EditorNotFoundError(
                f"Editor '{self._editor}' not found",
                hint="Set $EDITOR or $VISUAL environment variable",
            )

        # Build and execute command
        cmd = get_editor_command(self._editor, file_path, line_num)

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise EditorExecutionError(
                f"Editor failed with exit code {e.returncode}",
                hint="Check if the file is accessible and try again",
            ) from e


def open_file_in_editor(file_path: Path, line_num: int) -> None:
    """Open a file in the user's editor at a specific line.

    Convenience function that creates a SubprocessEditor and opens the file.
    This is the default way to open files in an editor.

    Args:
        file_path: Absolute path to file to open.
        line_num: Line number to jump to.

    Raises:
        FileNotFoundError: If file not found.
        EditorNotFoundError: If editor not found.
        EditorExecutionError: If editor fails.
    """
    editor = SubprocessEditor()
    editor.open_file(file_path, line_num)
