"""Unit tests for IndexingUseCase._get_files_to_index method.

These tests verify the file selection logic in isolation using mocks,
covering all edge cases before refactoring the method for lower complexity.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from ember.core.indexing.index_usecase import IndexingUseCase


@pytest.fixture
def mock_vcs() -> Mock:
    """Create a mock VCS adapter."""
    return Mock()


@pytest.fixture
def mock_meta_repo() -> Mock:
    """Create a mock MetaRepository."""
    return Mock()


@pytest.fixture
def mock_deps() -> dict:
    """Create minimal mock dependencies for IndexingUseCase."""
    return {
        "vcs": Mock(),
        "fs": Mock(),
        "chunk_usecase": Mock(),
        "embedder": Mock(),
        "chunk_repo": Mock(),
        "vector_repo": Mock(),
        "file_repo": Mock(),
        "meta_repo": Mock(),
        "project_id": "test_project",
    }


@pytest.fixture
def indexing_usecase(mock_deps: dict) -> IndexingUseCase:
    """Create IndexingUseCase with mock dependencies."""
    return IndexingUseCase(**mock_deps)


class TestGetFilesToIndexFullReindex:
    """Tests for full reindex scenarios."""

    def test_force_reindex_returns_all_tracked_files(
        self, mock_deps: dict
    ) -> None:
        """When force_reindex=True, return all tracked files."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["vcs"].list_tracked_files.return_value = [
            "src/app.py",
            "src/utils.py",
            "tests/test_app.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=[],
            force_reindex=True,
        )

        assert not is_incremental
        assert len(files) == 3
        assert all(f.is_absolute() for f in files)
        mock_deps["vcs"].list_tracked_files.assert_called_once()

    def test_no_last_tree_sha_returns_all_tracked_files(
        self, mock_deps: dict
    ) -> None:
        """When last_tree_sha is None (first index), return all tracked files."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = ["main.py", "lib.py"]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=[],
            force_reindex=False,
        )

        assert not is_incremental
        assert len(files) == 2
        mock_deps["meta_repo"].get.assert_called_once_with("last_tree_sha")


class TestGetFilesToIndexNoChanges:
    """Tests for no-changes scenario."""

    def test_same_tree_sha_returns_empty_list(self, mock_deps: dict) -> None:
        """When tree_sha matches last_tree_sha, return empty list."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "abc123"
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=[],
            force_reindex=False,
        )

        assert files == []
        assert not is_incremental  # No files to index
        mock_deps["vcs"].list_tracked_files.assert_not_called()
        mock_deps["vcs"].diff_files.assert_not_called()


class TestGetFilesToIndexIncremental:
    """Tests for incremental sync scenarios."""

    def test_incremental_returns_added_files(self, mock_deps: dict) -> None:
        """Incremental sync returns added files."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "old123"
        mock_deps["vcs"].diff_files.return_value = [
            ("added", "new_file.py"),
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="new456",
            path_filters=[],
            force_reindex=False,
        )

        assert is_incremental
        assert len(files) == 1
        assert files[0] == repo_root / "new_file.py"
        mock_deps["vcs"].diff_files.assert_called_once_with(
            from_sha="old123", to_sha="new456"
        )

    def test_incremental_returns_modified_files(self, mock_deps: dict) -> None:
        """Incremental sync returns modified files."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "old123"
        mock_deps["vcs"].diff_files.return_value = [
            ("modified", "existing.py"),
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="new456",
            path_filters=[],
            force_reindex=False,
        )

        assert is_incremental
        assert len(files) == 1
        assert files[0] == repo_root / "existing.py"

    def test_incremental_returns_renamed_files(self, mock_deps: dict) -> None:
        """Incremental sync returns renamed files."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "old123"
        mock_deps["vcs"].diff_files.return_value = [
            ("renamed", "new_name.py"),
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="new456",
            path_filters=[],
            force_reindex=False,
        )

        assert is_incremental
        assert len(files) == 1
        assert files[0] == repo_root / "new_name.py"

    def test_incremental_excludes_deleted_files(self, mock_deps: dict) -> None:
        """Incremental sync does not include deleted files (handled separately)."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "old123"
        mock_deps["vcs"].diff_files.return_value = [
            ("deleted", "removed.py"),
            ("added", "new.py"),
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="new456",
            path_filters=[],
            force_reindex=False,
        )

        assert is_incremental
        assert len(files) == 1
        assert files[0] == repo_root / "new.py"

    def test_incremental_handles_mixed_statuses(self, mock_deps: dict) -> None:
        """Incremental sync handles multiple file statuses."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "old123"
        mock_deps["vcs"].diff_files.return_value = [
            ("added", "new.py"),
            ("modified", "changed.py"),
            ("renamed", "renamed.py"),
            ("deleted", "removed.py"),
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="new456",
            path_filters=[],
            force_reindex=False,
        )

        assert is_incremental
        assert len(files) == 3
        file_names = {f.name for f in files}
        assert file_names == {"new.py", "changed.py", "renamed.py"}


class TestGetFilesToIndexCodeFileFilter:
    """Tests for code file extension filtering."""

    def test_filters_to_code_files_only(self, mock_deps: dict) -> None:
        """Only code files are included, non-code files are filtered out."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "app.py",
            "config.json",
            "README.md",
            "utils.ts",
            "data.csv",
            "main.go",
            "logo.png",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=[],
            force_reindex=False,
        )

        file_names = {f.name for f in files}
        assert file_names == {"app.py", "utils.ts", "main.go"}
        assert "config.json" not in file_names
        assert "README.md" not in file_names

    def test_supports_various_code_extensions(self, mock_deps: dict) -> None:
        """Various code file extensions are supported."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "app.py",
            "app.pyi",
            "app.js",
            "app.jsx",
            "app.ts",
            "app.tsx",
            "app.go",
            "app.rs",
            "app.java",
            "app.c",
            "app.cpp",
            "app.h",
            "app.rb",
            "app.php",
            "app.swift",
            "app.sh",
            "app.sql",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=[],
            force_reindex=False,
        )

        # All files should be included (all are code files)
        assert len(files) == 17


class TestGetFilesToIndexPathFilters:
    """Tests for path filter (glob pattern) functionality."""

    def test_path_filter_single_pattern(self, mock_deps: dict) -> None:
        """Single path filter pattern filters files correctly."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "src/app.py",
            "src/utils.py",
            "tests/test_app.py",
            "docs/readme.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=["src/*.py"],
            force_reindex=False,
        )

        file_names = {f.name for f in files}
        assert file_names == {"app.py", "utils.py"}

    def test_path_filter_multiple_patterns(self, mock_deps: dict) -> None:
        """Multiple path filter patterns use OR logic."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "src/app.py",
            "tests/test_app.py",
            "docs/readme.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=["src/*.py", "tests/*.py"],
            force_reindex=False,
        )

        file_names = {f.name for f in files}
        assert file_names == {"app.py", "test_app.py"}

    def test_path_filter_glob_star_star(self, mock_deps: dict) -> None:
        """Glob ** pattern matches any directory path.

        Note: Path.match() handles ** as matching any number of directories,
        so **/*.py will match files at any depth ending in .py.
        """
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "src/app.py",
            "src/core/utils.py",
            "src/core/deep/nested.py",
            "tests/test_app.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=["**/*.py"],  # ** matches any path, *.py matches filename
            force_reindex=False,
        )

        file_names = {f.name for f in files}
        # All .py files should match **/*.py
        assert file_names == {"app.py", "utils.py", "nested.py", "test_app.py"}

    def test_path_filter_no_match_returns_empty(self, mock_deps: dict) -> None:
        """Path filter with no matches returns empty list."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "src/app.py",
            "src/utils.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=["nonexistent/*.py"],
            force_reindex=False,
        )

        assert files == []

    def test_empty_path_filters_returns_all_code_files(
        self, mock_deps: dict
    ) -> None:
        """Empty path filters list returns all code files."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "app.py",
            "utils.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=[],
            force_reindex=False,
        )

        assert len(files) == 2


class TestGetFilesToIndexCombined:
    """Tests for combined behaviors."""

    def test_incremental_with_code_filter_and_path_filter(
        self, mock_deps: dict
    ) -> None:
        """Incremental sync applies both code file filter and path filter."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "old123"
        mock_deps["vcs"].diff_files.return_value = [
            ("added", "src/new.py"),
            ("added", "src/new.json"),
            ("added", "tests/test_new.py"),
            ("modified", "src/changed.py"),
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="new456",
            path_filters=["src/*.py"],
            force_reindex=False,
        )

        assert is_incremental
        file_names = {f.name for f in files}
        # Only Python files in src/ should be included
        assert file_names == {"new.py", "changed.py"}

    def test_full_reindex_with_path_filter(self, mock_deps: dict) -> None:
        """Full reindex with path filter only returns matching files."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["vcs"].list_tracked_files.return_value = [
            "src/app.py",
            "src/utils.py",
            "tests/test_app.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=["tests/*.py"],  # Direct match with tests directory
            force_reindex=True,
        )

        assert not is_incremental
        file_names = {f.name for f in files}
        assert file_names == {"test_app.py"}

    def test_returns_absolute_paths(self, mock_deps: dict) -> None:
        """All returned file paths are absolute."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["vcs"].list_tracked_files.return_value = [
            "app.py",
            "src/utils.py",
            "deep/nested/file.py",
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha="abc123",
            path_filters=[],
            force_reindex=False,
        )

        assert all(f.is_absolute() for f in files)
        assert all(str(f).startswith(str(repo_root)) for f in files)
