"""Tests for error path coverage in core components.

This module adds tests for error handling paths that are critical for
debugging and operational visibility. These tests verify that:
1. Error scenarios return appropriate error responses
2. Error paths log meaningful messages for diagnostics
3. Rollback mechanisms work correctly on failure

References: Issue #357
"""

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from ember.core.indexing.chunk_storage import ChunkStorageService
from ember.core.indexing.index_usecase import IndexingUseCase, ModelMismatchError
from ember.domain.entities import Chunk

# ============================================================================
# Test Helpers
# ============================================================================


def create_test_chunk(
    chunk_id: str = "chunk1",
    content: str = "def hello(): pass",
    content_hash: str | None = None,
) -> Chunk:
    """Create a test Chunk entity."""
    if content_hash is None:
        content_hash = Chunk.compute_content_hash(content)
    return Chunk(
        id=chunk_id,
        project_id="test_project",
        path=Path("test.py"),
        lang="py",
        symbol="hello",
        start_line=1,
        end_line=1,
        content=content,
        content_hash=content_hash,
        file_hash=Chunk.compute_content_hash("file content"),
        tree_sha="a" * 40,
        rev="worktree",
    )


# ============================================================================
# ChunkStorageService Error Logging Tests
# ============================================================================


class TestChunkStorageServiceErrorLogging:
    """Tests for error logging in ChunkStorageService."""

    @pytest.fixture
    def mock_deps(self) -> dict:
        """Create mock dependencies for ChunkStorageService."""
        return {
            "chunk_repo": Mock(),
            "vector_repo": Mock(),
            "embedder": Mock(),
        }

    @pytest.fixture
    def storage_service(self, mock_deps: dict) -> ChunkStorageService:
        """Create ChunkStorageService with mock dependencies."""
        return ChunkStorageService(
            mock_deps["chunk_repo"],
            mock_deps["vector_repo"],
            mock_deps["embedder"],
        )

    def test_embedding_failure_logs_error_with_rollback_message(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Embedding failure should log error with rollback context."""
        chunk = create_test_chunk()
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["embedder"].embed_texts.side_effect = RuntimeError("GPU out of memory")

        with caplog.at_level(logging.ERROR):
            result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1
        # Should log the error with file path context
        assert len(caplog.records) >= 1
        error_record = caplog.records[0]
        assert error_record.levelname == "ERROR"
        assert "test.py" in error_record.message
        assert "Rolling back" in error_record.message

    def test_embedding_count_mismatch_logs_error(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Embedding count mismatch should log error with details."""
        chunks = [
            create_test_chunk("chunk1", "content1"),
            create_test_chunk("chunk2", "content2"),
        ]
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        # Return only 1 embedding for 2 chunks
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384]

        with caplog.at_level(logging.ERROR):
            result = storage_service.store_chunks_and_embeddings(chunks, Path("test.py"))

        assert result.failed == 1
        # Should log the mismatch details
        assert len(caplog.records) >= 1
        assert any("mismatch" in r.message.lower() for r in caplog.records)

    def test_vector_add_failure_logs_error_and_rolls_back(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Vector add failure should log error and rollback message."""
        chunk = create_test_chunk()
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384]
        mock_deps["embedder"].fingerprint.return_value = "test-model:384"
        mock_deps["vector_repo"].add.side_effect = RuntimeError("Database full")

        with caplog.at_level(logging.ERROR):
            result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1
        assert len(caplog.records) >= 1
        error_record = caplog.records[0]
        assert "Rolling back" in error_record.message

    def test_delete_old_chunks_failure_logs_error(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Failure to delete old chunks should log error with path."""
        mock_deps["chunk_repo"].delete_all_for_path.side_effect = RuntimeError("DB locked")

        with caplog.at_level(logging.ERROR):
            result = storage_service.delete_old_chunks(Path("important/file.py"))

        assert result is False
        assert len(caplog.records) >= 1
        error_record = caplog.records[0]
        assert error_record.levelname == "ERROR"
        assert "important/file.py" in error_record.message

    def test_rollback_failure_logs_warning_per_chunk(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Rollback failure should log warning for each failed delete."""
        chunk1 = create_test_chunk("chunk1", "content1")
        chunk2 = create_test_chunk("chunk2", "content2")
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384, [0.2] * 384]
        mock_deps["embedder"].fingerprint.return_value = "test-model:384"
        # Second vector add fails
        mock_deps["vector_repo"].add.side_effect = [None, RuntimeError("Disk full")]
        # Chunk delete also fails
        mock_deps["chunk_repo"].delete.side_effect = RuntimeError("Rollback failed")
        mock_deps["vector_repo"].delete.return_value = None

        with caplog.at_level(logging.WARNING):
            result = storage_service.store_chunks_and_embeddings(
                [chunk1, chunk2], Path("test.py")
            )

        assert result.failed == 1
        # Should have warning logs for failed rollback attempts
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) >= 1
        assert any("rollback" in r.message.lower() for r in warning_records)


# ============================================================================
# IndexingUseCase Error Logging Tests
# ============================================================================


class TestIndexingUseCaseErrorLogging:
    """Tests for error logging in IndexingUseCase."""

    @pytest.fixture
    def mock_deps(self) -> dict:
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
    def indexing_usecase(self, mock_deps: dict) -> IndexingUseCase:
        """Create IndexingUseCase with mock dependencies."""
        return IndexingUseCase(**mock_deps)

    def test_model_mismatch_logs_error(
        self,
        indexing_usecase: IndexingUseCase,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ModelMismatchError should be logged with both model names."""
        from ember.core.indexing.index_usecase import IndexRequest

        mock_deps["meta_repo"].get.return_value = "old-model:768"
        mock_deps["embedder"].fingerprint.return_value = "new-model:384"

        request = IndexRequest(repo_root=Path("/repo"), force_reindex=False)

        with caplog.at_level(logging.ERROR):
            response = indexing_usecase.execute(request)

        assert not response.success
        assert len(caplog.records) >= 1
        # Should log both model names
        error_messages = " ".join(r.message for r in caplog.records)
        assert "old-model:768" in error_messages
        assert "new-model:384" in error_messages

    def test_file_tracking_failure_logs_warning(
        self,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """file_repo.track_file failure should log warning but not fail indexing."""
        from ember.ports.chunkers import ChunkData

        # Configure successful chunking and embedding
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
        mock_deps["fs"].read.return_value = b"def hello(): pass"
        mock_deps["embedder"].fingerprint.return_value = "test-model:384"
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384]
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["chunk_repo"].delete_all_for_path.return_value = 0
        mock_deps["file_repo"].track_file.side_effect = RuntimeError("DB error")

        usecase = IndexingUseCase(**mock_deps)

        with caplog.at_level(logging.WARNING):
            result = usecase._index_file(
                file_path=Path("/repo/test.py"),
                repo_root=Path("/repo"),
                tree_sha="a" * 40,
                sync_mode="worktree",
            )

        # Indexing should succeed despite file tracking failure
        assert result["failed"] == 0
        assert result["chunks_created"] == 1
        # Should log warning about tracking failure
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) >= 1
        assert any("track" in r.message.lower() for r in warning_records)

    def test_chunking_failure_logs_warning(
        self,
        mock_deps: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Chunking failure should log warning with file path."""
        mock_deps["chunk_usecase"].execute.return_value = Mock(
            success=False,
            chunks=[],
            error="Parse error: unexpected token",
        )
        mock_deps["fs"].read.return_value = b"def hello( pass"  # Invalid syntax

        usecase = IndexingUseCase(**mock_deps)

        with caplog.at_level(logging.WARNING):
            result = usecase._index_file(
                file_path=Path("/repo/broken.py"),
                repo_root=Path("/repo"),
                tree_sha="a" * 40,
                sync_mode="worktree",
            )

        assert result["failed"] == 1
        # Should log warning with file path
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) >= 1
        assert any("broken.py" in r.message for r in warning_records)


# ============================================================================
# Partial Sync Rollback Tests
# ============================================================================


class TestPartialSyncRollback:
    """Tests for partial sync rollback scenarios.

    These tests verify that when embedding or storage fails partway through
    processing multiple chunks, all previously stored chunks are properly
    rolled back to maintain consistency.
    """

    @pytest.fixture
    def mock_deps(self) -> dict:
        """Create mock dependencies for ChunkStorageService."""
        return {
            "chunk_repo": Mock(),
            "vector_repo": Mock(),
            "embedder": Mock(),
        }

    @pytest.fixture
    def storage_service(self, mock_deps: dict) -> ChunkStorageService:
        """Create ChunkStorageService with mock dependencies."""
        return ChunkStorageService(
            mock_deps["chunk_repo"],
            mock_deps["vector_repo"],
            mock_deps["embedder"],
        )

    def test_failure_on_third_chunk_rolls_back_all_stored(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
    ) -> None:
        """Failure on third chunk should rollback the first two that were stored."""
        chunks = [
            create_test_chunk("chunk1", "content1"),
            create_test_chunk("chunk2", "content2"),
            create_test_chunk("chunk3", "content3"),
        ]
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384] * 3
        mock_deps["embedder"].fingerprint.return_value = "test-model:384"
        # First two succeed, third fails
        mock_deps["chunk_repo"].add.side_effect = [None, None, RuntimeError("Constraint")]

        result = storage_service.store_chunks_and_embeddings(chunks, Path("test.py"))

        assert result.failed == 1
        # Only the two successfully added chunks should be rolled back
        # (the third was never added because add() failed)
        assert mock_deps["chunk_repo"].delete.call_count == 2
        # Vectors are deleted for all chunks that were added before failure
        assert mock_deps["vector_repo"].delete.call_count == 2

    def test_embedding_failure_leaves_no_orphan_chunks(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
    ) -> None:
        """Embedding failure should not leave any orphan chunks in database."""
        chunks = [
            create_test_chunk("chunk1", "content1"),
            create_test_chunk("chunk2", "content2"),
        ]
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        # Embedding fails before any chunks are stored
        mock_deps["embedder"].embed_texts.side_effect = RuntimeError("Model not loaded")

        result = storage_service.store_chunks_and_embeddings(chunks, Path("test.py"))

        assert result.failed == 1
        # No chunks should have been added (embeddings-first approach)
        mock_deps["chunk_repo"].add.assert_not_called()
        # No vectors should have been added
        mock_deps["vector_repo"].add.assert_not_called()
        # No rollback needed since nothing was stored
        mock_deps["chunk_repo"].delete.assert_not_called()

    def test_vector_add_failure_rolls_back_associated_chunk(
        self,
        storage_service: ChunkStorageService,
        mock_deps: dict,
    ) -> None:
        """When vector add fails, the associated chunk should be rolled back."""
        chunk = create_test_chunk()
        mock_deps["chunk_repo"].find_by_content_hash.return_value = []
        mock_deps["embedder"].embed_texts.return_value = [[0.1] * 384]
        mock_deps["embedder"].fingerprint.return_value = "test-model:384"
        # Chunk add succeeds, vector add fails
        mock_deps["chunk_repo"].add.return_value = None
        mock_deps["vector_repo"].add.side_effect = RuntimeError("Vector storage full")

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1
        # The chunk should be rolled back
        mock_deps["chunk_repo"].delete.assert_called_once_with(chunk.id)
        # Vector delete should also be attempted
        mock_deps["vector_repo"].delete.assert_called_once_with(chunk.id)


# ============================================================================
# ModelMismatchError Tests
# ============================================================================


class TestModelMismatchErrorDetails:
    """Tests for ModelMismatchError exception details."""

    def test_error_message_includes_recovery_command(self) -> None:
        """Error message should include ember sync --force command."""
        error = ModelMismatchError(
            stored_model="jina-code-v2:768",
            current_model="minilm:384",
        )

        message = str(error)

        assert "ember sync --force" in message
        assert "jina-code-v2:768" in message
        assert "minilm:384" in message

    def test_error_includes_arrow_indicating_change(self) -> None:
        """Error message should show transition with arrow."""
        error = ModelMismatchError(
            stored_model="old-model:512",
            current_model="new-model:768",
        )

        message = str(error)

        # Should indicate direction of change
        assert "old-model:512" in message
        assert "new-model:768" in message
        assert "→" in message or "->" in message


# ============================================================================
# Query Validation Tests
# ============================================================================


class TestQueryEmptyTextValidation:
    """Tests for Query empty text validation."""

    def test_empty_string_raises_value_error(self) -> None:
        """Empty string query should raise ValueError."""
        from ember.domain.entities import Query

        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query(text="")

    def test_whitespace_only_raises_value_error(self) -> None:
        """Whitespace-only query should raise ValueError."""
        from ember.domain.entities import Query

        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query(text="   \t\n  ")

    def test_valid_query_succeeds(self) -> None:
        """Valid non-empty query should succeed."""
        from ember.domain.entities import Query

        query = Query(text="search term")
        assert query.text == "search term"

    def test_query_with_leading_whitespace_succeeds(self) -> None:
        """Query with leading/trailing whitespace but content should succeed."""
        from ember.domain.entities import Query

        query = Query(text="  valid query  ")
        assert query.text == "  valid query  "
