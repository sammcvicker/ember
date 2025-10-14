"""SQLite adapter implementing MetaRepository protocol for metadata storage."""

import sqlite3
from pathlib import Path


class SQLiteMetaRepository:
    """SQLite implementation of MetaRepository for storing metadata."""

    def __init__(self, db_path: Path) -> None:
        """Initialize meta repository.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection.

        Returns:
            SQLite connection object.
        """
        return sqlite3.connect(self.db_path)

    def get(self, key: str) -> str | None:
        """Get a metadata value by key.

        Args:
            key: The metadata key.

        Returns:
            The value if found, None otherwise.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT value FROM meta WHERE key = ?",
                (key,),
            )

            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def set(self, key: str, value: str) -> None:
        """Set a metadata key-value pair.

        Uses UPSERT semantics - inserts if key doesn't exist, updates if it does.

        Args:
            key: The metadata key.
            value: The value to store.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # UPSERT: insert or update if key exists
            cursor.execute(
                """
                INSERT INTO meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value
                """,
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, key: str) -> None:
        """Delete a metadata key.

        Args:
            key: The metadata key to delete.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM meta WHERE key = ?",
                (key,),
            )
            conn.commit()
        finally:
            conn.close()
