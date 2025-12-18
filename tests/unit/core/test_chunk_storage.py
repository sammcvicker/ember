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


# Note: mock_embedder fixture is provided by conftest.py


@pytest.fixture
def storage_service(
    mock_chunk_repo: Mock, mock_vector_repo: Mock, mock_embedder: Mock
) -> ChunkStorageService:
    """Create ChunkStorageService with mock dependencies."""
    return ChunkStorageService(mock_chunk_repo, mock_vector_repo, mock_embedder)


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
        chunk1 = create_test_chunk("chunk1", "content1")
        chunk2 = create_test_chunk("chunk2", "content2")
        chunk3 = create_test_chunk("chunk3", "content3")

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
        chunk1 = create_test_chunk("chunk1", "content1")
        chunk2 = create_test_chunk("chunk2", "content2")
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
        # Override side_effect to return empty list (wrong count)
        mock_embedder.embed_texts.side_effect = None
        mock_embedder.embed_texts.return_value = []

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

    def test_embedding_failure_prevents_any_storage(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_vector_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """When embedding fails, no chunks or vectors should be stored (embeddings-first)."""
        chunk = create_test_chunk()
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.side_effect = RuntimeError("GPU OOM")

        result = storage_service.store_chunks_and_embeddings([chunk], Path("test.py"))

        assert result.failed == 1
        # With embeddings-first approach, chunk_repo.add should never be called
        mock_chunk_repo.add.assert_not_called()
        mock_vector_repo.add.assert_not_called()
        # No rollback needed since nothing was stored
        mock_chunk_repo.delete.assert_not_called()

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
        mock_vector_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """Rollback should continue even if individual deletes fail."""
        chunk1 = create_test_chunk("chunk1", "content1")
        chunk2 = create_test_chunk("chunk2", "content2")
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.return_value = [[0.1] * 384, [0.2] * 384]

        # First chunk/vector succeeds, second vector add fails
        mock_vector_repo.add.side_effect = [None, RuntimeError("DB full")]

        # First chunk delete fails, second succeeds
        mock_chunk_repo.delete.side_effect = [RuntimeError("Delete failed"), None]
        # Vector deletes succeed
        mock_vector_repo.delete.return_value = None

        result = storage_service.store_chunks_and_embeddings(
            [chunk1, chunk2], Path("test.py")
        )

        assert result.failed == 1
        # Should have tried to delete both chunks (even though first failed)
        assert mock_chunk_repo.delete.call_count == 2
        # Should have tried to delete both vectors too
        assert mock_vector_repo.delete.call_count == 2

    def test_vector_add_failure_rolls_back_both_chunks_and_vectors(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_vector_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """When vector_repo.add() fails partway through, both chunks AND vectors are rolled back."""
        chunk1 = create_test_chunk("chunk1", "content1")
        chunk2 = create_test_chunk("chunk2", "content2")
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.return_value = [[0.1] * 384, [0.2] * 384]

        # First vector add succeeds, second fails
        mock_vector_repo.add.side_effect = [None, RuntimeError("DB full")]

        result = storage_service.store_chunks_and_embeddings(
            [chunk1, chunk2], Path("test.py")
        )

        assert result.failed == 1
        # Both chunks should be rolled back
        assert mock_chunk_repo.delete.call_count == 2
        # The successfully stored vector should also be rolled back
        mock_vector_repo.delete.assert_called()

    def test_rollback_deletes_vectors_for_all_chunks(
        self,
        storage_service: ChunkStorageService,
        mock_chunk_repo: Mock,
        mock_vector_repo: Mock,
        mock_embedder: Mock,
    ) -> None:
        """Rollback should delete vectors for all chunk IDs, not just chunks."""
        chunk1 = create_test_chunk("chunk1", "content1")
        chunk2 = create_test_chunk("chunk2", "content2")
        chunk3 = create_test_chunk("chunk3", "content3")
        mock_chunk_repo.find_by_content_hash.return_value = []
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 3

        # All vector adds succeed, but then final operation fails
        # Simulate by making the last vector add raise
        mock_vector_repo.add.side_effect = [None, None, RuntimeError("Disk full")]

        result = storage_service.store_chunks_and_embeddings(
            [chunk1, chunk2, chunk3], Path("test.py")
        )

        assert result.failed == 1
        # All 3 chunks should be deleted
        assert mock_chunk_repo.delete.call_count == 3
        # All 3 vectors should be deleted (even though only 2 were successfully added)
        # Rollback is best-effort for all, so we attempt all
        assert mock_vector_repo.delete.call_count == 3
