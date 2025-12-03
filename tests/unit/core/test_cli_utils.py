"""Unit tests for CLI utility functions.

Tests for the helper functions extracted from the CLI cat command.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ember.core.cli_utils import (
    display_content_with_context,
    display_content_with_highlighting,
    lookup_result_by_hash,
    lookup_result_from_cache,
)


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

    def test_exits_for_missing_cache(self, tmp_path: Path) -> None:
        """Should exit with error when cache doesn't exist."""
        cache_path = tmp_path / ".last_search.json"

        with pytest.raises(SystemExit):
            lookup_result_from_cache("1", cache_path)

    def test_exits_for_index_out_of_range(self, tmp_path: Path) -> None:
        """Should exit with error when index is out of range."""
        cache_path = tmp_path / ".last_search.json"
        cache_data = {
            "query": "test",
            "results": [{"path": "file1.py", "content": "content1"}],
        }
        cache_path.write_text(json.dumps(cache_data))

        with pytest.raises(SystemExit):
            lookup_result_from_cache("5", cache_path)


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

    def test_exits_for_no_matches(self) -> None:
        """Should exit with error when no chunks match."""
        mock_repo = MagicMock()
        mock_repo.find_by_id_prefix.return_value = []

        with pytest.raises(SystemExit):
            lookup_result_by_hash("abc123", mock_repo)

    def test_exits_for_multiple_matches(self) -> None:
        """Should exit with error when multiple chunks match."""
        mock_chunk1 = MagicMock()
        mock_chunk1.id = "abc123456"
        mock_chunk2 = MagicMock()
        mock_chunk2.id = "abc123789"

        mock_repo = MagicMock()
        mock_repo.find_by_id_prefix.return_value = [mock_chunk1, mock_chunk2]

        with pytest.raises(SystemExit):
            lookup_result_by_hash("abc123", mock_repo)


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
