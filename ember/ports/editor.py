"""Editor port interface for opening files in external editors.

Defines abstract interface for editor operations, allowing different
implementations for different platforms or testing.
"""

from pathlib import Path
from typing import Protocol


class EditorError(Exception):
    """Base exception for editor-related errors.

    Attributes:
        message: User-facing error message.
        hint: Optional actionable suggestion.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class EditorFileNotFoundError(EditorError):
    """Raised when file to open doesn't exist."""

    pass


class EditorNotFoundError(EditorError):
    """Raised when the configured editor is not available."""

    pass


class EditorExecutionError(EditorError):
    """Raised when the editor fails to execute."""

    pass


class Editor(Protocol):
    """Protocol for editor operations.

    Abstracts file editor integration to allow different implementations
    and easier testing.
    """

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
        ...

    def get_editor_name(self) -> str:
        """Get the name of the configured editor.

        Returns:
            Editor name (e.g., "vim", "code").
        """
        ...
