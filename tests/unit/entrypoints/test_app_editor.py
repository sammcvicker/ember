"""Unit tests for the app/editor.py facade.

Tests that CLI-level error handling correctly converts domain exceptions
(EditorError subtypes) to click.ClickException for user-friendly error messages.
"""

from pathlib import Path
from unittest.mock import patch

import click
import pytest

from ember.app.editor import open_file_in_editor
from ember.ports.editor import (
    EditorError,
    EditorExecutionError,
    EditorFileNotFoundError,
    EditorNotFoundError,
)


class TestAppEditorErrorHandling:
    """Tests for exception conversion in the app editor facade."""

    def test_file_not_found_converts_to_click_exception(self) -> None:
        """EditorFileNotFoundError is converted to click.ClickException."""
        error = EditorFileNotFoundError(
            "File not found: /tmp/missing.py",
            hint="Check the path",
        )

        with patch(
            "ember.app.editor._open_file_in_editor",
            side_effect=error,
        ):
            with pytest.raises(click.ClickException) as exc_info:
                open_file_in_editor(Path("/tmp/missing.py"), 1)

            assert "File not found" in str(exc_info.value.message)

    def test_editor_not_found_converts_with_hint(self) -> None:
        """EditorNotFoundError is converted with hint appended to message."""
        error = EditorNotFoundError(
            "Editor 'myeditor' not found",
            hint="Set $EDITOR or $VISUAL environment variable",
        )

        with patch(
            "ember.app.editor._open_file_in_editor",
            side_effect=error,
        ):
            with pytest.raises(click.ClickException) as exc_info:
                open_file_in_editor(Path("/tmp/test.py"), 1)

            msg = str(exc_info.value.message)
            assert "Editor 'myeditor' not found" in msg
            assert "Set $EDITOR" in msg

    def test_editor_not_found_without_hint(self) -> None:
        """EditorNotFoundError without hint uses message only."""
        error = EditorNotFoundError(
            "Editor 'myeditor' not found",
            hint=None,
        )

        with patch(
            "ember.app.editor._open_file_in_editor",
            side_effect=error,
        ):
            with pytest.raises(click.ClickException) as exc_info:
                open_file_in_editor(Path("/tmp/test.py"), 1)

            msg = str(exc_info.value.message)
            assert "Editor 'myeditor' not found" in msg

    def test_execution_error_converts_with_prefix(self) -> None:
        """EditorExecutionError is converted with 'Editor failed:' prefix."""
        error = EditorExecutionError(
            "Editor failed with exit code 1",
            hint="Check if the file is accessible",
        )

        with patch(
            "ember.app.editor._open_file_in_editor",
            side_effect=error,
        ):
            with pytest.raises(click.ClickException) as exc_info:
                open_file_in_editor(Path("/tmp/test.py"), 1)

            msg = str(exc_info.value.message)
            assert "Editor failed:" in msg

    def test_generic_editor_error_converts(self) -> None:
        """Base EditorError is converted to click.ClickException."""
        error = EditorError("Something went wrong")

        with patch(
            "ember.app.editor._open_file_in_editor",
            side_effect=error,
        ):
            with pytest.raises(click.ClickException) as exc_info:
                open_file_in_editor(Path("/tmp/test.py"), 1)

            assert "Something went wrong" in str(exc_info.value.message)

    def test_success_does_not_raise(self) -> None:
        """No exception when underlying call succeeds."""
        with patch(
            "ember.app.editor._open_file_in_editor",
            return_value=None,
        ):
            # Should not raise
            open_file_in_editor(Path("/tmp/test.py"), 1)
