"""Unit tests for IndexingUseCase._get_files_to_index method.

These tests verify the file selection logic in isolation using mocks,
covering all edge cases before refactoring the method for lower complexity.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from ember.core.indexing.index_usecase import IndexingUseCase, ModelMismatchError


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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
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
        same_sha = "a" * 40
        mock_deps["meta_repo"].get.return_value = same_sha
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha=same_sha,
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
        old_sha = "c" * 40
        new_sha = "d" * 40
        mock_deps["meta_repo"].get.return_value = old_sha
        mock_deps["vcs"].diff_files.return_value = [
            ("added", "new_file.py"),
        ]
        repo_root = Path("/repo")

        files, is_incremental = usecase._get_files_to_index(
            repo_root=repo_root,
            tree_sha=new_sha,
            path_filters=[],
            force_reindex=False,
        )

        assert is_incremental
        assert len(files) == 1
        assert files[0] == repo_root / "new_file.py"
        mock_deps["vcs"].diff_files.assert_called_once_with(
            from_sha=old_sha, to_sha=new_sha
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
            tree_sha="b" * 40,
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
            tree_sha="b" * 40,
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
            tree_sha="b" * 40,
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
            tree_sha="b" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="b" * 40,
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
            tree_sha="a" * 40,
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
            tree_sha="a" * 40,
            path_filters=[],
            force_reindex=False,
        )

        assert all(f.is_absolute() for f in files)
        assert all(str(f).startswith(str(repo_root)) for f in files)


class TestModelMismatchDetection:
    """Tests for embedding model mismatch detection."""

    def test_no_stored_fingerprint_allows_sync(self, mock_deps: dict) -> None:
        """When no model fingerprint is stored, sync proceeds normally."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = None
        mock_deps["embedder"].fingerprint.return_value = "jina-code-v2:768"

        # Should not raise
        usecase._verify_model_compatibility(force_reindex=False)

    def test_matching_fingerprint_allows_sync(self, mock_deps: dict) -> None:
        """When model fingerprint matches, sync proceeds normally."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "jina-code-v2:768"
        mock_deps["embedder"].fingerprint.return_value = "jina-code-v2:768"

        # Should not raise
        usecase._verify_model_compatibility(force_reindex=False)

    def test_different_fingerprint_raises_error(self, mock_deps: dict) -> None:
        """When model fingerprint differs and force_reindex is False, raise error."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "jina-code-v2:768"
        mock_deps["embedder"].fingerprint.return_value = "minilm:384"

        with pytest.raises(ModelMismatchError) as exc_info:
            usecase._verify_model_compatibility(force_reindex=False)

        assert "jina-code-v2:768" in str(exc_info.value)
        assert "minilm:384" in str(exc_info.value)
        assert "ember sync --force" in str(exc_info.value)

    def test_different_fingerprint_with_force_allows_sync(self, mock_deps: dict) -> None:
        """When model fingerprint differs but force_reindex is True, allow sync."""
        usecase = IndexingUseCase(**mock_deps)
        mock_deps["meta_repo"].get.return_value = "jina-code-v2:768"
        mock_deps["embedder"].fingerprint.return_value = "minilm:384"

        # Should not raise when force_reindex is True
        usecase._verify_model_compatibility(force_reindex=True)


class TestModelMismatchErrorAttributes:
    """Tests for ModelMismatchError exception attributes."""

    def test_error_stores_model_names(self) -> None:
        """ModelMismatchError stores both model names."""
        error = ModelMismatchError(
            stored_model="jina-code-v2:768",
            current_model="minilm:384",
        )

        assert error.stored_model == "jina-code-v2:768"
        assert error.current_model == "minilm:384"

    def test_error_message_contains_instructions(self) -> None:
        """ModelMismatchError message contains helpful instructions."""
        error = ModelMismatchError(
            stored_model="jina-code-v2:768",
            current_model="minilm:384",
        )

        msg = str(error)
        assert "jina-code-v2:768" in msg
        assert "minilm:384" in msg
        assert "ember sync --force" in msg


class TestIndexFileErrorHandling:
    """Tests for error handling in _index_file() method."""

    @pytest.fixture
    def setup_indexing_usecase(self, mock_deps: dict) -> IndexingUseCase:
        """Create IndexingUseCase configured for indexing a single file."""
        # Configure chunk_usecase to return success with chunks
        from ember.ports.chunkers import ChunkData

        chunk_data = ChunkData(
            content="def hello(): pass",
            start_line=1,
            end_line=1,
            lang="py",
            symbol="hello",
        )
        mock_deps["chunk_usecase"].execute.return_value = Mock(
            success=True,
            chunks=[chunk_data],
            error=None,
        )
        # Configure fs to return file content
        mock_deps["fs"].read.return_value = b"def hello(): pass"
        # Configure embedder
        mock_deps["embedder"].fingerprint.return_value = "test-model:384"
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384]
        # Configure chunk_repo
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["chunk_repo"].delete_all_for_path.return_value = 0

        return IndexingUseCase(**mock_deps)

    def test_embedding_failure_rolls_back_chunks(
        self, mock_deps: dict, setup_indexing_usecase: IndexingUseCase
    ) -> None:
        """When embedding fails, chunks added during this indexing are rolled back."""
        usecase = setup_indexing_usecase

        # Make embedding fail
        mock_deps["embedder"].embed_texts.side_effect = RuntimeError("GPU OOM")

        result = usecase._index_file(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
            tree_sha="a" * 40,
            sync_mode="worktree",
        )

        # Should return failed status
        assert result["failed"] == 1
        assert result["chunks_created"] == 0
        assert result["vectors_stored"] == 0

    def test_embedding_count_mismatch_detected(
        self, mock_deps: dict, setup_indexing_usecase: IndexingUseCase
    ) -> None:
        """When embedding count doesn't match chunk count, error is raised."""
        usecase = setup_indexing_usecase

        # Return wrong number of embeddings (0 instead of 1)
        mock_deps["embedder"].embed_texts.return_value = []

        result = usecase._index_file(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
            tree_sha="a" * 40,
            sync_mode="worktree",
        )

        # Should detect mismatch and return failed status
        assert result["failed"] == 1
        assert result["vectors_stored"] == 0

    def test_vector_repo_failure_partial_rollback(
        self, mock_deps: dict, setup_indexing_usecase: IndexingUseCase
    ) -> None:
        """When vector_repo.add() fails, partial vectors are cleaned up."""
        usecase = setup_indexing_usecase

        # Make vector_repo.add fail
        mock_deps["vector_repo"].add.side_effect = RuntimeError("DB connection lost")

        result = usecase._index_file(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
            tree_sha="a" * 40,
            sync_mode="worktree",
        )

        # Should return failed status
        assert result["failed"] == 1
        assert result["vectors_stored"] == 0

    def test_chunk_deletion_failure_handled(
        self, mock_deps: dict, setup_indexing_usecase: IndexingUseCase
    ) -> None:
        """When chunk_repo.delete_all_for_path() fails, error is logged and handled."""
        usecase = setup_indexing_usecase

        # Make delete_all_for_path fail
        mock_deps["chunk_repo"].delete_all_for_path.side_effect = RuntimeError(
            "DB locked"
        )

        result = usecase._index_file(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
            tree_sha="a" * 40,
            sync_mode="worktree",
        )

        # Should return failed status
        assert result["failed"] == 1

    def test_chunk_add_failure_rolls_back(
        self, mock_deps: dict, setup_indexing_usecase: IndexingUseCase
    ) -> None:
        """When chunk_repo.add() fails, the file indexing is marked as failed."""
        usecase = setup_indexing_usecase

        # Make chunk_repo.add fail
        mock_deps["chunk_repo"].add.side_effect = RuntimeError("Constraint violation")

        result = usecase._index_file(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
            tree_sha="a" * 40,
            sync_mode="worktree",
        )

        # Should return failed status
        assert result["failed"] == 1
        assert result["chunks_created"] == 0

    def test_successful_indexing_returns_correct_counts(
        self, mock_deps: dict, setup_indexing_usecase: IndexingUseCase
    ) -> None:
        """Successful indexing returns correct chunk and vector counts."""
        usecase = setup_indexing_usecase

        result = usecase._index_file(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
            tree_sha="a" * 40,
            sync_mode="worktree",
        )

        # Should succeed with correct counts
        assert result["failed"] == 0
        assert result["chunks_created"] == 1
        assert result["vectors_stored"] == 1

    def test_file_repo_failure_does_not_affect_indexing_result(
        self, mock_deps: dict, setup_indexing_usecase: IndexingUseCase
    ) -> None:
        """When file_repo.track_file() fails, indexing should still report success.

        File tracking is metadata and should not fail the entire indexing operation.
        """
        usecase = setup_indexing_usecase

        # Make file_repo.track_file fail
        mock_deps["file_repo"].track_file.side_effect = RuntimeError("DB error")

        result = usecase._index_file(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
            tree_sha="a" * 40,
            sync_mode="worktree",
        )

        # Indexing should succeed (file tracking is not critical)
        assert result["failed"] == 0
        assert result["chunks_created"] == 1
        assert result["vectors_stored"] == 1


class TestExecuteErrorHandling:
    """Tests for error handling in execute() method.

    These tests verify that the execute() method properly catches and
    handles various exception types, returning appropriate IndexResponse
    objects with error information.
    """

    @pytest.fixture
    def setup_execute_usecase(self, mock_deps: dict) -> IndexingUseCase:
        """Create IndexingUseCase configured for execute() testing."""
        # Configure for basic successful operation
        mock_deps["meta_repo"].get.return_value = None  # No previous index
        mock_deps["vcs"].list_tracked_files.return_value = ["test.py"]
        mock_deps["vcs"].get_worktree_tree_sha.return_value = "abc123"
        mock_deps["embedder"].fingerprint.return_value = "test-model:384"
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384]
        mock_deps["fs"].read.return_value = b"def hello(): pass"
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["chunk_repo"].delete_all_for_path.return_value = 0

        from ember.ports.chunkers import ChunkData

        chunk_data = ChunkData(
            content="def hello(): pass",
            start_line=1,
            end_line=1,
            lang="py",
            symbol="hello",
        )
        mock_deps["chunk_usecase"].execute.return_value = Mock(
            success=True,
            chunks=[chunk_data],
            error=None,
        )

        return IndexingUseCase(**mock_deps)

    def test_model_mismatch_returns_error_response(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """ModelMismatchError returns an error response with helpful message."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Set up model mismatch scenario
        mock_deps["meta_repo"].get.return_value = "old-model:768"
        mock_deps["embedder"].fingerprint.return_value = "new-model:384"

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=False)
        response = usecase.execute(request)

        assert not response.success
        assert response.error is not None
        assert "old-model:768" in response.error
        assert "new-model:384" in response.error

    def test_file_not_found_returns_io_error_response(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """FileNotFoundError (subclass of OSError) returns an I/O error response."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make fs.read raise FileNotFoundError
        mock_deps["fs"].read.side_effect = FileNotFoundError("test.py not found")

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)
        response = usecase.execute(request)

        assert not response.success
        assert response.error is not None
        assert "i/o error" in response.error.lower()

    def test_permission_error_returns_io_error_response(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """PermissionError (subclass of OSError) returns an I/O error response."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make fs.read raise PermissionError
        mock_deps["fs"].read.side_effect = PermissionError("Access denied")

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)
        response = usecase.execute(request)

        assert not response.success
        assert response.error is not None
        assert "i/o error" in response.error.lower()
        assert "permission" in response.error.lower()

    def test_os_error_returns_io_error_response(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """OSError returns an I/O error response."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make fs.read raise OSError
        mock_deps["fs"].read.side_effect = OSError("Disk full")

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)
        response = usecase.execute(request)

        assert not response.success
        assert response.error is not None
        assert "i/o error" in response.error.lower()

    def test_value_error_returns_error_response(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """ValueError at the orchestration level returns an error response."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make _get_tree_sha raise ValueError (at orchestration level)
        mock_deps["vcs"].get_worktree_tree_sha.side_effect = ValueError(
            "Invalid sync mode"
        )

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)
        response = usecase.execute(request)

        assert not response.success
        assert response.error is not None

    def test_runtime_error_returns_error_response(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """RuntimeError returns an error response."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make vcs raise RuntimeError
        mock_deps["vcs"].get_worktree_tree_sha.side_effect = RuntimeError("Git error")

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)
        response = usecase.execute(request)

        assert not response.success
        assert response.error is not None

    def test_unexpected_exception_returns_internal_error(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """Unexpected exceptions return a generic internal error response."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make something raise an unexpected exception type
        mock_deps["vcs"].get_worktree_tree_sha.side_effect = TypeError("Unexpected")

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)
        response = usecase.execute(request)

        assert not response.success
        assert response.error is not None
        assert "internal error" in response.error.lower()

    def test_keyboard_interrupt_propagates(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """KeyboardInterrupt is not caught and propagates up."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make vcs raise KeyboardInterrupt
        mock_deps["vcs"].get_worktree_tree_sha.side_effect = KeyboardInterrupt()

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)

        with pytest.raises(KeyboardInterrupt):
            usecase.execute(request)

    def test_system_exit_propagates(
        self, mock_deps: dict, setup_execute_usecase: IndexingUseCase
    ) -> None:
        """SystemExit is not caught and propagates up."""
        from ember.core.indexing.index_usecase import IndexRequest

        usecase = setup_execute_usecase

        # Make vcs raise SystemExit
        mock_deps["vcs"].get_worktree_tree_sha.side_effect = SystemExit(1)

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=True)

        with pytest.raises(SystemExit):
            usecase.execute(request)
