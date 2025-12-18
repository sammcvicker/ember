"""Integration tests for SQLite thread safety in search operations.

Tests that SQLite adapters can be safely used across threads, which is
required for interactive search where search operations run in a thread
executor while the main thread handles UI.

Fixes: #204 - SQLite thread safety error in interactive search
"""

import asyncio
import concurrent.futures
from pathlib import Path

import pytest

from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.schema import init_database
from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
from ember.domain.entities import Chunk


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized."""
    db = tmp_path / "test.db"
    init_database(db)
    return db


@pytest.fixture
def sample_chunk() -> Chunk:
    """Create a sample chunk for testing."""
    content = "def hello(): return 'world'"
    return Chunk(
        id="test-chunk-id",
        project_id="test-project",
        path=Path("test.py"),
        lang="py",
        symbol="hello",
        start_line=1,
        end_line=1,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash="file-hash",
        tree_sha="tree-sha",
        rev="worktree",
    )


class TestSQLiteFTSThreadSafety:
    """Test SQLiteFTS adapter thread safety."""

    def test_query_from_different_thread(
        self, db_path: Path, sample_chunk: Chunk
    ) -> None:
        """Test that FTS queries work when called from a different thread.

        This simulates the interactive search scenario where the search
        function runs in a thread executor while the main thread owns
        the original connection.
        """
        # Create adapter in main thread
        fts = SQLiteFTS(db_path)

        # First, add a chunk via chunk repository so FTS has data
        chunk_repo = SQLiteChunkRepository(db_path)
        chunk_repo.add(sample_chunk)
        chunk_repo.close()

        # Run query in a thread executor (simulating interactive search)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fts.query, "hello", 10)
            # Should not raise ProgrammingError about thread safety
            results = future.result(timeout=5.0)

        assert isinstance(results, list)
        fts.close()

    def test_concurrent_queries_from_multiple_threads(
        self, db_path: Path, sample_chunk: Chunk
    ) -> None:
        """Test that multiple concurrent FTS queries work from different threads."""
        # Setup: add chunk
        chunk_repo = SQLiteChunkRepository(db_path)
        chunk_repo.add(sample_chunk)
        chunk_repo.close()

        # Create adapter in main thread
        fts = SQLiteFTS(db_path)

        # Run multiple queries concurrently from different threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(fts.query, "hello", 10)
                for _ in range(5)
            ]
            # All should complete without thread safety errors
            for future in concurrent.futures.as_completed(futures):
                results = future.result(timeout=5.0)
                assert isinstance(results, list)

        fts.close()


class TestSQLiteChunkRepositoryThreadSafety:
    """Test SQLiteChunkRepository thread safety."""

    def test_get_from_different_thread(
        self, db_path: Path, sample_chunk: Chunk
    ) -> None:
        """Test that chunk retrieval works from a different thread."""
        # Create adapter in main thread and add chunk
        chunk_repo = SQLiteChunkRepository(db_path)
        chunk_repo.add(sample_chunk)

        # Run query in a thread executor
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(chunk_repo.get, sample_chunk.id)
            result = future.result(timeout=5.0)

        assert result is not None
        assert result.id == sample_chunk.id
        chunk_repo.close()


class TestSqliteVecAdapterThreadSafety:
    """Test SqliteVecAdapter thread safety."""

    def test_query_from_different_thread(
        self, db_path: Path, sample_chunk: Chunk
    ) -> None:
        """Test that vector queries work from a different thread."""
        # Create adapter in main thread
        vec_adapter = SqliteVecAdapter(db_path)

        # Create a dummy query vector (768 dimensions for Jina)
        query_vector = [0.1] * 768

        # Run query in a thread executor
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(vec_adapter.query, query_vector, 10)
            # Should not raise thread safety error
            results = future.result(timeout=5.0)

        assert isinstance(results, list)
        vec_adapter.close()


class TestInteractiveSearchThreadSafety:
    """Test the full interactive search scenario with async executor."""

    def test_search_in_executor_thread(
        self, db_path: Path, sample_chunk: Chunk
    ) -> None:
        """Simulate the exact pattern used by interactive search UI.

        The UI uses asyncio.get_event_loop().run_in_executor(None, search_fn, query)
        which runs the search function in a thread pool executor.
        """
        async def run_async_search() -> list[tuple[str, float]]:
            # Create search adapters (as CLI does)
            fts = SQLiteFTS(db_path)
            chunk_repo_inner = SQLiteChunkRepository(db_path)

            # Define search function (simulating what CLI creates)
            def search_fn(query_text: str) -> list[tuple[str, float]]:
                return fts.query(query_text, topk=10)

            # Run search in executor (as interactive UI does)
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, search_fn, "hello")

            fts.close()
            chunk_repo_inner.close()
            return results

        # Setup: add chunk
        chunk_repo = SQLiteChunkRepository(db_path)
        chunk_repo.add(sample_chunk)
        chunk_repo.close()

        # Run the async search
        results = asyncio.run(run_async_search())

        assert isinstance(results, list)
