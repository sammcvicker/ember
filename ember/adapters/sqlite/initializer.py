"""SQLite database initializer adapter.

Implements the DatabaseInitializer port using SQLite.
"""

from pathlib import Path

from ember.adapters.sqlite.schema import init_database as sqlite_init_database


class SqliteDatabaseInitializer:
    """SQLite implementation of DatabaseInitializer port.

    Wraps the existing init_database function to satisfy the port interface.
    """

    def init_database(self, db_path: Path) -> None:
        """Initialize a new SQLite database with complete schema.

        Creates all tables, indexes, and default metadata entries.

        Args:
            db_path: Path to the SQLite database file.

        Raises:
            sqlite3.Error: If database creation fails.
        """
        sqlite_init_database(db_path)
