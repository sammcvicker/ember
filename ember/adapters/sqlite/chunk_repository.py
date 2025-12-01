"""SQLite adapter implementing ChunkRepository protocol for chunk storage."""

import sqlite3
import time
from pathlib import Path

from ember.adapters.sqlite.schema import migrate_database
from ember.domain.entities import Chunk


class SQLiteChunkRepository:
    """SQLite implementation of ChunkRepository for storing code chunks."""

    def __init__(self, db_path: Path) -> None:
        """Initialize chunk repository.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

        # Run any pending migrations
        if db_path.exists():
            migrate_database(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with foreign keys enabled.

        Reuses an existing connection if available, otherwise creates a new one.

        Returns:
            SQLite connection object.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SQLiteChunkRepository":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit context manager, closing the database connection."""
        self.close()
        return False

    def add(self, chunk: Chunk) -> None:
        """Add or update a chunk in the repository.

        Uses UPSERT semantics based on (tree_sha, path, start_line, end_line).
        The chunk.id is computed from these fields and doesn't need to be stored separately.

        Args:
            chunk: The chunk to store.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        path_str = str(chunk.path)
        now = time.time()

        # UPSERT: insert or update if (tree_sha, path, start_line, end_line) exists
        cursor.execute(
                """
                INSERT INTO chunks (
                    chunk_id, project_id, path, lang, symbol, start_line, end_line,
                    content, content_hash, file_hash, tree_sha, rev, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tree_sha, path, start_line, end_line) DO UPDATE SET
                    chunk_id = excluded.chunk_id,
                    project_id = excluded.project_id,
                    lang = excluded.lang,
                    symbol = excluded.symbol,
                    content = excluded.content,
                    content_hash = excluded.content_hash,
                    file_hash = excluded.file_hash,
                    rev = excluded.rev
                """,
                (
                    chunk.id,  # chunk.id is the computed chunk_id
                    chunk.project_id,
                    path_str,
                    chunk.lang,
                    chunk.symbol,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.content,
                    chunk.content_hash,
                    chunk.file_hash,
                    chunk.tree_sha,
                    chunk.rev,
                    now,
                ),
        )
        conn.commit()

    def get(self, chunk_id: str) -> Chunk | None:
        """Retrieve a chunk by its ID.

        Args:
            chunk_id: The unique identifier for the chunk.

        Returns:
            The chunk if found, None otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Use chunk_id column for O(1) lookup
        cursor.execute(
                """
                SELECT chunk_id, project_id, path, lang, symbol, start_line, end_line,
                       content, content_hash, file_hash, tree_sha, rev
                FROM chunks
                WHERE chunk_id = ?
                """,
                (chunk_id,)
        )

        row = cursor.fetchone()
        if row is None:
            return None

        return Chunk(
                id=row[0],  # chunk_id from database
                project_id=row[1],
                path=Path(row[2]),
                lang=row[3],
                symbol=row[4],
                start_line=row[5],
                end_line=row[6],
                content=row[7],
                content_hash=row[8],
                file_hash=row[9],
                tree_sha=row[10],
                rev=row[11],
        )

    def find_by_id_prefix(self, prefix: str) -> list[Chunk]:
        """Find chunks whose ID starts with the given prefix.

        Supports short hash lookups (like git's short SHAs).

        Args:
            prefix: The chunk ID prefix to match.

        Returns:
            List of chunks whose ID starts with the prefix.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Use LIKE with prefix pattern for efficient prefix search
        # The index on chunk_id will make this reasonably fast
        cursor.execute(
                """
                SELECT chunk_id, project_id, path, lang, symbol, start_line, end_line,
                       content, content_hash, file_hash, tree_sha, rev
                FROM chunks
                WHERE chunk_id LIKE ? || '%'
                """,
                (prefix,)
        )

        rows = cursor.fetchall()
        chunks = []
        for row in rows:
            chunk = Chunk(
                id=row[0],  # chunk_id from database
                project_id=row[1],
                path=Path(row[2]),
                lang=row[3],
                symbol=row[4],
                start_line=row[5],
                end_line=row[6],
                content=row[7],
                content_hash=row[8],
                file_hash=row[9],
                tree_sha=row[10],
                rev=row[11],
            )
            chunks.append(chunk)

        return chunks

    def find_by_content_hash(self, content_hash: str) -> list[Chunk]:
        """Find chunks with matching content hash.

        Args:
            content_hash: blake3 hash of chunk content.

        Returns:
            List of chunks with matching hash.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
                """
                SELECT project_id, path, lang, symbol, start_line, end_line,
                       content, content_hash, file_hash, tree_sha, rev
                FROM chunks
                WHERE content_hash = ?
                """,
                (content_hash,),
        )

        rows = cursor.fetchall()
        chunks = []
        for row in rows:
            project_id = row[0]
            path = Path(row[1])
            start_line = row[4]
            end_line = row[5]

            chunk = Chunk(
                id=Chunk.compute_id(project_id, path, start_line, end_line),
                project_id=project_id,
                path=path,
                lang=row[2],
                symbol=row[3],
                start_line=start_line,
                end_line=end_line,
                content=row[6],
                content_hash=row[7],
                file_hash=row[8],
                tree_sha=row[9],
                rev=row[10],
            )
            chunks.append(chunk)

        return chunks

    def delete(self, chunk_id: str) -> None:
        """Delete a chunk by ID.

        Deletes directly using the indexed chunk_id column for efficiency.

        Args:
            chunk_id: The chunk identifier to delete.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete directly by chunk_id (which is indexed)
        cursor.execute(
            "DELETE FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        )
        conn.commit()

    def delete_by_path(self, path: Path, tree_sha: str) -> int:
        """Delete all chunks for a given file path and tree SHA.

        This is more efficient than calling delete() for each chunk.
        Used for handling deleted files during incremental sync.

        Args:
            path: File path relative to repository root.
            tree_sha: Tree SHA to delete chunks for.

        Returns:
            Number of chunks deleted.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        path_str = str(path)

        # Delete all chunks for this path and tree_sha
        cursor.execute(
                """
                DELETE FROM chunks
                WHERE tree_sha = ? AND path = ?
                """,
                (tree_sha, path_str),
        )
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count

    def delete_all_for_path(self, path: Path) -> int:
        """Delete all chunks for a given file path across all tree SHAs.

        This is used when re-indexing a file to remove all old chunks
        before adding new ones, preventing duplicate accumulation across
        multiple syncs.

        Args:
            path: File path relative to repository root.

        Returns:
            Number of chunks deleted.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        path_str = str(path)

        # Delete all chunks for this path regardless of tree_sha
        cursor.execute(
                """
                DELETE FROM chunks
                WHERE path = ?
                """,
                (path_str,),
        )
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count

    def delete_old_tree_shas(self, current_tree_sha: str) -> int:
        """Delete all chunks that don't match the current tree SHA.

        This cleans up stale chunks from previous syncs.

        Args:
            current_tree_sha: The current tree SHA to keep.

        Returns:
            Number of chunks deleted.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete all chunks with different tree_sha
        cursor.execute(
                """
                DELETE FROM chunks
                WHERE tree_sha != ?
                """,
                (current_tree_sha,),
        )
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count

    def list_all(
        self,
        path_filter: str | None = None,
        lang_filter: str | None = None,
    ) -> list[Chunk]:
        """List all chunks, optionally filtered.

        Args:
            path_filter: Optional glob pattern to filter by file path.
            lang_filter: Optional language code to filter by.

        Returns:
            List of matching chunks.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Build query with optional filters
        query = """
                SELECT project_id, path, lang, symbol, start_line, end_line,
                       content, content_hash, file_hash, tree_sha, rev
                FROM chunks
                WHERE 1=1
        """
        params: list[str] = []

        if path_filter:
            # SQLite GLOB for pattern matching (Unix-style wildcards)
            query += " AND path GLOB ?"
            params.append(path_filter)

        if lang_filter:
            query += " AND lang = ?"
            params.append(lang_filter)

        query += " ORDER BY path, start_line"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        chunks = []
        for row in rows:
            project_id = row[0]
            path = Path(row[1])
            start_line = row[4]
            end_line = row[5]

            chunk = Chunk(
                id=Chunk.compute_id(project_id, path, start_line, end_line),
                project_id=project_id,
                path=path,
                lang=row[2],
                symbol=row[3],
                start_line=start_line,
                end_line=end_line,
                content=row[6],
                content_hash=row[7],
                file_hash=row[8],
                tree_sha=row[9],
                rev=row[10],
            )
            chunks.append(chunk)

        return chunks

    def count_chunks(self) -> int:
        """Get total number of chunks in the repository.

        Returns:
            Total count of all chunks.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks")
        result = cursor.fetchone()
        return result[0] if result else 0

    def count_unique_files(self) -> int:
        """Get count of unique files that have been indexed.

        Returns:
            Number of distinct file paths in chunks.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT path) FROM chunks")
        result = cursor.fetchone()
        return result[0] if result else 0
