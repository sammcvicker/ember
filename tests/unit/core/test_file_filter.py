"""Unit tests for FileFilterService.

Tests for file filtering based on extensions and glob patterns.
"""

from pathlib import Path

import pytest

from ember.core.indexing.file_filter import FileFilterService
from ember.core.languages import get_code_file_extensions


@pytest.fixture
def file_filter() -> FileFilterService:
    """Create FileFilterService instance."""
    return FileFilterService()


class TestIsCodeFile:
    """Tests for is_code_file method."""

    def test_python_files_are_code(self, file_filter: FileFilterService) -> None:
        """Python files (.py, .pyi) are recognized as code."""
        assert file_filter.is_code_file(Path("app.py"))
        assert file_filter.is_code_file(Path("stubs.pyi"))

    def test_javascript_files_are_code(self, file_filter: FileFilterService) -> None:
        """JavaScript/TypeScript files are recognized as code."""
        assert file_filter.is_code_file(Path("app.js"))
        assert file_filter.is_code_file(Path("app.jsx"))
        assert file_filter.is_code_file(Path("app.ts"))
        assert file_filter.is_code_file(Path("app.tsx"))
        assert file_filter.is_code_file(Path("module.mjs"))
        assert file_filter.is_code_file(Path("module.cjs"))

    def test_go_files_are_code(self, file_filter: FileFilterService) -> None:
        """Go files are recognized as code."""
        assert file_filter.is_code_file(Path("main.go"))

    def test_rust_files_are_code(self, file_filter: FileFilterService) -> None:
        """Rust files are recognized as code."""
        assert file_filter.is_code_file(Path("lib.rs"))

    def test_c_cpp_files_are_code(self, file_filter: FileFilterService) -> None:
        """C/C++ files are recognized as code."""
        assert file_filter.is_code_file(Path("main.c"))
        assert file_filter.is_code_file(Path("main.cpp"))
        assert file_filter.is_code_file(Path("main.cc"))
        assert file_filter.is_code_file(Path("main.cxx"))
        assert file_filter.is_code_file(Path("header.h"))
        assert file_filter.is_code_file(Path("header.hpp"))
        assert file_filter.is_code_file(Path("header.hh"))
        assert file_filter.is_code_file(Path("header.hxx"))

    def test_json_files_are_not_code(self, file_filter: FileFilterService) -> None:
        """JSON files are not recognized as code."""
        assert not file_filter.is_code_file(Path("config.json"))

    def test_markdown_files_are_not_code(self, file_filter: FileFilterService) -> None:
        """Markdown files are not recognized as code."""
        assert not file_filter.is_code_file(Path("README.md"))

    def test_image_files_are_not_code(self, file_filter: FileFilterService) -> None:
        """Image files are not recognized as code."""
        assert not file_filter.is_code_file(Path("logo.png"))
        assert not file_filter.is_code_file(Path("photo.jpg"))

    def test_case_insensitive(self, file_filter: FileFilterService) -> None:
        """Extension matching is case-insensitive."""
        assert file_filter.is_code_file(Path("app.PY"))
        assert file_filter.is_code_file(Path("app.Py"))


class TestFilterCodeFiles:
    """Tests for filter_code_files method."""

    def test_filters_to_code_files_only(self, file_filter: FileFilterService) -> None:
        """Returns only code files from the list."""
        files = [
            Path("app.py"),
            Path("config.json"),
            Path("README.md"),
            Path("utils.ts"),
            Path("data.csv"),
            Path("main.go"),
            Path("logo.png"),
        ]

        result = file_filter.filter_code_files(files)

        assert set(result) == {Path("app.py"), Path("utils.ts"), Path("main.go")}

    def test_empty_list_returns_empty(self, file_filter: FileFilterService) -> None:
        """Empty input returns empty output."""
        result = file_filter.filter_code_files([])

        assert result == []

    def test_all_code_files_returns_all(self, file_filter: FileFilterService) -> None:
        """All code files are returned unchanged."""
        files = [Path("a.py"), Path("b.js"), Path("c.go")]

        result = file_filter.filter_code_files(files)

        assert result == files

    def test_no_code_files_returns_empty(self, file_filter: FileFilterService) -> None:
        """No code files returns empty list."""
        files = [Path("config.json"), Path("README.md"), Path("logo.png")]

        result = file_filter.filter_code_files(files)

        assert result == []


class TestApplyPathFilters:
    """Tests for apply_path_filters method."""

    def test_single_pattern_filters_correctly(
        self, file_filter: FileFilterService
    ) -> None:
        """Single pattern filters files correctly."""
        repo_root = Path("/repo")
        files = [
            Path("/repo/src/app.py"),
            Path("/repo/src/utils.py"),
            Path("/repo/tests/test_app.py"),
            Path("/repo/docs/readme.py"),
        ]

        result = file_filter.apply_path_filters(files, ["src/*.py"], repo_root)

        assert set(f.name for f in result) == {"app.py", "utils.py"}

    def test_multiple_patterns_use_or_logic(
        self, file_filter: FileFilterService
    ) -> None:
        """Multiple patterns use OR logic."""
        repo_root = Path("/repo")
        files = [
            Path("/repo/src/app.py"),
            Path("/repo/tests/test_app.py"),
            Path("/repo/docs/readme.py"),
        ]

        result = file_filter.apply_path_filters(
            files, ["src/*.py", "tests/*.py"], repo_root
        )

        assert set(f.name for f in result) == {"app.py", "test_app.py"}

    def test_glob_star_star_matches_any_depth(
        self, file_filter: FileFilterService
    ) -> None:
        """Glob ** matches any directory depth."""
        repo_root = Path("/repo")
        files = [
            Path("/repo/src/app.py"),
            Path("/repo/src/core/utils.py"),
            Path("/repo/src/core/deep/nested.py"),
            Path("/repo/tests/test_app.py"),
        ]

        result = file_filter.apply_path_filters(files, ["**/*.py"], repo_root)

        assert len(result) == 4

    def test_no_match_returns_empty(self, file_filter: FileFilterService) -> None:
        """No matches returns empty list."""
        repo_root = Path("/repo")
        files = [
            Path("/repo/src/app.py"),
            Path("/repo/src/utils.py"),
        ]

        result = file_filter.apply_path_filters(files, ["nonexistent/*.py"], repo_root)

        assert result == []

    def test_files_outside_repo_are_skipped(
        self, file_filter: FileFilterService
    ) -> None:
        """Files not relative to repo_root are silently skipped."""
        repo_root = Path("/repo")
        files = [
            Path("/repo/src/app.py"),
            Path("/other/project/file.py"),  # Not in repo
        ]

        result = file_filter.apply_path_filters(files, ["**/*.py"], repo_root)

        assert result == [Path("/repo/src/app.py")]


class TestCodeFileExtensions:
    """Tests for code file extensions via language registry."""

    def test_contains_common_languages(self) -> None:
        """Registry contains extensions for common languages."""
        common = {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".rb"}
        code_extensions = get_code_file_extensions()
        assert common.issubset(code_extensions)

    def test_is_frozenset(self) -> None:
        """Code extensions are returned as frozenset for immutability and fast lookups."""
        code_extensions = get_code_file_extensions()
        assert isinstance(code_extensions, frozenset)
