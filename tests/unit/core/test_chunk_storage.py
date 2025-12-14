"""Unit tests for ChunkStorageService.

Tests chunk storage, embedding generation, and rollback functionality.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from ember.core.indexing.chunk_storage import ChunkStorageService, StorageResult
from ember.domain.entities import Chunk


@pytest.fixture
def mock_chunk_repo() -> Mock:
    """Create a mock ChunkRepository."""
    return Mock()


@pytest.fixture
def mock_vector_repo() -> Mock:
    """Create a mock VectorRepository."""
    return Mock()


@pytest.fixture
def mock_embedder() -> Mock:
    """Create a mock Embedder."""
    embedder = Mock()
    embedder.fingerprint.return_value = "test-model:384"
    return embedder


@pytest.fixture
def storage_service(
    mock_chunk_repo: Mock, mock_vector_repo: Mock, mock_embedder: Mock
) -> ChunkStorageService:
    """Create ChunkStorageService with mock dependencies."""
    return ChunkStorageService(mock_chunk_repo, mock_vector_repo, mock_embedder)


def create_test_chunk(
    chunk_id: str = "chunk1",
    content: str = "def hello(): pass",
    content_hash: str = "hash1",
) -> Chunk:
    """Create a test Chunk entity."""
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
        file_hash="file_hash",
        tree_sha="tree_sha",
        rev="worktree",
    )


class TestStorageResult:
    """Tests for StorageResult dataclass."""

    def test_success_creates_result_with_zero_failed(self) -> None:
        """StorageResult.success() should set failed=0."""
        result = StorageResult.success(
            chunks_created=5, chunks_updated=2, vectors_stored=7
        )
        assert result.chunks_created == 5
        assert result.chunks_updated == 2
        assert result.vectors_stored == 7
        assert result.failed == 0

    def test_failure_creates_result_with_all_zeros(self) -> None:
        """StorageResult.failure() should return all zeros with failed=1."""
        result = StorageResult.failure()
        assert result.chunks_created == 0
        assert result.chunks_updated == 0
        assert result.vectors_stored == 0
        assert result.failed == 1


class TestDeleteOldChunks:
    """Tests for ChunkStorageService.delete_old_chunks()."""

    def test_delete_old_chunks_returns_true_on_success(
        self, storage_service: ChunkStorageService, mock_chunk_repo: Mock
    ) -> None:
        """delete_old_chunks() returns True when deletion succeeds."""
        mock_chunk_repo.delete_all_for_path.return_value = 5

        result = storage_service.delete_old_chunks(Path("test.py"))

        assert result is True
        mock_chunk_repo.delete_all_for_path.assert_called_once_with(path=Path("test.py"))

    def test_delete_old_chunks_returns_false_on_error(
        self, storage_service: ChunkStorageService, mock_chunk_repo: Mock
    ) -> None:
        """delete_old_chunks() returns False when deletion fails."""
        mock_chunk_repo.delete_all_for_path.side_effect = RuntimeError("DB error")

        result = storage_service.delete_old_chunks(Path("test.py"))

        assert result is False


class TestStoreChunksAndEmbeddings:
    """Tests for ChunkStorageService.store_chunks_and_embeddings()."""

    def test_store_empty_chunks_returns_success_with_zero_counts(
        self, storage_service: ChunkStorageService
    ) -> None:
        """Storing empty chunks list should succeed with zero counts."""
        result = storage_service.store_chunks_and_embeddings([], Path("test.py"))

        assert result.failed == 0
        assert result.chunks_created == 0
        assert result.chunks_updated == 0
        assert result.vectors_stored == 0

    def test_store_new_chunk_increments_created_count(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """Storing a new chunk (not seen before) should increment chunks_created."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = []  # Not found = new
        mock_embedder.embed_texts.return_value = [[0.1] * 384]

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 0
        assert result.chunks_created == 1
        assert result.chunks_updated == 0
        assert result.vectors_stored == 1

    def test_store_existing_chunk_increments_updated_count(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """Storing an existing chunk (by content hash) should increment chunks_updated."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = [chunk]  # Found = existing
        mock_embedder.embed_texts.return_value = [[0.1] * 384]

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 0
        assert result.chunks_created == 0
        assert result.chunks_updated == 1
        assert result.vectors_stored == 1

    def test_store_multiple_chunks_counts_correctly(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """Storing multiple chunks should count new and existing separately."""
        chunk1 = create_test_chunk("chunk1", "content1", "hash1")
        chunk2 = create_test_chunk("chunk2", "content2", "hash2")
        chunk3 = create_test_chunk("chunk3", "content3", "hash3")

        # chunk1 is new, chunk2 exists, chunk3 is new
        mock_chunk_repo.find_by_content_hash.side_effect = [
            [],  # chunk1 not found
            [chunk2],  # chunk2 found
            [],  # chunk3 not found
        ]
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 3

        result = storage_service.store_chunks_and_embeddings(
            [chunk1, chunk2, chunk3], Path("test.py")
        )

        assert result.chunks_created == 2
        assert result.chunks_updated == 1
        assert result.vectors_stored == 3

    def test_store_calls_embedder_with_all_contents(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """store_chunks_and_embeddings() should batch embed all chunk contents."""
        chunk1 = create_test_chunk("chunk1", "content1", "hash1")
        chunk2 = create_test_chunk("chunk2", "content2", "hash2")
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 2

        storage_service.store_chunks_and_embeddings([chunk1, chunk2], Path("test.py"))

        mock_embedder.embed_texts.assert_called_once_with(["content1", "content2"])

    def test_store_validates_embedding_count(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """store_chunks_and_embeddings() should fail if embedding count mismatches."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.return_value = []  # Wrong count

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1

    def test_store_uses_correct_model_fingerprint(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_vector_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """store_chunks_and_embeddings() should use embedder fingerprint for vectors."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.return_value = [[0.1] * 384]
        mock_embedder.fingerprint.return_value = "custom-model:512"

        storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        mock_vector_repo.add.assert_called_once()
        call_kwargs = mock_vector_repo.add.call_args[1]
        assert call_kwargs["model_fingerprint"] == "custom-model:512"


class TestRollback:
    """Tests for rollback functionality on failure."""

    def test_embedding_failure_triggers_rollback(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """When embedding fails, added chunks should be rolled back."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.side_effect = RuntimeError("GPU OOM")

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1
        # Should have attempted to delete the chunk
        mock_chunk_repo.delete.assert_called_once_with(chunk.id)

    def test_chunk_add_failure_triggers_rollback(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
    ) -> None:
        """When chunk_repo.add() fails, no chunks should remain."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_chunk_repo.add.side_effect = RuntimeError("Constraint violation")

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1

    def test_vector_add_failure_triggers_rollback(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_vector_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """When vector_repo.add() fails, chunks should be rolled back."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.return_value = [[0.1] * 384]
        mock_vector_repo.add.side_effect = RuntimeError("DB full")

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1
        mock_chunk_repo.delete.assert_called_once_with(chunk.id)

    def test_rollback_continues_on_delete_failure(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """Rollback should continue even if individual deletes fail."""
        chunk1 = create_test_chunk("chunk1", "content1", "hash1")
        chunk2 = create_test_chunk("chunk2", "content2", "hash2")
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.side_effect = RuntimeError("Error")

        # First delete fails, second succeeds
        mock_chunk_repo.delete.side_effect = [RuntimeError("Delete failed"), None]

        result = storage_service.store_chunks_and_embeddings(
            [chunk1, chunk2], Path("test.py")
        )

        assert result.failed == 1
        # Should have tried to delete both chunks
        assert mock_chunk_repo.delete.call_count == 2
