"""Unit tests for repository context manager protocol.

Tests that all repository classes properly implement the context manager protocol
for resource cleanup (closes database connections on exit).
"""

from pathlib import Path

from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.file_repository import SQLiteFileRepository
from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter


class TestChunkRepositoryContextManager:
    """Tests for SQLiteChunkRepository context manager protocol."""

    def test_context_manager_returns_self(self, db_path: Path):
        """Test that __enter__ returns the repository instance."""
        repo = SQLiteChunkRepository(db_path)
        with repo as ctx:
            assert ctx is repo

    def test_context_manager_closes_connection(self, db_path: Path):
        """Test that __exit__ closes the database connection."""
        repo = SQLiteChunkRepository(db_path)
        with repo:
            # Access connection to ensure it's created
            _ = repo._get_connection()
            assert repo._conn is not None

        # After exiting context, connection should be closed
        assert repo._conn is None

    def test_context_manager_closes_on_exception(self, db_path: Path):
        """Test that connection is closed even when exception occurs."""
        repo = SQLiteChunkRepository(db_path)
        try:
            with repo:
                _ = repo._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Connection should still be closed
        assert repo._conn is None

    def test_close_method_idempotent(self, db_path: Path):
        """Test that close() can be called multiple times safely."""
        repo = SQLiteChunkRepository(db_path)
        repo._get_connection()
        repo.close()
        repo.close()  # Should not raise
        assert repo._conn is None


class TestFileRepositoryContextManager:
    """Tests for SQLiteFileRepository context manager protocol."""

    def test_context_manager_returns_self(self, db_path: Path):
        """Test that __enter__ returns the repository instance."""
        repo = SQLiteFileRepository(db_path)
        with repo as ctx:
            assert ctx is repo

    def test_context_manager_closes_connection(self, db_path: Path):
        """Test that __exit__ closes the database connection."""
        repo = SQLiteFileRepository(db_path)
        with repo:
            _ = repo._get_connection()
            assert repo._conn is not None

        assert repo._conn is None

    def test_context_manager_closes_on_exception(self, db_path: Path):
        """Test that connection is closed even when exception occurs."""
        repo = SQLiteFileRepository(db_path)
        try:
            with repo:
                _ = repo._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert repo._conn is None


class TestVectorRepositoryContextManager:
    """Tests for SQLiteVectorRepository context manager protocol."""

    def test_context_manager_returns_self(self, db_path: Path):
        """Test that __enter__ returns the repository instance."""
        repo = SQLiteVectorRepository(db_path)
        with repo as ctx:
            assert ctx is repo

    def test_context_manager_closes_connection(self, db_path: Path):
        """Test that __exit__ closes the database connection."""
        repo = SQLiteVectorRepository(db_path)
        with repo:
            _ = repo._get_connection()
            assert repo._conn is not None

        assert repo._conn is None

    def test_context_manager_closes_on_exception(self, db_path: Path):
        """Test that connection is closed even when exception occurs."""
        repo = SQLiteVectorRepository(db_path)
        try:
            with repo:
                _ = repo._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert repo._conn is None


class TestMetaRepositoryContextManager:
    """Tests for SQLiteMetaRepository context manager protocol."""

    def test_context_manager_returns_self(self, db_path: Path):
        """Test that __enter__ returns the repository instance."""
        repo = SQLiteMetaRepository(db_path)
        with repo as ctx:
            assert ctx is repo

    def test_context_manager_closes_connection(self, db_path: Path):
        """Test that __exit__ closes the database connection."""
        repo = SQLiteMetaRepository(db_path)
        with repo:
            _ = repo._get_connection()
            assert repo._conn is not None

        assert repo._conn is None

    def test_context_manager_closes_on_exception(self, db_path: Path):
        """Test that connection is closed even when exception occurs."""
        repo = SQLiteMetaRepository(db_path)
        try:
            with repo:
                _ = repo._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert repo._conn is None


class TestSqliteFtsContextManager:
    """Tests for SQLiteFTS context manager protocol."""

    def test_context_manager_returns_self(self, db_path: Path):
        """Test that __enter__ returns the adapter instance."""
        adapter = SQLiteFTS(db_path)
        with adapter as ctx:
            assert ctx is adapter

    def test_context_manager_closes_connection(self, db_path: Path):
        """Test that __exit__ closes the database connection."""
        adapter = SQLiteFTS(db_path)
        with adapter:
            _ = adapter._get_connection()
            assert adapter._conn is not None

        assert adapter._conn is None

    def test_context_manager_closes_on_exception(self, db_path: Path):
        """Test that connection is closed even when exception occurs."""
        adapter = SQLiteFTS(db_path)
        try:
            with adapter:
                _ = adapter._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert adapter._conn is None


class TestSqliteVecAdapterContextManager:
    """Tests for SqliteVecAdapter context manager protocol."""

    def test_context_manager_returns_self(self, db_path: Path):
        """Test that __enter__ returns the adapter instance."""
        adapter = SqliteVecAdapter(db_path)
        with adapter as ctx:
            assert ctx is adapter

    def test_context_manager_closes_connection(self, db_path: Path):
        """Test that __exit__ closes the database connection."""
        adapter = SqliteVecAdapter(db_path)
        with adapter:
            # Access connection to ensure it's created
            _ = adapter._get_connection()
            assert adapter._conn is not None

        # After exiting context, connection should be closed
        assert adapter._conn is None

    def test_context_manager_closes_on_exception(self, db_path: Path):
        """Test that connection is closed even when exception occurs."""
        adapter = SqliteVecAdapter(db_path)
        try:
            with adapter:
                _ = adapter._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Connection should still be closed
        assert adapter._conn is None

    def test_close_method_idempotent(self, db_path: Path):
        """Test that close() can be called multiple times safely."""
        adapter = SqliteVecAdapter(db_path)
        adapter._get_connection()
        adapter.close()
        adapter.close()  # Should not raise
        assert adapter._conn is None

    def test_connection_reuse(self, db_path: Path):
        """Test that connections are reused across multiple operations."""
        adapter = SqliteVecAdapter(db_path)
        conn1 = adapter._get_connection()
        conn2 = adapter._get_connection()

        # Should be the same connection object
        assert conn1 is conn2
        adapter.close()
