"""Unit tests for CLI utility functions.

Tests for the helper functions extracted from the CLI cat command.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest

from ember.core.cli_utils import (
    EmberCliError,
    display_content_with_context,
    display_content_with_highlighting,
    index_out_of_range_error,
    lookup_result_by_hash,
    lookup_result_from_cache,
    no_search_results_error,
    normalize_path_filter,
    path_not_in_repo_error,
    repo_not_found_error,
)


class TestEmberCliError:
    """Tests for EmberCliError exception class."""

    def test_error_without_hint(self) -> None:
        """Should format message correctly without hint."""
        error = EmberCliError("Test error message")

        assert error.message == "Test error message"
        assert error.hint is None
        assert error.format_message() == "Test error message"

    def test_error_with_hint(self) -> None:
        """Should format message correctly with hint."""
        error = EmberCliError("Test error message", hint="Try this instead")

        assert error.message == "Test error message"
        assert error.hint == "Try this instead"
        assert error.format_message() == "Test error message\nHint: Try this instead"

    def test_is_click_exception(self) -> None:
        """Should be a ClickException subclass."""
        error = EmberCliError("Test")

        assert isinstance(error, click.ClickException)


class TestErrorHelperFunctions:
    """Tests for error helper functions."""

    def test_repo_not_found_error(self) -> None:
        """Should raise EmberCliError with init hint."""
        with pytest.raises(EmberCliError) as exc_info:
            repo_not_found_error()

        assert "Not in an ember repository" in exc_info.value.message
        assert "ember init" in exc_info.value.hint

    def test_no_search_results_error(self) -> None:
        """Should raise EmberCliError with find hint."""
        with pytest.raises(EmberCliError) as exc_info:
            no_search_results_error()

        assert "No recent search results" in exc_info.value.message
        assert "ember find" in exc_info.value.hint

    def test_path_not_in_repo_error(self) -> None:
        """Should raise EmberCliError with path context."""
        with pytest.raises(EmberCliError) as exc_info:
            path_not_in_repo_error("/some/path")

        assert "/some/path" in exc_info.value.message
        assert "not within repository" in exc_info.value.message
        assert exc_info.value.hint is not None

    def test_index_out_of_range_error(self) -> None:
        """Should raise EmberCliError with valid range hint."""
        with pytest.raises(EmberCliError) as exc_info:
            index_out_of_range_error(15, 10)

        assert "15" in exc_info.value.message
        assert "1-10" in exc_info.value.message
        assert "ember find" in exc_info.value.hint


class TestLookupResultFromCache:
    """Tests for lookup_result_from_cache function."""

    def test_returns_result_for_valid_index(self, tmp_path: Path) -> None:
        """Should return the result at the given index."""
        cache_path = tmp_path / ".last_search.json"
        cache_data = {
            "query": "test",
            "results": [
                {"path": "file1.py", "start_line": 1, "content": "content1"},
                {"path": "file2.py", "start_line": 10, "content": "content2"},
            ],
        }
        cache_path.write_text(json.dumps(cache_data))

        result = lookup_result_from_cache("2", cache_path)

        assert result["path"] == "file2.py"
        assert result["start_line"] == 10

    def test_raises_ember_cli_error_for_missing_cache(self, tmp_path: Path) -> None:
        """Should raise EmberCliError when cache doesn't exist."""
        cache_path = tmp_path / ".last_search.json"

        with pytest.raises(EmberCliError) as exc_info:
            lookup_result_from_cache("1", cache_path)

        assert "No recent search results" in exc_info.value.message
        assert exc_info.value.hint is not None
        assert "ember find" in exc_info.value.hint

    def test_raises_ember_cli_error_for_index_out_of_range(self, tmp_path: Path) -> None:
        """Should raise EmberCliError when index is out of range."""
        cache_path = tmp_path / ".last_search.json"
        cache_data = {
            "query": "test",
            "results": [{"path": "file1.py", "content": "content1"}],
        }
        cache_path.write_text(json.dumps(cache_data))

        with pytest.raises(EmberCliError) as exc_info:
            lookup_result_from_cache("5", cache_path)

        assert "out of range" in exc_info.value.message
        assert exc_info.value.hint is not None


class TestLookupResultByHash:
    """Tests for lookup_result_by_hash function."""

    def test_returns_result_for_unique_match(self) -> None:
        """Should return result when exactly one chunk matches."""
        mock_chunk = MagicMock()
        mock_chunk.path = Path("file.py")
        mock_chunk.start_line = 10
        mock_chunk.end_line = 20
        mock_chunk.content = "test content"
        mock_chunk.lang = "python"
        mock_chunk.symbol = "test_func"

        mock_repo = MagicMock()
        mock_repo.find_by_id_prefix.return_value = [mock_chunk]

        result = lookup_result_by_hash("abc123", mock_repo)

        assert result["path"] == "file.py"
        assert result["start_line"] == 10
        assert result["end_line"] == 20
        assert result["content"] == "test content"
        assert result["lang"] == "python"
        assert result["symbol"] == "test_func"

    def test_raises_ember_cli_error_for_no_matches(self) -> None:
        """Should raise EmberCliError when no chunks match."""
        mock_repo = MagicMock()
        mock_repo.find_by_id_prefix.return_value = []

        with pytest.raises(EmberCliError) as exc_info:
            lookup_result_by_hash("abc123", mock_repo)

        assert "No chunk found" in exc_info.value.message
        assert "abc123" in exc_info.value.message
        assert exc_info.value.hint is not None

    def test_raises_ember_cli_error_for_multiple_matches(self) -> None:
        """Should raise EmberCliError when multiple chunks match."""
        mock_chunk1 = MagicMock()
        mock_chunk1.id = "abc123456"
        mock_chunk2 = MagicMock()
        mock_chunk2.id = "abc123789"

        mock_repo = MagicMock()
        mock_repo.find_by_id_prefix.return_value = [mock_chunk1, mock_chunk2]

        with pytest.raises(EmberCliError) as exc_info:
            lookup_result_by_hash("abc123", mock_repo)

        assert "Ambiguous" in exc_info.value.message
        assert "abc123" in exc_info.value.message
        assert exc_info.value.hint is not None
        assert "longer prefix" in exc_info.value.hint


class TestDisplayContentWithContext:
    """Tests for display_content_with_context function."""

    def test_displays_context_lines(self, tmp_path: Path) -> None:
        """Should display content with surrounding context lines."""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\n")

        result = {
            "path": "test.py",
            "start_line": 3,
            "end_line": 4,
            "content": "line3\nline4",
        }

        # Should return True on success
        success = display_content_with_context(result, context=2, repo_root=tmp_path)
        assert success is True

    def test_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        """Should return False when file doesn't exist."""
        result = {
            "path": "nonexistent.py",
            "start_line": 1,
            "end_line": 5,
            "content": "test",
        }

        success = display_content_with_context(result, context=2, repo_root=tmp_path)
        assert success is False


class TestDisplayContentWithHighlighting:
    """Tests for display_content_with_highlighting function."""

    def test_displays_plain_content_when_highlighting_disabled(self) -> None:
        """Should display plain content when syntax highlighting is off."""
        result = {
            "path": "test.py",
            "start_line": 1,
            "content": "def foo(): pass",
        }

        mock_config = MagicMock()
        mock_config.display.syntax_highlighting = False

        # Should not raise any errors
        display_content_with_highlighting(result, mock_config)

    def test_applies_syntax_highlighting_when_enabled(self) -> None:
        """Should apply syntax highlighting when enabled."""
        result = {
            "path": "test.py",
            "start_line": 1,
            "content": "def foo(): pass",
        }

        mock_config = MagicMock()
        mock_config.display.syntax_highlighting = True
        mock_config.display.theme = "monokai"

        # Should not raise any errors
        display_content_with_highlighting(result, mock_config)

    def test_falls_back_to_plain_on_highlighting_error(self) -> None:
        """Should fall back to plain text if highlighting fails."""
        result = {
            "path": "test.unknown_extension",
            "start_line": 1,
            "content": "some content",
        }

        mock_config = MagicMock()
        mock_config.display.syntax_highlighting = True
        mock_config.display.theme = "invalid_theme_that_should_fail"

        # Should not raise any errors (falls back to plain text)
        display_content_with_highlighting(result, mock_config)


class TestGetEditor:
    """Tests for get_editor function."""

    def test_returns_visual_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return $VISUAL when set."""
        from ember.core.cli_utils import get_editor

        monkeypatch.setenv("VISUAL", "code")
        monkeypatch.setenv("EDITOR", "vim")

        assert get_editor() == "code"

    def test_returns_editor_when_visual_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return $EDITOR when $VISUAL is not set."""
        from ember.core.cli_utils import get_editor

        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "nano")

        assert get_editor() == "nano"

    def test_returns_vim_when_no_env_vars_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 'vim' as default when no env vars are set."""
        from ember.core.cli_utils import get_editor

        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)

        assert get_editor() == "vim"

    def test_returns_empty_visual_falls_through_to_editor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return $EDITOR when $VISUAL is empty string."""
        from ember.core.cli_utils import get_editor

        monkeypatch.setenv("VISUAL", "")
        monkeypatch.setenv("EDITOR", "emacs")

        assert get_editor() == "emacs"

    def test_returns_empty_editor_falls_through_to_vim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return 'vim' when both env vars are empty."""
        from ember.core.cli_utils import get_editor

        monkeypatch.setenv("VISUAL", "")
        monkeypatch.setenv("EDITOR", "")

        assert get_editor() == "vim"


class TestOpenFileInEditor:
    """Tests for open_file_in_editor function."""

    def test_opens_file_in_editor_successfully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should open file in editor when all conditions are met."""
        from ember.core.cli_utils import open_file_in_editor

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        # Mock environment and subprocess
        monkeypatch.setenv("EDITOR", "vim")
        mock_run = MagicMock()
        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/vim")

        # Should succeed without raising
        open_file_in_editor(test_file, line_num=1)

        # Verify subprocess was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "vim" in call_args[0]
        assert str(test_file) in call_args

    def test_raises_for_nonexistent_file(self, tmp_path: Path) -> None:
        """Should raise ClickException when file doesn't exist."""
        from ember.core.cli_utils import open_file_in_editor

        nonexistent = tmp_path / "nonexistent.py"

        with pytest.raises(click.ClickException) as exc_info:
            open_file_in_editor(nonexistent, line_num=1)

        assert "File not found" in str(exc_info.value)

    def test_raises_for_missing_editor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ClickException when editor is not found."""
        from ember.core.cli_utils import open_file_in_editor

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        # Mock shutil.which to return None (editor not found)
        monkeypatch.setattr("shutil.which", lambda x: None)
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)

        with pytest.raises(click.ClickException) as exc_info:
            open_file_in_editor(test_file, line_num=1)

        assert "not found" in str(exc_info.value)
        assert "EDITOR" in str(exc_info.value) or "VISUAL" in str(exc_info.value)

    def test_raises_on_editor_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should raise ClickException when editor fails."""
        import subprocess

        from ember.core.cli_utils import open_file_in_editor

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        # Mock environment
        monkeypatch.setenv("EDITOR", "vim")
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/vim")

        # Mock subprocess to raise CalledProcessError
        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "vim")

        monkeypatch.setattr("subprocess.run", mock_run)

        with pytest.raises(click.ClickException) as exc_info:
            open_file_in_editor(test_file, line_num=1)

        assert "Editor failed" in str(exc_info.value)

    def test_uses_visual_over_editor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should prefer $VISUAL over $EDITOR."""
        from ember.core.cli_utils import open_file_in_editor

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        # Set both VISUAL and EDITOR
        monkeypatch.setenv("VISUAL", "code")
        monkeypatch.setenv("EDITOR", "vim")

        mock_run = MagicMock()
        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        open_file_in_editor(test_file, line_num=1)

        # Verify code (VISUAL) was used, not vim (EDITOR)
        call_args = mock_run.call_args[0][0]
        assert "code" in call_args[0]

    def test_defaults_to_vim(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should default to vim when no env vars set."""
        from ember.core.cli_utils import open_file_in_editor

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        # Clear VISUAL and EDITOR
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)

        mock_run = MagicMock()
        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/vim")

        open_file_in_editor(test_file, line_num=1)

        # Verify vim was used as default
        call_args = mock_run.call_args[0][0]
        assert "vim" in call_args[0]


class TestNormalizePathFilter:
    """Tests for normalize_path_filter function."""

    def test_converts_path_to_glob_pattern(self, tmp_path: Path) -> None:
        """Should convert path argument to glob pattern."""
        repo_root = tmp_path
        cwd = tmp_path / "src"
        cwd.mkdir()

        result = normalize_path_filter(
            path="models",
            existing_filter=None,
            repo_root=repo_root,
            cwd=cwd,
        )

        assert result == "src/models/**"

    def test_converts_dot_path_to_wildcard_glob(self, tmp_path: Path) -> None:
        """Should convert '.' path to wildcard glob when at repo root."""
        repo_root = tmp_path

        result = normalize_path_filter(
            path=".",
            existing_filter=None,
            repo_root=repo_root,
            cwd=repo_root,
        )

        assert result == "*/**"

    def test_converts_subdir_dot_path_to_subdir_glob(self, tmp_path: Path) -> None:
        """Should convert '.' path to subdir glob when in subdirectory."""
        repo_root = tmp_path
        cwd = tmp_path / "src" / "components"
        cwd.mkdir(parents=True)

        result = normalize_path_filter(
            path=".",
            existing_filter=None,
            repo_root=repo_root,
            cwd=cwd,
        )

        assert result == "src/components/**"

    def test_returns_none_when_no_path(self, tmp_path: Path) -> None:
        """Should return None when path is None."""
        result = normalize_path_filter(
            path=None,
            existing_filter=None,
            repo_root=tmp_path,
            cwd=tmp_path,
        )

        assert result is None

    def test_returns_existing_filter_when_no_path(self, tmp_path: Path) -> None:
        """Should return existing filter when path is None."""
        result = normalize_path_filter(
            path=None,
            existing_filter="*.py",
            repo_root=tmp_path,
            cwd=tmp_path,
        )

        assert result == "*.py"

    def test_raises_when_both_path_and_filter_provided(self, tmp_path: Path) -> None:
        """Should raise EmberCliError when both path and filter are provided."""
        with pytest.raises(EmberCliError) as exc_info:
            normalize_path_filter(
                path="src",
                existing_filter="*.py",
                repo_root=tmp_path,
                cwd=tmp_path,
            )

        assert "Cannot use both" in exc_info.value.message
        assert exc_info.value.hint is not None

    def test_raises_when_path_outside_repo(self, tmp_path: Path) -> None:
        """Should raise EmberCliError when path is outside repository."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        outside_path = tmp_path / "outside"
        outside_path.mkdir()

        with pytest.raises(EmberCliError) as exc_info:
            normalize_path_filter(
                path=str(outside_path),
                existing_filter=None,
                repo_root=repo_root,
                cwd=repo_root,
            )

        assert "not within repository" in exc_info.value.message

    def test_handles_absolute_path(self, tmp_path: Path) -> None:
        """Should handle absolute path correctly."""
        repo_root = tmp_path
        target_dir = tmp_path / "src" / "utils"
        target_dir.mkdir(parents=True)

        result = normalize_path_filter(
            path=str(target_dir),
            existing_filter=None,
            repo_root=repo_root,
            cwd=repo_root,
        )

        assert result == "src/utils/**"

    def test_handles_relative_path_from_subdirectory(self, tmp_path: Path) -> None:
        """Should handle relative path from subdirectory correctly."""
        repo_root = tmp_path
        cwd = tmp_path / "src"
        cwd.mkdir()
        target = tmp_path / "src" / "utils"
        target.mkdir()

        result = normalize_path_filter(
            path="utils",
            existing_filter=None,
            repo_root=repo_root,
            cwd=cwd,
        )

        assert result == "src/utils/**"
