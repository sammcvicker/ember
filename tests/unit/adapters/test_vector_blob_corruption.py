"""Tests for corrupted vector BLOB handling (issue #443).

Tests that corrupted BLOBs in SQLite produce clear error messages with context
rather than generic struct.error exceptions, and that graceful degradation
works correctly in the sqlite-vec sync path.
"""

import logging
import struct
from pathlib import Path

import pytest

from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.schema import init_database
from ember.adapters.sqlite.vector_repository import (
    CorruptedVectorError,
    SQLiteVectorRepository,
)
from ember.domain.entities import Chunk

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_with_chunk(tmp_path: Path) -> tuple[Path, str]:
    """Create a database with a single chunk, returning (db_path, chunk_id)."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    chunk_repo = SQLiteChunkRepository(db_path)
    content = "def hello(): pass"
    chunk = Chunk(
        id=Chunk.compute_id("test_proj", Path("test.py"), 1, 10),
        project_id="test_proj",
        path=Path("test.py"),
        start_line=1,
        end_line=10,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash=Chunk.compute_content_hash("file_content"),
        lang="py",
        symbol=None,
        tree_sha="a" * 40,
        rev="worktree",
    )
    chunk_repo.add(chunk)
    return db_path, chunk.id


# =============================================================================
# SQLiteVectorRepository._decode_vector tests
# =============================================================================


class TestDecodeVectorCorruption:
    """Tests for _decode_vector handling of corrupted BLOBs."""

    def test_decode_vector_with_truncated_blob(self, db_with_chunk: tuple[Path, str]) -> None:
        """Truncated BLOB (too few bytes) raises CorruptedVectorError."""
        db_path, _ = db_with_chunk
        repo = SQLiteVectorRepository(db_path)

        # 3-dimensional vector needs 12 bytes, provide only 8
        truncated_blob = b"\x00" * 8
        with pytest.raises(CorruptedVectorError) as exc_info:
            repo._decode_vector(truncated_blob, dim=3)

        error = exc_info.value
        assert "expected 12 bytes" in str(error).lower()
        assert "got 8 bytes" in str(error).lower()

    def test_decode_vector_with_oversized_blob(self, db_with_chunk: tuple[Path, str]) -> None:
        """Oversized BLOB (too many bytes) raises CorruptedVectorError."""
        db_path, _ = db_with_chunk
        repo = SQLiteVectorRepository(db_path)

        # 3-dimensional vector needs 12 bytes, provide 16
        oversized_blob = b"\x00" * 16
        with pytest.raises(CorruptedVectorError) as exc_info:
            repo._decode_vector(oversized_blob, dim=3)

        error = exc_info.value
        assert "expected 12 bytes" in str(error).lower()
        assert "got 16 bytes" in str(error).lower()

    def test_decode_vector_with_empty_blob(self, db_with_chunk: tuple[Path, str]) -> None:
        """Empty BLOB raises CorruptedVectorError."""
        db_path, _ = db_with_chunk
        repo = SQLiteVectorRepository(db_path)

        with pytest.raises(CorruptedVectorError) as exc_info:
            repo._decode_vector(b"", dim=3)

        assert "expected 12 bytes" in str(exc_info.value).lower()
        assert "got 0 bytes" in str(exc_info.value).lower()

    def test_decode_vector_with_chunk_id_context(self, db_with_chunk: tuple[Path, str]) -> None:
        """CorruptedVectorError includes chunk_id when provided."""
        db_path, _ = db_with_chunk
        repo = SQLiteVectorRepository(db_path)

        truncated_blob = b"\x00" * 4
        with pytest.raises(CorruptedVectorError) as exc_info:
            repo._decode_vector(truncated_blob, dim=3, chunk_id="abc123")

        assert "abc123" in str(exc_info.value)

    def test_decode_vector_with_correct_blob_succeeds(
        self, db_with_chunk: tuple[Path, str]
    ) -> None:
        """Correctly sized BLOB decodes successfully (regression check)."""
        db_path, _ = db_with_chunk
        repo = SQLiteVectorRepository(db_path)

        vector = [1.0, 2.0, 3.0]
        blob = struct.pack("3f", *vector)
        result = repo._decode_vector(blob, dim=3)

        assert len(result) == 3
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(2.0)
        assert result[2] == pytest.approx(3.0)

    def test_decode_vector_error_suggests_sync_force(
        self, db_with_chunk: tuple[Path, str]
    ) -> None:
        """Error message suggests 'ember sync --force' as remediation."""
        db_path, _ = db_with_chunk
        repo = SQLiteVectorRepository(db_path)

        truncated_blob = b"\x00" * 4
        with pytest.raises(CorruptedVectorError) as exc_info:
            repo._decode_vector(truncated_blob, dim=3)

        assert "ember sync --force" in str(exc_info.value)


class TestCorruptedVectorErrorAttributes:
    """Tests for CorruptedVectorError exception attributes."""

    def test_error_has_chunk_id(self) -> None:
        """CorruptedVectorError stores chunk_id attribute."""
        error = CorruptedVectorError(
            chunk_id="abc123",
            expected_bytes=12,
            actual_bytes=8,
        )
        assert error.chunk_id == "abc123"

    def test_error_has_expected_bytes(self) -> None:
        """CorruptedVectorError stores expected_bytes attribute."""
        error = CorruptedVectorError(
            chunk_id="abc123",
            expected_bytes=12,
            actual_bytes=8,
        )
        assert error.expected_bytes == 12

    def test_error_has_actual_bytes(self) -> None:
        """CorruptedVectorError stores actual_bytes attribute."""
        error = CorruptedVectorError(
            chunk_id="abc123",
            expected_bytes=12,
            actual_bytes=8,
        )
        assert error.actual_bytes == 8

    def test_error_without_chunk_id(self) -> None:
        """CorruptedVectorError works without chunk_id."""
        error = CorruptedVectorError(
            chunk_id=None,
            expected_bytes=12,
            actual_bytes=8,
        )
        assert error.chunk_id is None
        assert "unknown" in str(error).lower() or "12" in str(error)


# =============================================================================
# SQLiteVectorRepository.get() with corrupted data tests
# =============================================================================


class TestGetWithCorruptedData:
    """Tests for SQLiteVectorRepository.get() when database has corrupted vectors."""

    def test_get_with_corrupted_blob_returns_none_and_logs(
        self, db_with_chunk: tuple[Path, str], caplog: pytest.LogCaptureFixture
    ) -> None:
        """get() returns None and logs warning for corrupted BLOB (graceful degradation)."""
        db_path, chunk_id = db_with_chunk
        repo = SQLiteVectorRepository(db_path)

        # First store a valid vector
        valid_embedding = [1.0, 2.0, 3.0]
        repo.add(chunk_id, valid_embedding, "test-model")

        # Now corrupt the BLOB in the database directly
        conn = repo._get_connection()
        cursor = conn.cursor()
        # Get the internal DB id
        cursor.execute("SELECT id FROM chunks WHERE chunk_id = ?", (chunk_id,))
        db_id = cursor.fetchone()[0]
        # Write a truncated BLOB (should be 12 bytes for 3 dims, write only 4)
        cursor.execute(
            "UPDATE vectors SET embedding = ? WHERE chunk_id = ?",
            (b"\x00" * 4, db_id),
        )
        conn.commit()

        # get() should return None and log a warning
        with caplog.at_level(logging.WARNING):
            result = repo.get(chunk_id)

        assert result is None
        assert any("corrupted" in record.message.lower() for record in caplog.records)
        assert any("ember sync --force" in record.message for record in caplog.records)


# =============================================================================
# SqliteVecAdapter._sync_vectors with corrupted data tests
# =============================================================================


class TestSyncVectorsCorruptedBlobs:
    """Tests for SqliteVecAdapter._sync_vectors handling corrupted BLOBs."""

    def test_sync_skips_corrupted_vectors_and_logs_warning(
        self, db_with_chunk: tuple[Path, str], caplog: pytest.LogCaptureFixture
    ) -> None:
        """_sync_vectors skips corrupted vectors instead of crashing."""
        from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter

        db_path, chunk_id = db_with_chunk
        vector_repo = SQLiteVectorRepository(db_path)

        # Store a valid vector first
        valid_embedding = [0.1] * 3
        vector_repo.add(chunk_id, valid_embedding, "test-model")

        # Corrupt the BLOB in the vectors table
        conn = vector_repo._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM chunks WHERE chunk_id = ?", (chunk_id,))
        db_id = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE vectors SET embedding = ? WHERE chunk_id = ?",
            (b"\x00" * 4, db_id),  # Wrong size for dim=3
        )
        conn.commit()
        vector_repo.close()

        # SqliteVecAdapter should skip corrupted vectors and log warning
        with caplog.at_level(logging.WARNING):
            adapter = SqliteVecAdapter(db_path, vector_dim=3)

        # Should not crash - adapter should be created successfully
        assert adapter is not None

        # Should have logged a warning about the corrupted vector
        assert any("corrupted" in record.message.lower() for record in caplog.records)

        adapter.close()

    def test_sync_processes_valid_vectors_alongside_corrupted(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid vectors are synced even when some are corrupted."""
        from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter

        db_path = tmp_path / "test.db"
        init_database(db_path)
        chunk_repo = SQLiteChunkRepository(db_path)
        vector_repo = SQLiteVectorRepository(db_path)

        # Create two chunks
        content1 = "def foo(): pass"
        chunk1 = Chunk(
            id=Chunk.compute_id("proj", Path("a.py"), 1, 5),
            project_id="proj",
            path=Path("a.py"),
            start_line=1,
            end_line=5,
            content=content1,
            content_hash=Chunk.compute_content_hash(content1),
            file_hash=Chunk.compute_content_hash("file_a"),
            lang="py",
            symbol=None,
            tree_sha="a" * 40,
            rev="worktree",
        )
        content2 = "def bar(): pass"
        chunk2 = Chunk(
            id=Chunk.compute_id("proj", Path("b.py"), 1, 5),
            project_id="proj",
            path=Path("b.py"),
            start_line=1,
            end_line=5,
            content=content2,
            content_hash=Chunk.compute_content_hash(content2),
            file_hash=Chunk.compute_content_hash("file_b"),
            lang="py",
            symbol=None,
            tree_sha="b" * 40,
            rev="worktree",
        )
        chunk_repo.add(chunk1)
        chunk_repo.add(chunk2)

        # Store valid vectors for both
        embedding = [0.1] * 3
        vector_repo.add(chunk1.id, embedding, "test-model")
        vector_repo.add(chunk2.id, embedding, "test-model")

        # Corrupt only the first vector
        conn = vector_repo._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM chunks WHERE chunk_id = ?", (chunk1.id,))
        db_id1 = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE vectors SET embedding = ? WHERE chunk_id = ?",
            (b"\x00" * 4, db_id1),  # Corrupted
        )
        conn.commit()
        vector_repo.close()

        # Sync should process the valid vector and skip the corrupted one
        with caplog.at_level(logging.WARNING):
            adapter = SqliteVecAdapter(db_path, vector_dim=3)

        # The valid vector should have been synced
        query_vector = [0.1] * 3
        results = adapter.query(query_vector, topk=10)
        # Should have at least the valid vector
        assert len(results) >= 1

        adapter.close()
