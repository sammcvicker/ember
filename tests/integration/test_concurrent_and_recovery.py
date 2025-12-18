"""Integration tests for concurrent sync and recovery scenarios.

Tests critical concurrent access and recovery behaviors that are real
production concerns but were previously uncovered (#323):

1. Concurrent sync calls - what happens when multiple threads call sync
2. Database corruption recovery - partial/corrupted database handling
3. Transaction rollback - complete verification of rollback behavior
4. Daemon timeout - handling of embedding service timeouts
"""

import concurrent.futures
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
from ember.adapters.sqlite.schema import init_database
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.core.indexing.chunk_storage import ChunkStorageService
from ember.domain.entities import Chunk

# =============================================================================
# Test fixtures
# =============================================================================


@pytest.fixture
def fresh_db_path(tmp_path: Path) -> Path:
    """Create a fresh temporary database for tests needing isolation."""
    path = tmp_path / "fresh_test.db"
    init_database(path)
    return path


@pytest.fixture
def chunk_repo(db_path: Path) -> SQLiteChunkRepository:
    """Create a chunk repository for testing."""
    return SQLiteChunkRepository(db_path)


@pytest.fixture
def vector_repo(db_path: Path) -> SQLiteVectorRepository:
    """Create a vector repository for testing."""
    return SQLiteVectorRepository(db_path)


@pytest.fixture
def meta_repo(db_path: Path) -> SQLiteMetaRepository:
    """Create a meta repository for testing."""
    return SQLiteMetaRepository(db_path)


def create_test_chunk(
    chunk_id: str,
    content: str = "def test(): pass",
    path: str = "test.py",
    start_line: int = 1,
    end_line: int = 1,
) -> Chunk:
    """Create a test chunk with valid data.

    Note: To add multiple unique chunks, vary start_line/end_line since
    the database has a UNIQUE constraint on (tree_sha, path, start_line, end_line).
    """
    return Chunk(
        id=chunk_id,
        project_id="test_project",
        path=Path(path),
        lang="py",
        symbol="test",
        start_line=start_line,
        end_line=end_line,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash=Chunk.compute_content_hash("file content"),
        tree_sha="a" * 40,
        rev="worktree",
    )


# =============================================================================
# Concurrent sync tests
# =============================================================================


class TestConcurrentSyncOperations:
    """Tests for concurrent sync operation safety."""

    def test_sequential_chunk_additions_from_single_connection(
        self, fresh_db_path: Path
    ) -> None:
        """Adding chunks sequentially from a single connection should work.

        This is the expected usage pattern - one connection per operation.
        """
        repo = SQLiteChunkRepository(fresh_db_path)

        for i in range(20):
            # Use unique start_line to avoid UPSERT overwriting
            chunk = create_test_chunk(
                chunk_id=f"chunk_{i}",
                content=f"def func_{i}(): pass",
                start_line=i + 1,
                end_line=i + 1,
            )
            repo.add(chunk)

        # Verify all chunks were added (from same connection)
        for i in range(20):
            chunk = repo.get(f"chunk_{i}")
            assert chunk is not None, f"Chunk chunk_{i} not found"

        repo.close()

    def test_reads_from_multiple_threads_are_safe(
        self, fresh_db_path: Path
    ) -> None:
        """Concurrent reads from multiple threads should work.

        SQLite allows multiple concurrent readers.
        """
        # Pre-populate some chunks with a fresh repo
        setup_repo = SQLiteChunkRepository(fresh_db_path)
        for i in range(10):
            # Use unique start_line to avoid UPSERT overwriting
            chunk = create_test_chunk(
                f"initial_{i}",
                f"def initial_{i}(): pass",
                start_line=i + 1,
                end_line=i + 1,
            )
            setup_repo.add(chunk)
        setup_repo.close()

        read_results: list[int] = []
        errors: list[Exception] = []

        def reader(iterations: int) -> int:
            """Read chunks repeatedly."""
            try:
                count = 0
                repo = SQLiteChunkRepository(fresh_db_path)
                for _ in range(iterations):
                    for i in range(10):
                        chunk = repo.get(f"initial_{i}")
                        if chunk is not None:
                            count += 1
                repo.close()
                return count
            except Exception as e:
                errors.append(e)
                return -1

        # Run concurrent reads (readers can run in parallel)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            read_futures = [executor.submit(reader, 20) for _ in range(5)]
            read_results = [f.result(timeout=30) for f in read_futures]

        # All reads should succeed
        assert all(r > 0 for r in read_results), f"Some reads failed: {errors}"
        # Each reader should have found all 10 chunks * 20 iterations
        assert all(r == 200 for r in read_results)

    def test_sequential_meta_updates_work(
        self, db_path: Path, meta_repo: SQLiteMetaRepository
    ) -> None:
        """Sequential metadata updates should work correctly.

        Tests the typical pattern of updating metadata after sync.
        """
        # Simulate multiple sync operations updating metadata
        for i in range(10):
            meta_repo.set("last_tree_sha", f"sha_{i}")
            meta_repo.set("sync_timestamp", f"2024-01-{i:02d}")

        # Final values should be from the last update
        assert meta_repo.get("last_tree_sha") == "sha_9"
        assert meta_repo.get("sync_timestamp") == "2024-01-09"


# =============================================================================
# Database corruption recovery tests
# =============================================================================


class TestDatabaseCorruptionRecovery:
    """Tests for handling corrupted or partial database states."""

    def test_corrupted_database_header_detected(self, tmp_path: Path) -> None:
        """Corrupted database should raise a clear error on open.

        This tests that we detect and report database corruption rather
        than silently returning wrong results.
        """
        db_path = tmp_path / "corrupted.db"

        # Create a valid database first
        init_database(db_path)
        repo = SQLiteChunkRepository(db_path)
        repo.add(create_test_chunk("test1"))
        repo.close()

        # Corrupt the database header (first 16 bytes contain SQLite magic)
        with open(db_path, "r+b") as f:
            f.write(b"CORRUPTED_HEADER")

        # Attempting to use the corrupted database should fail clearly
        with pytest.raises(sqlite3.DatabaseError):
            repo = SQLiteChunkRepository(db_path)
            repo.get("test1")

    def test_truncated_database_detected(self, tmp_path: Path) -> None:
        """Truncated database should be detected.

        Simulates a database file that was partially written (e.g., disk full).
        """
        db_path = tmp_path / "truncated.db"

        # Create a valid database with some data
        init_database(db_path)
        repo = SQLiteChunkRepository(db_path)
        for i in range(10):
            repo.add(create_test_chunk(f"test_{i}", f"def test_{i}(): pass"))
        repo.close()

        # Get original file size
        original_size = db_path.stat().st_size

        # Truncate the file to half its size
        with open(db_path, "r+b") as f:
            f.truncate(original_size // 2)

        # Attempting to use should fail or return partial data
        # (SQLite may detect corruption on various operations)
        with pytest.raises((sqlite3.DatabaseError, sqlite3.OperationalError)):
            repo = SQLiteChunkRepository(db_path)
            # Try to access data that was in the truncated portion
            for i in range(10):
                repo.get(f"test_{i}")

    def test_missing_database_creates_new_on_init(self, tmp_path: Path) -> None:
        """Missing database should be created fresh on init.

        Tests the recovery path when .ember/index.db doesn't exist.
        """
        db_path = tmp_path / "new.db"

        # Database doesn't exist yet
        assert not db_path.exists()

        # init_database should create it
        init_database(db_path)

        # Should now be usable
        repo = SQLiteChunkRepository(db_path)
        repo.add(create_test_chunk("test1"))
        retrieved = repo.get("test1")
        repo.close()

        assert retrieved is not None
        assert retrieved.id == "test1"

    def test_database_locked_error_is_sqlite_error(
        self, db_path: Path
    ) -> None:
        """Database locked errors are a known SQLite limitation.

        This test documents that SQLite raises OperationalError when
        a database is locked by another connection with an exclusive lock.
        """
        # Create a connection that holds an exclusive lock
        conn = sqlite3.connect(db_path, timeout=0.1)
        conn.execute("BEGIN EXCLUSIVE")

        try:
            # Another connection with short timeout should fail quickly
            other_conn = sqlite3.connect(db_path, timeout=0.1)
            with pytest.raises(sqlite3.OperationalError, match="locked|busy"):
                other_conn.execute("INSERT INTO meta (key, value) VALUES ('test', 'value')")
            other_conn.close()
        finally:
            conn.rollback()
            conn.close()


# =============================================================================
# Transaction rollback verification tests
# =============================================================================


class TestTransactionRollbackVerification:
    """Tests for complete transaction rollback on failure."""

    def test_embedding_failure_rolls_back_all_chunks(
        self, chunk_repo: SQLiteChunkRepository, vector_repo: SQLiteVectorRepository
    ) -> None:
        """When embedding fails, ALL added chunks should be rolled back.

        Verifies that partial state is not left in the database.
        """
        mock_embedder = Mock()
        mock_embedder.fingerprint.return_value = "test-model:384"
        # Fail on embedding
        mock_embedder.embed_texts.side_effect = RuntimeError("GPU OOM")

        service = ChunkStorageService(chunk_repo, vector_repo, mock_embedder)

        # Try to store multiple chunks
        chunks = [
            create_test_chunk(f"chunk_{i}", f"def func_{i}(): pass")
            for i in range(5)
        ]

        result = service.store_chunks_and_embeddings(chunks, Path("test.py"))

        # Should report failure
        assert result.failed == 1

        # ALL chunks should be rolled back (not just some)
        for i in range(5):
            chunk = chunk_repo.get(f"chunk_{i}")
            assert chunk is None, f"Chunk {i} was not rolled back"

    def test_vector_storage_failure_rolls_back_partial_vectors(
        self, chunk_repo: SQLiteChunkRepository, vector_repo: SQLiteVectorRepository
    ) -> None:
        """When vector storage fails partway through, chunks are rolled back.

        Tests the scenario where some vectors are stored before failure.
        """
        mock_embedder = Mock()
        mock_embedder.fingerprint.return_value = "test-model:384"
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 3

        # Make vector_repo.add fail on the second call
        original_add = vector_repo.add
        call_count = [0]

        def failing_add(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("DB full")
            return original_add(*args, **kwargs)

        vector_repo.add = failing_add

        service = ChunkStorageService(chunk_repo, vector_repo, mock_embedder)

        chunks = [
            create_test_chunk(f"chunk_{i}", f"def func_{i}(): pass")
            for i in range(3)
        ]

        result = service.store_chunks_and_embeddings(chunks, Path("test.py"))

        # Should report failure
        assert result.failed == 1

        # All chunks should be rolled back
        for i in range(3):
            chunk = chunk_repo.get(f"chunk_{i}")
            assert chunk is None, f"Chunk {i} was not rolled back"

    def test_rollback_continues_on_individual_delete_failures(
        self, chunk_repo: SQLiteChunkRepository, vector_repo: SQLiteVectorRepository
    ) -> None:
        """Rollback should attempt to delete all chunks even if some fail.

        Tests resilience of the rollback process itself.
        With embeddings-first approach, we need storage to start before triggering failure.
        """
        mock_embedder = Mock()
        mock_embedder.fingerprint.return_value = "test-model:384"
        mock_embedder.embed_texts.return_value = [[0.1] * 384] * 3

        # Make vector_repo.add fail on the third call (after chunks are stored)
        original_vector_add = vector_repo.add
        vector_add_count = [0]

        def failing_vector_add(*args, **kwargs):
            vector_add_count[0] += 1
            if vector_add_count[0] == 3:  # Fail on third vector add
                raise RuntimeError("Vector storage failed")
            return original_vector_add(*args, **kwargs)

        vector_repo.add = failing_vector_add

        # Make some chunk deletes fail during rollback
        original_delete = chunk_repo.delete
        delete_count = [0]

        def failing_delete(chunk_id: str):
            delete_count[0] += 1
            if delete_count[0] == 2:  # Fail on second delete
                raise RuntimeError("Delete failed")
            return original_delete(chunk_id)

        chunk_repo.delete = failing_delete

        service = ChunkStorageService(chunk_repo, vector_repo, mock_embedder)

        chunks = [
            create_test_chunk(f"chunk_{i}", f"def func_{i}(): pass")
            for i in range(3)
        ]

        result = service.store_chunks_and_embeddings(chunks, Path("test.py"))

        assert result.failed == 1
        # Should have attempted to delete all 3 chunks (rollback continues on failure)
        assert delete_count[0] == 3


# =============================================================================
# Daemon timeout and fallback tests
# =============================================================================


class TestDaemonTimeoutHandling:
    """Tests for daemon timeout scenarios."""

    def test_embedder_timeout_returns_failure(
        self, chunk_repo: SQLiteChunkRepository, vector_repo: SQLiteVectorRepository
    ) -> None:
        """Embedder timeout should be handled gracefully.

        Tests that socket timeouts during embedding don't leave partial state.
        """
        mock_embedder = Mock()
        mock_embedder.fingerprint.return_value = "test-model:384"
        # Simulate timeout
        mock_embedder.embed_texts.side_effect = TimeoutError("Connection timed out")

        service = ChunkStorageService(chunk_repo, vector_repo, mock_embedder)

        chunks = [create_test_chunk("chunk_1")]
        result = service.store_chunks_and_embeddings(chunks, Path("test.py"))

        # Should report failure
        assert result.failed == 1

        # Chunk should be rolled back
        assert chunk_repo.get("chunk_1") is None

    def test_connection_refused_returns_failure(
        self, chunk_repo: SQLiteChunkRepository, vector_repo: SQLiteVectorRepository
    ) -> None:
        """Connection refused should be handled gracefully.

        Tests the scenario where daemon is not running.
        """
        mock_embedder = Mock()
        mock_embedder.fingerprint.return_value = "test-model:384"
        mock_embedder.embed_texts.side_effect = ConnectionRefusedError("Connection refused")

        service = ChunkStorageService(chunk_repo, vector_repo, mock_embedder)

        chunks = [create_test_chunk("chunk_1")]
        result = service.store_chunks_and_embeddings(chunks, Path("test.py"))

        assert result.failed == 1
        assert chunk_repo.get("chunk_1") is None

    def test_ensure_synced_handles_embedding_failure_gracefully(
        self, tmp_path: Path
    ) -> None:
        """ensure_synced should handle embedding failures without crashing.

        This tests the full integration path from ensure_synced down to
        embedding failure.
        """
        from ember.entrypoints.cli import ensure_synced

        db_path = tmp_path / ".ember" / "index.db"
        db_path.parent.mkdir(parents=True)
        init_database(db_path)

        with (
            patch("ember.adapters.git_cmd.git_adapter.GitAdapter") as mock_git,
            patch(
                "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
            ) as mock_meta,
            patch("ember.entrypoints.cli._create_indexing_usecase") as mock_usecase,
            patch("ember.entrypoints.cli.progress_context") as mock_progress_ctx,
        ):
            mock_git.return_value.get_worktree_tree_sha.return_value = "new_sha"
            mock_meta.return_value.get.return_value = "old_sha"

            # Mock index response with failure
            mock_response = MagicMock()
            mock_response.success = False
            mock_response.error = "Embedding failed: GPU OOM"
            mock_response.files_indexed = 0
            mock_usecase.return_value.execute.return_value = mock_response

            mock_progress_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_progress_ctx.return_value.__exit__ = MagicMock(return_value=None)

            result = ensure_synced(
                repo_root=tmp_path,
                db_path=db_path,
                config=MagicMock(),
            )

            # Should complete without crashing
            # Result depends on how error is classified
            assert result is not None
