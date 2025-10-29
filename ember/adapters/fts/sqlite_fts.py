"""SQLite FTS5 adapter implementing TextSearch protocol for full-text search."""

import sqlite3
from pathlib import Path

from ember.domain.entities import Chunk


class SQLiteFTS:
    """SQLite FTS5 implementation of TextSearch for BM25-style full-text search.

    This adapter uses the FTS5 virtual table 'chunk_text' which is automatically
    kept in sync with the 'chunks' table via triggers. Therefore, the add() method
    is a no-op - chunks are indexed automatically when added to chunks table.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize FTS5 text search adapter.

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

    def add(self, chunk_id: str, text: str, metadata: dict[str, str]) -> None:
        """Add a document to the text search index.

        This is a no-op because the FTS5 table is automatically synced via triggers
        when chunks are inserted/updated/deleted in the chunks table.

        Args:
            chunk_id: Unique identifier for the chunk (unused).
            text: Text content to index (unused).
            metadata: Additional metadata (unused).
        """
        # No-op: FTS5 table is automatically synced via triggers
        pass

    def query(
        self, q: str, topk: int = 100, path_filter: str | None = None
    ) -> list[tuple[str, float]]:
        """Query the FTS5 index using SQLite full-text search.

        Args:
            q: Query string (supports FTS5 query syntax like AND, OR, NEAR, quotes).
            topk: Maximum number of results to return.
            path_filter: Optional glob pattern to filter results by path.

        Returns:
            List of (chunk_id, score) tuples, sorted by relevance (descending).
            Score is the negative BM25 rank from FTS5 (higher = more relevant).
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Query FTS5 table and join with chunks to get chunk metadata
        # FTS5's rank is negative (closer to 0 = better), so we negate it
        # to get a positive score where higher = more relevant
        # Add path filtering if specified
        if path_filter:
            cursor.execute(
                """
                SELECT
                    c.project_id,
                    c.path,
                    c.start_line,
                    c.end_line,
                    -rank AS score
                FROM chunk_text
                JOIN chunks c ON chunk_text.rowid = c.id
                WHERE chunk_text MATCH ?
                  AND c.path GLOB ?
                ORDER BY rank
                LIMIT ?
                """,
                (q, path_filter, topk),
            )
        else:
            cursor.execute(
                """
                SELECT
                    c.project_id,
                    c.path,
                    c.start_line,
                    c.end_line,
                    -rank AS score
                FROM chunk_text
                JOIN chunks c ON chunk_text.rowid = c.id
                WHERE chunk_text MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (q, topk),
            )

        rows = cursor.fetchall()
        results = []

        for row in rows:
            # Compute chunk_id from the fields
            project_id = row[0]
            path = Path(row[1])
            start_line = row[2]
            end_line = row[3]
            score = row[4]

            chunk_id = Chunk.compute_id(project_id, path, start_line, end_line)
            results.append((chunk_id, score))

        return results
