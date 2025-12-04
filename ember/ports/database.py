"""Database port interface for database initialization.

Defines abstract interface for database schema initialization.
Implementations should be in adapters/ layer.
"""

from pathlib import Path
from typing import Protocol


class DatabaseInitializer(Protocol):
    """Protocol for database initialization operations.

    This port abstracts the database initialization logic, allowing
    the core layer to remain independent of specific database implementations.
    """

    def init_database(self, db_path: Path) -> None:
        """Initialize a new database with complete schema.

        Creates all tables, indexes, and default metadata entries.

        Args:
            db_path: Path to the database file (e.g., .ember/index.db)

        Raises:
            Exception: If database creation fails.
        """
        ...
