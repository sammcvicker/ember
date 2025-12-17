"""Base class for SQLite repository adapters.

Provides consistent connection management, thread safety, and context
manager protocol for all SQLite-based adapters in the codebase.
"""

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Self


class SQLiteBaseRepository:
    """Base class providing SQLite connection management.

    All SQLite repository adapters should inherit from this class to get:
    - Thread-safe connection initialization (double-checked locking)
    - Cross-thread connection access (check_same_thread=False)
    - Context manager protocol (__enter__/__exit__)
    - Configurable foreign keys and custom setup callbacks

    Thread Safety:
        Connections are initialized lazily with double-checked locking.
        This prevents race conditions where multiple threads could create
        separate connections simultaneously. The connection itself allows
        cross-thread access via check_same_thread=False.

    Example:
        class MyRepository(SQLiteBaseRepository):
            def __init__(self, db_path: Path) -> None:
                super().__init__(db_path, foreign_keys=True)

            def my_query(self) -> list:
                conn = self._get_connection()
                cursor = conn.execute("SELECT * FROM my_table")
                return cursor.fetchall()
    """

    def __init__(
        self,
        db_path: Path,
        *,
        foreign_keys: bool = False,
        connection_setup: Callable[[sqlite3.Connection], None] | None = None,
    ) -> None:
        """Initialize the repository.

        Args:
            db_path: Path to SQLite database file.
            foreign_keys: Whether to enable foreign key constraints.
            connection_setup: Optional callback for custom connection setup.
                Called after connection is created but before first use.
        """
        self.db_path = db_path
        self._foreign_keys = foreign_keys
        self._connection_setup = connection_setup
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection, creating one if needed.

        Uses double-checked locking to ensure thread-safe initialization.
        The connection is configured with check_same_thread=False to allow
        use from different threads (required for interactive search where
        queries run in a thread executor).

        Returns:
            SQLite connection object.
        """
        if self._conn is None:
            with self._conn_lock:
                # Double-check pattern: re-check after acquiring lock
                if self._conn is None:
                    self._conn = sqlite3.connect(
                        self.db_path, check_same_thread=False
                    )
                    if self._foreign_keys:
                        self._conn.execute("PRAGMA foreign_keys = ON")
                    if self._connection_setup is not None:
                        self._connection_setup(self._conn)
        return self._conn

    def close(self) -> None:
        """Close the database connection if open.

        Safe to call multiple times. After calling close(), the next call
        to _get_connection() will create a new connection.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Exit context manager, closing the database connection."""
        self.close()
        return False
