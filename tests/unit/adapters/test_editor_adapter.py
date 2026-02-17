"""Unit tests for the editor adapter (SubprocessEditor).

Tests cover:
- get_editor() environment variable lookup
- get_editor_command() for various editor types
- SubprocessEditor.open_file() with mocked subprocess
- SubprocessEditor.get_editor_name()
- Error handling for missing files, missing editors, and execution failures
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ember.adapters.editor import (
    EDITOR_PATTERNS,
    SubprocessEditor,
    get_editor,
    get_editor_command,
    open_file_in_editor,
)
from ember.ports.editor import (
    EditorExecutionError,
    EditorFileNotFoundError,
    EditorNotFoundError,
)


class TestGetEditor:
    """Tests for get_editor() environment variable lookup."""

    def test_returns_visual_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """VISUAL takes priority over EDITOR."""
        monkeypatch.setenv("VISUAL", "code")
        monkeypatch.setenv("EDITOR", "vim")
        assert get_editor() == "code"

    def test_returns_editor_when_visual_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EDITOR is used when VISUAL is not set."""
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "nano")
        assert get_editor() == "nano"

    def test_returns_vim_as_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to vim when neither VISUAL nor EDITOR is set."""
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)
        assert get_editor() == "vim"

    def test_returns_editor_when_visual_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty VISUAL falls through to EDITOR."""
        monkeypatch.setenv("VISUAL", "")
        monkeypatch.setenv("EDITOR", "emacs")
        assert get_editor() == "emacs"

    def test_returns_vim_when_both_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty VISUAL and empty EDITOR fall back to vim."""
        monkeypatch.setenv("VISUAL", "")
        monkeypatch.setenv("EDITOR", "")
        assert get_editor() == "vim"


class TestGetEditorCommand:
    """Tests for get_editor_command() command building."""

    def test_vim_style_editors(self) -> None:
        """Vim-style editors use +line syntax."""
        for editor in ["vim", "vi", "nvim", "emacs", "emacsclient", "nano"]:
            cmd = get_editor_command(editor, Path("/tmp/test.py"), 42)
            assert cmd == [editor, "+42", "/tmp/test.py"]

    def test_vscode_style_editors(self) -> None:
        """VS Code uses --goto file:line syntax."""
        for editor in ["code", "vscode"]:
            cmd = get_editor_command(editor, Path("/tmp/test.py"), 42)
            assert cmd == [editor, "--goto", "/tmp/test.py:42"]

    def test_colon_style_editors(self) -> None:
        """Sublime and Atom use file:line syntax."""
        for editor in ["subl", "atom"]:
            cmd = get_editor_command(editor, Path("/tmp/test.py"), 42)
            assert cmd == [editor, "/tmp/test.py:42"]

    def test_unknown_editor_uses_vim_style_fallback(self) -> None:
        """Unknown editors fall back to vim-style +line."""
        cmd = get_editor_command("my-custom-editor", Path("/tmp/test.py"), 42)
        assert cmd == ["my-custom-editor", "+42", "/tmp/test.py"]

    def test_editor_with_full_path(self) -> None:
        """Editors specified with full path are matched by basename."""
        cmd = get_editor_command("/usr/bin/vim", Path("/tmp/test.py"), 42)
        assert cmd == ["/usr/bin/vim", "+42", "/tmp/test.py"]

    def test_line_number_one(self) -> None:
        """Line number 1 is handled correctly."""
        cmd = get_editor_command("vim", Path("/tmp/test.py"), 1)
        assert cmd == ["vim", "+1", "/tmp/test.py"]

    def test_large_line_number(self) -> None:
        """Large line numbers are formatted correctly."""
        cmd = get_editor_command("code", Path("/tmp/test.py"), 99999)
        assert cmd == ["code", "--goto", "/tmp/test.py:99999"]


class TestEditorPatterns:
    """Tests for EDITOR_PATTERNS constant."""

    def test_all_pattern_groups_have_required_keys(self) -> None:
        """Each pattern group should have 'editors' list and 'build' callable."""
        for name, pattern in EDITOR_PATTERNS.items():
            assert "editors" in pattern, f"Pattern '{name}' missing 'editors'"
            assert "build" in pattern, f"Pattern '{name}' missing 'build'"
            assert callable(pattern["build"]), f"Pattern '{name}' build is not callable"
            assert isinstance(pattern["editors"], list), f"Pattern '{name}' editors is not a list"

    def test_no_duplicate_editors_across_patterns(self) -> None:
        """No editor should appear in multiple pattern groups."""
        seen = set()
        for _name, pattern in EDITOR_PATTERNS.items():
            for editor in pattern["editors"]:
                assert editor not in seen, (
                    f"Editor '{editor}' appears in multiple pattern groups"
                )
                seen.add(editor)


class TestSubprocessEditorInit:
    """Tests for SubprocessEditor initialization."""

    def test_uses_provided_editor(self) -> None:
        """Constructor uses explicitly provided editor."""
        editor = SubprocessEditor(editor="nano")
        assert editor.get_editor_name() == "nano"

    def test_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Constructor falls back to get_editor() when no editor provided."""
        monkeypatch.setenv("EDITOR", "emacs")
        monkeypatch.delenv("VISUAL", raising=False)
        editor = SubprocessEditor()
        assert editor.get_editor_name() == "emacs"

    def test_uses_full_path_returns_basename(self) -> None:
        """get_editor_name returns just the basename from a full path."""
        editor = SubprocessEditor(editor="/usr/local/bin/nvim")
        assert editor.get_editor_name() == "nvim"


class TestSubprocessEditorOpenFile:
    """Tests for SubprocessEditor.open_file() method."""

    def test_open_file_success(self, tmp_path: Path) -> None:
        """Successfully opens a file with subprocess."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass\n")

        editor = SubprocessEditor(editor="vim")

        with (
            patch("ember.adapters.editor.shutil.which", return_value="/usr/bin/vim"),
            patch("ember.adapters.editor.subprocess.run") as mock_run,
        ):
            editor.open_file(test_file, 1)

            mock_run.assert_called_once_with(
                ["vim", "+1", str(test_file)],
                check=True,
            )

    def test_open_file_at_specific_line(self, tmp_path: Path) -> None:
        """Opens file at the specified line number."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        editor = SubprocessEditor(editor="code")

        with (
            patch("ember.adapters.editor.shutil.which", return_value="/usr/bin/code"),
            patch("ember.adapters.editor.subprocess.run") as mock_run,
        ):
            editor.open_file(test_file, 25)

            mock_run.assert_called_once_with(
                ["code", "--goto", f"{test_file}:25"],
                check=True,
            )

    def test_open_file_raises_for_missing_file(self, tmp_path: Path) -> None:
        """Raises EditorFileNotFoundError when file does not exist."""
        nonexistent = tmp_path / "does_not_exist.py"

        editor = SubprocessEditor(editor="vim")

        with pytest.raises(EditorFileNotFoundError, match="File not found"):
            editor.open_file(nonexistent, 1)

    def test_open_file_raises_for_missing_editor(self, tmp_path: Path) -> None:
        """Raises EditorNotFoundError when editor is not on PATH."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        editor = SubprocessEditor(editor="nonexistent-editor")

        with (
            patch("ember.adapters.editor.shutil.which", return_value=None),
            pytest.raises(EditorNotFoundError, match="not found"),
        ):
            editor.open_file(test_file, 1)

    def test_open_file_raises_on_subprocess_failure(self, tmp_path: Path) -> None:
        """Raises EditorExecutionError when subprocess exits with error."""
        import subprocess

        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        editor = SubprocessEditor(editor="vim")

        with (
            patch("ember.adapters.editor.shutil.which", return_value="/usr/bin/vim"),
            patch(
                "ember.adapters.editor.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "vim"),
            ),
            pytest.raises(EditorExecutionError, match="exit code 1"),
        ):
            editor.open_file(test_file, 1)

    def test_editor_not_found_error_includes_hint(self, tmp_path: Path) -> None:
        """EditorNotFoundError includes an actionable hint."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        editor = SubprocessEditor(editor="fake-editor")

        with (
            patch("ember.adapters.editor.shutil.which", return_value=None),
            pytest.raises(EditorNotFoundError) as exc_info,
        ):
            editor.open_file(test_file, 1)

        assert exc_info.value.hint is not None
        assert "EDITOR" in exc_info.value.hint or "VISUAL" in exc_info.value.hint

    def test_file_not_found_error_includes_hint(self, tmp_path: Path) -> None:
        """EditorFileNotFoundError includes an actionable hint."""
        nonexistent = tmp_path / "nope.py"

        editor = SubprocessEditor(editor="vim")

        with pytest.raises(EditorFileNotFoundError) as exc_info:
            editor.open_file(nonexistent, 1)

        assert exc_info.value.hint is not None
        assert "path" in exc_info.value.hint.lower() or "verify" in exc_info.value.hint.lower()


class TestOpenFileInEditor:
    """Tests for the convenience function open_file_in_editor()."""

    def test_creates_editor_and_calls_open(self, tmp_path: Path) -> None:
        """Convenience function delegates to SubprocessEditor.open_file()."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        with (
            patch("ember.adapters.editor.shutil.which", return_value="/usr/bin/vim"),
            patch("ember.adapters.editor.subprocess.run") as mock_run,
        ):
            open_file_in_editor(test_file, 1)
            mock_run.assert_called_once()

    def test_propagates_errors(self, tmp_path: Path) -> None:
        """Convenience function propagates editor errors."""
        nonexistent = tmp_path / "missing.py"

        with pytest.raises(EditorFileNotFoundError):
            open_file_in_editor(nonexistent, 1)
