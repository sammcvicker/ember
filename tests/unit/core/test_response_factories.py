"""Tests for response dataclass factory methods.

These tests verify that response dataclasses have factory methods
for creating success and error responses consistently.
"""

from pathlib import Path

from ember.core.chunking.chunk_usecase import ChunkFileResponse
from ember.core.config.init_usecase import InitResponse
from ember.core.indexing.index_usecase import IndexResponse
from ember.core.status.status_usecase import StatusResponse
from ember.domain.config import EmberConfig
from ember.ports.chunkers import ChunkData


class TestIndexResponseFactories:
    """Tests for IndexResponse factory methods."""

    def test_error_creates_failed_response_with_zero_counts(self) -> None:
        """Error factory should set success=False and all counts to zero."""
        response = IndexResponse.create_error("Something went wrong")

        assert response.success is False
        assert response.error == "Something went wrong"
        assert response.files_indexed == 0
        assert response.chunks_created == 0
        assert response.chunks_updated == 0
        assert response.chunks_deleted == 0
        assert response.vectors_stored == 0
        assert response.tree_sha == ""
        assert response.is_incremental is False
        assert response.files_failed == 0

    def test_success_creates_successful_response(self) -> None:
        """Success factory should set success=True and provided values."""
        response = IndexResponse.create_success(
            files_indexed=10,
            chunks_created=50,
            chunks_updated=5,
            chunks_deleted=2,
            vectors_stored=55,
            tree_sha="abc123",
            is_incremental=True,
            files_failed=1,
        )

        assert response.success is True
        assert response.error is None
        assert response.files_indexed == 10
        assert response.chunks_created == 50
        assert response.chunks_updated == 5
        assert response.chunks_deleted == 2
        assert response.vectors_stored == 55
        assert response.tree_sha == "abc123"
        assert response.is_incremental is True
        assert response.files_failed == 1

    def test_success_with_defaults(self) -> None:
        """Success factory should have sensible defaults for optional fields."""
        response = IndexResponse.create_success(
            files_indexed=5,
            chunks_created=20,
            chunks_updated=0,
            chunks_deleted=0,
            vectors_stored=20,
            tree_sha="def456",
        )

        assert response.is_incremental is False
        assert response.files_failed == 0


class TestStatusResponseFactories:
    """Tests for StatusResponse factory methods."""

    def test_error_creates_failed_response(self) -> None:
        """Error factory should set success=False with error message."""
        response = StatusResponse.create_error(
            "Connection failed", repo_root=Path("/test")
        )

        assert response.success is False
        assert response.error == "Connection failed"
        assert response.initialized is True  # We know ember is initialized if we got this far
        assert response.repo_root == Path("/test")

    def test_success_creates_successful_response(self) -> None:
        """Success factory should set success=True and provided values."""
        config = EmberConfig()
        response = StatusResponse.create_success(
            repo_root=Path("/test/repo"),
            indexed_files=100,
            total_chunks=500,
            last_tree_sha="abc123",
            is_stale=False,
            model_fingerprint="model-v1",
            config=config,
        )

        assert response.success is True
        assert response.error is None
        assert response.initialized is True
        assert response.repo_root == Path("/test/repo")
        assert response.indexed_files == 100
        assert response.total_chunks == 500
        assert response.last_tree_sha == "abc123"
        assert response.is_stale is False
        assert response.model_fingerprint == "model-v1"
        assert response.config == config


class TestInitResponseFactories:
    """Tests for InitResponse factory methods."""

    def test_error_creates_failed_response(self) -> None:
        """Error factory should set success=False with all paths as None."""
        response = InitResponse.create_error("Permission denied")

        assert response.success is False
        assert response.error == "Permission denied"
        assert response.ember_dir is None
        assert response.config_path is None
        assert response.db_path is None
        assert response.state_path is None
        assert response.was_reinitialized is False
        assert response.already_exists is False

    def test_error_with_already_exists(self) -> None:
        """Error factory should support already_exists flag."""
        response = InitResponse.create_error("Already exists", already_exists=True)

        assert response.success is False
        assert response.already_exists is True

    def test_success_creates_successful_response(self) -> None:
        """Success factory should set success=True and provided paths."""
        response = InitResponse.create_success(
            ember_dir=Path("/test/.ember"),
            config_path=Path("/test/.ember/config.toml"),
            db_path=Path("/test/.ember/index.db"),
            state_path=Path("/test/.ember/state.json"),
            was_reinitialized=True,
            global_config_created=True,
            global_config_path=Path("~/.config/ember/config.toml"),
        )

        assert response.success is True
        assert response.error is None
        assert response.ember_dir == Path("/test/.ember")
        assert response.config_path == Path("/test/.ember/config.toml")
        assert response.db_path == Path("/test/.ember/index.db")
        assert response.state_path == Path("/test/.ember/state.json")
        assert response.was_reinitialized is True
        assert response.global_config_created is True
        assert response.global_config_path == Path("~/.config/ember/config.toml")
        assert response.already_exists is False


class TestChunkFileResponseFactories:
    """Tests for ChunkFileResponse factory methods."""

    def test_error_creates_failed_response(self) -> None:
        """Error factory should set success=False with empty chunks."""
        response = ChunkFileResponse.create_error("Parse error")

        assert response.success is False
        assert response.error == "Parse error"
        assert response.chunks == []
        assert response.strategy == ""

    def test_success_creates_successful_response(self) -> None:
        """Success factory should set success=True and provided values."""
        chunks = [
            ChunkData(
                content="def foo(): pass",
                start_line=1,
                end_line=1,
                lang="py",
                symbol="foo",
            )
        ]
        response = ChunkFileResponse.create_success(
            chunks=chunks, strategy="tree-sitter"
        )

        assert response.success is True
        assert response.error is None
        assert response.chunks == chunks
        assert response.strategy == "tree-sitter"

    def test_success_empty_file(self) -> None:
        """Success factory should work for empty files."""
        response = ChunkFileResponse.create_success(chunks=[], strategy="none")

        assert response.success is True
        assert response.chunks == []
        assert response.strategy == "none"
