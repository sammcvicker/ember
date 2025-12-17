"""Unit tests for SQLiteBaseRepository base class.

Tests that the base class provides consistent connection management,
thread safety, and context manager protocol for all SQLite adapters.
"""

import concurrent.futures
import sqlite3
import threading
from pathlib import Path

import pytest

from ember.adapters.sqlite.base_repository import SQLiteBaseRepository
from ember.adapters.sqlite.schema import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized."""
    db = tmp_path / "test.db"
    init_database(db)
    return db


class ConcreteRepository(SQLiteBaseRepository):
    """Concrete implementation for testing the abstract base class."""

    pass


class RepositoryWithForeignKeys(SQLiteBaseRepository):
    """Test repository that enables foreign keys."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path, foreign_keys=True)


class RepositoryWithCallback(SQLiteBaseRepository):
    """Test repository with custom connection setup callback."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path, connection_setup=self._setup_connection)
        self.setup_called = False

    def _setup_connection(self, conn: sqlite3.Connection) -> None:
        """Custom setup callback."""
        self.setup_called = True
        conn.execute("PRAGMA journal_mode = WAL")


class TestSQLiteBaseRepositoryInit:
    """Tests for initialization and configuration."""

    def test_init_stores_db_path(self, db_path: Path) -> None:
        """Test that db_path is stored correctly."""
        repo = ConcreteRepository(db_path)
        assert repo.db_path == db_path

    def test_init_connection_is_none(self, db_path: Path) -> None:
        """Test that connection is not created on init."""
        repo = ConcreteRepository(db_path)
        assert repo._conn is None

    def test_init_creates_lock(self, db_path: Path) -> None:
        """Test that thread lock is created on init."""
        repo = ConcreteRepository(db_path)
        assert repo._conn_lock is not None
        assert isinstance(repo._conn_lock, type(threading.Lock()))


class TestSQLiteBaseRepositoryConnection:
    """Tests for connection management."""

    def test_get_connection_creates_connection(self, db_path: Path) -> None:
        """Test that _get_connection creates a new connection when needed."""
        repo = ConcreteRepository(db_path)
        conn = repo._get_connection()
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        repo.close()

    def test_get_connection_reuses_connection(self, db_path: Path) -> None:
        """Test that _get_connection returns the same connection."""
        repo = ConcreteRepository(db_path)
        conn1 = repo._get_connection()
        conn2 = repo._get_connection()
        assert conn1 is conn2
        repo.close()

    def test_connection_uses_check_same_thread_false(self, db_path: Path) -> None:
        """Test that connections allow cross-thread access."""
        repo = ConcreteRepository(db_path)
        conn = repo._get_connection()

        # Verify we can use connection from another thread without error
        def use_connection() -> bool:
            try:
                conn.execute("SELECT 1")
                return True
            except sqlite3.ProgrammingError:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(use_connection)
            result = future.result(timeout=5.0)

        assert result is True
        repo.close()

    def test_foreign_keys_disabled_by_default(self, db_path: Path) -> None:
        """Test that foreign keys are disabled by default."""
        repo = ConcreteRepository(db_path)
        conn = repo._get_connection()
        cursor = conn.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()[0]
        assert result == 0  # 0 = disabled
        repo.close()

    def test_foreign_keys_enabled_when_requested(self, db_path: Path) -> None:
        """Test that foreign keys can be enabled."""
        repo = RepositoryWithForeignKeys(db_path)
        conn = repo._get_connection()
        cursor = conn.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()[0]
        assert result == 1  # 1 = enabled
        repo.close()

    def test_connection_setup_callback(self, db_path: Path) -> None:
        """Test that custom connection setup callback is called."""
        repo = RepositoryWithCallback(db_path)
        _ = repo._get_connection()
        assert repo.setup_called is True
        repo.close()


class TestSQLiteBaseRepositoryClose:
    """Tests for close() method."""

    def test_close_closes_connection(self, db_path: Path) -> None:
        """Test that close() closes the connection."""
        repo = ConcreteRepository(db_path)
        _ = repo._get_connection()
        assert repo._conn is not None
        repo.close()
        assert repo._conn is None

    def test_close_idempotent(self, db_path: Path) -> None:
        """Test that close() can be called multiple times."""
        repo = ConcreteRepository(db_path)
        _ = repo._get_connection()
        repo.close()
        repo.close()  # Should not raise
        assert repo._conn is None

    def test_close_without_connection(self, db_path: Path) -> None:
        """Test that close() works when no connection exists."""
        repo = ConcreteRepository(db_path)
        repo.close()  # Should not raise
        assert repo._conn is None


class TestSQLiteBaseRepositoryContextManager:
    """Tests for context manager protocol."""

    def test_enter_returns_self(self, db_path: Path) -> None:
        """Test that __enter__ returns the repository instance."""
        repo = ConcreteRepository(db_path)
        with repo as ctx:
            assert ctx is repo

    def test_exit_closes_connection(self, db_path: Path) -> None:
        """Test that __exit__ closes the connection."""
        repo = ConcreteRepository(db_path)
        with repo:
            _ = repo._get_connection()
            assert repo._conn is not None
        assert repo._conn is None

    def test_exit_closes_on_exception(self, db_path: Path) -> None:
        """Test that connection is closed even on exception."""
        repo = ConcreteRepository(db_path)
        try:
            with repo:
                _ = repo._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass
        assert repo._conn is None


class TestSQLiteBaseRepositoryThreadSafety:
    """Tests for thread-safe connection initialization."""

    def test_concurrent_get_connection_returns_same_connection(
        self, db_path: Path
    ) -> None:
        """Test that concurrent calls to _get_connection return the same connection.

        This tests the double-checked locking pattern to prevent race conditions.
        """
        repo = ConcreteRepository(db_path)
        connections_seen: list[int] = []

        def get_connection_id() -> int:
            conn = repo._get_connection()
            return id(conn)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_connection_id) for _ in range(50)]
            for future in concurrent.futures.as_completed(futures):
                connections_seen.append(future.result(timeout=5.0))

        unique_connections = set(connections_seen)
        assert len(unique_connections) == 1, (
            f"Expected 1 connection but got {len(unique_connections)}. "
            "Race condition in _get_connection()."
        )
        repo.close()

    def test_queries_work_from_different_threads(self, db_path: Path) -> None:
        """Test that the connection can be used from different threads."""
        repo = ConcreteRepository(db_path)

        def run_query() -> int:
            conn = repo._get_connection()
            cursor = conn.execute("SELECT 1")
            row = cursor.fetchone()
            assert row is not None, "SELECT 1 should always return a row"
            return row[0]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_query) for _ in range(10)]
            results = []
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result(timeout=5.0))

        assert all(r == 1 for r in results)
        repo.close()
