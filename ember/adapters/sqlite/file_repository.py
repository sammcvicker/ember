"""SQLite adapter implementing FileRepository protocol for file tracking."""

import sqlite3
import time
from pathlib import Path


class SQLiteFileRepository:
    """SQLite implementation of FileRepository for tracking indexed files."""

    def __init__(self, db_path: Path) -> None:
        """Initialize file repository.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection.

        Reuses an existing connection if available, otherwise creates a new one.

        Returns:
            SQLite connection object.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
        return self._conn

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SQLiteFileRepository":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit context manager, closing the database connection."""
        self.close()
        return False

    def track_file(
        self,
        path: Path,
        file_hash: str,
        size: int,
        mtime: float,
    ) -> None:
        """Track state of an indexed file.

        Args:
            path: Absolute path to the file.
            file_hash: Hash of file content (blake3).
            size: File size in bytes.
            mtime: File modification timestamp.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        # Convert path to string for storage
        path_str = str(path)
        now = time.time()

        # UPSERT: insert or update if path already exists
        cursor.execute(
            """
            INSERT INTO files (path, file_hash, size, mtime, last_indexed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                file_hash = excluded.file_hash,
                size = excluded.size,
                mtime = excluded.mtime,
                last_indexed_at = excluded.last_indexed_at
            """,
            (path_str, file_hash, size, mtime, now),
        )
        conn.commit()

    def get_file_state(self, path: Path) -> dict[str, str | int | float] | None:
        """Get tracked state for a file.

        Args:
            path: Absolute path to the file.

        Returns:
            Dict with keys: file_hash, size, mtime, last_indexed_at.
            Returns None if file is not tracked.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        path_str = str(path)

        cursor.execute(
            """
            SELECT file_hash, size, mtime, last_indexed_at
            FROM files
            WHERE path = ?
            """,
            (path_str,),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        return {
            "file_hash": row[0],
            "size": row[1],
            "mtime": row[2],
            "last_indexed_at": row[3],
        }

    def get_all_tracked_files(self) -> list[Path]:
        """Get list of all tracked file paths.

        Returns:
            List of absolute paths for all tracked files.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT path FROM files ORDER BY path")

        rows = cursor.fetchall()
        return [Path(row[0]) for row in rows]
