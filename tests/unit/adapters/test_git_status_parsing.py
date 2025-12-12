"""Unit tests for git status code parsing in GitAdapter.

Tests the _parse_status_code helper function which converts git diff-tree
status codes to FileStatus values and extracts paths.
"""

from pathlib import Path

from ember.adapters.git_cmd.git_adapter import _parse_status_code


class TestParseStatusCode:
    """Tests for _parse_status_code function."""

    # Exact match status codes

    def test_added_file(self):
        """Test parsing 'A' (added) status code."""
        parts = ["A", "new_file.py"]
        result = _parse_status_code(parts)
        assert result == ("added", Path("new_file.py"))

    def test_deleted_file(self):
        """Test parsing 'D' (deleted) status code."""
        parts = ["D", "removed_file.py"]
        result = _parse_status_code(parts)
        assert result == ("deleted", Path("removed_file.py"))

    def test_modified_file(self):
        """Test parsing 'M' (modified) status code."""
        parts = ["M", "changed_file.py"]
        result = _parse_status_code(parts)
        assert result == ("modified", Path("changed_file.py"))

    def test_type_change(self):
        """Test parsing 'T' (type change) status code - treated as modified."""
        parts = ["T", "type_changed.py"]
        result = _parse_status_code(parts)
        assert result == ("modified", Path("type_changed.py"))

    # Prefix match status codes (R###, C###)

    def test_rename_with_similarity(self):
        """Test parsing rename with similarity score (R100, R090, etc.)."""
        parts = ["R100", "old_name.py", "new_name.py"]
        result = _parse_status_code(parts)
        assert result == ("renamed", Path("new_name.py"))

    def test_rename_partial_similarity(self):
        """Test parsing rename with partial similarity."""
        parts = ["R075", "original.py", "renamed.py"]
        result = _parse_status_code(parts)
        assert result == ("renamed", Path("renamed.py"))

    def test_rename_fallback_to_first_path(self):
        """Test rename falls back to first path if second is missing."""
        parts = ["R100", "only_path.py"]
        result = _parse_status_code(parts)
        assert result == ("renamed", Path("only_path.py"))

    def test_copy_with_similarity(self):
        """Test parsing copy status (C###) - treated as added."""
        parts = ["C100", "source.py", "copied.py"]
        result = _parse_status_code(parts)
        assert result == ("added", Path("copied.py"))

    def test_copy_fallback_to_first_path(self):
        """Test copy falls back to first path if second is missing."""
        parts = ["C050", "only_path.py"]
        result = _parse_status_code(parts)
        assert result == ("added", Path("only_path.py"))

    # Unknown status codes

    def test_unknown_status_code_returns_none(self):
        """Test that unknown status codes return None."""
        parts = ["X", "some_file.py"]
        result = _parse_status_code(parts)
        assert result is None

    def test_unknown_prefix_status_code_returns_none(self):
        """Test that unknown prefix status codes return None."""
        parts = ["U100", "some_file.py"]
        result = _parse_status_code(parts)
        assert result is None

    # Edge cases

    def test_path_with_spaces(self):
        """Test parsing paths containing spaces."""
        parts = ["A", "path with spaces/file.py"]
        result = _parse_status_code(parts)
        assert result == ("added", Path("path with spaces/file.py"))

    def test_nested_path(self):
        """Test parsing deeply nested paths."""
        parts = ["M", "src/utils/helpers/string_utils.py"]
        result = _parse_status_code(parts)
        assert result == ("modified", Path("src/utils/helpers/string_utils.py"))

    def test_dotfile(self):
        """Test parsing dotfiles."""
        parts = ["A", ".gitignore"]
        result = _parse_status_code(parts)
        assert result == ("added", Path(".gitignore"))

    def test_rename_in_subdirectory(self):
        """Test parsing rename where files are in subdirectories."""
        parts = ["R100", "src/old.py", "src/new.py"]
        result = _parse_status_code(parts)
        assert result == ("renamed", Path("src/new.py"))
