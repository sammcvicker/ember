"""SQLite database schema for ember index storage.

This module defines the database schema and initialization logic for the ember
index database. The schema is designed for efficient hybrid search (FTS5 + vectors)
with git-aware incremental indexing.

Schema follows PRD §4 requirements:
- chunks: Core chunk metadata with git tracking
- chunk_text: FTS5 virtual table for full-text search
- vectors: Vector embeddings for semantic search
- meta: System metadata (model, version, etc.)
- tags: Custom metadata tags
- files: File tracking for incremental sync

Migration safety (issue #436):
- Database is backed up before migration (shutil.copy)
- Migration history is tracked in a migration_history table
- All migrations are idempotent (safe to re-run after partial failure)
- DML operations (UPDATE, INSERT) use transactions for rollback on failure
"""

import logging
import shutil
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 2


def init_database(db_path: Path) -> None:
    """Initialize a new ember index database with complete schema.

    Creates all tables, indexes, and default metadata entries.
    This is called by the init command to set up a new .ember/ directory.

    Args:
        db_path: Path to the SQLite database file (typically .ember/index.db)

    Raises:
        sqlite3.Error: If database creation fails
    """
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        _create_tables(conn)
        _create_indexes(conn)
        _insert_default_meta(conn)
        conn.commit()
    finally:
        conn.close()


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create all database tables.

    Args:
        conn: Open SQLite connection
    """
    cursor = conn.cursor()

    # chunks: Core chunk metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT UNIQUE,
            project_id TEXT,
            path TEXT NOT NULL,
            lang TEXT,
            symbol TEXT,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            tree_sha TEXT,
            rev TEXT,
            created_at REAL NOT NULL,
            UNIQUE(tree_sha, path, start_line, end_line)
        )
    """)

    # chunk_text: FTS5 virtual table for full-text search
    # tokenize='porter' uses Porter stemming for better English matching
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_text USING fts5(
            content,
            path,
            symbol,
            lang,
            content='chunks',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """)

    # Triggers to keep FTS5 table in sync with chunks table
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunk_text(rowid, content, path, symbol, lang)
            VALUES (new.id, new.content, new.path, new.symbol, new.lang);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            DELETE FROM chunk_text WHERE rowid = old.id;
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            DELETE FROM chunk_text WHERE rowid = old.id;
            INSERT INTO chunk_text(rowid, content, path, symbol, lang)
            VALUES (new.id, new.content, new.path, new.symbol, new.lang);
        END
    """)

    # vectors: Vector embeddings for semantic search
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vectors (
            chunk_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            dim INTEGER NOT NULL,
            model_fingerprint TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
        )
    """)

    # meta: System metadata (model, version, chunking params)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # tags: Custom metadata tags (e.g., team=search)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            chunk_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (chunk_id, key),
            FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
        )
    """)

    # files: File tracking for incremental sync
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            last_indexed_at REAL NOT NULL
        )
    """)


def _create_indexes(conn: sqlite3.Connection) -> None:
    """Create database indexes for query performance.

    Args:
        conn: Open SQLite connection
    """
    cursor = conn.cursor()

    # Index for git-aware queries (find chunks by tree SHA and path)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_tree_path
        ON chunks(tree_sha, path)
    """)

    # Index for content-based deduplication
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_content_hash
        ON chunks(content_hash)
    """)

    # Index for file-based queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_path
        ON chunks(path)
    """)

    # Index for symbol lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_symbol
        ON chunks(symbol) WHERE symbol IS NOT NULL
    """)

    # Index for tag queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tags_key_value
        ON tags(key, value)
    """)


def _insert_default_meta(conn: sqlite3.Connection) -> None:
    """Insert default metadata entries.

    Args:
        conn: Open SQLite connection
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO meta (key, value) VALUES
        ('schema_version', ?),
        ('created_at', datetime('now')),
        ('index_version', '0.1.0')
    """,
        (str(SCHEMA_VERSION),),
    )


def check_schema_version(db_path: Path) -> int:
    """Check the schema version of an existing database.

    Args:
        db_path: Path to the SQLite database

    Returns:
        Schema version number (0 if database doesn't exist or has no version)
    """
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM meta WHERE key = 'schema_version'")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _ensure_migration_history_table(conn: sqlite3.Connection) -> None:
    """Create the migration_history table if it does not exist.

    This table tracks which migrations have been applied, preventing
    duplicate application and providing an audit trail.

    Args:
        conn: Open SQLite connection
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migration_history (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _is_migration_applied(conn: sqlite3.Connection, version: int) -> bool:
    """Check if a specific migration version has been recorded as applied.

    Args:
        conn: Open SQLite connection
        version: Migration version number to check

    Returns:
        True if the migration is recorded in migration_history
    """
    cursor = conn.execute(
        "SELECT 1 FROM migration_history WHERE version = ?", (version,)
    )
    return cursor.fetchone() is not None


def _record_migration(
    conn: sqlite3.Connection, version: int, description: str
) -> None:
    """Record a successfully applied migration in the history table.

    Args:
        conn: Open SQLite connection
        version: Migration version number
        description: Human-readable description of the migration
    """
    conn.execute(
        "INSERT OR IGNORE INTO migration_history (version, description) "
        "VALUES (?, ?)",
        (version, description),
    )


def _backup_database(db_path: Path, current_version: int) -> None:
    """Create a backup of the database before migration.

    The backup filename includes the current schema version so multiple
    backups from different migration paths do not collide.

    If a backup already exists (e.g., from a previous failed attempt),
    it is preserved and not overwritten.

    Args:
        db_path: Path to the SQLite database file
        current_version: Current schema version (used in backup filename)
    """
    backup_path = db_path.parent / f"{db_path.name}.backup_v{current_version}"
    if not backup_path.exists():
        shutil.copy2(db_path, backup_path)
        logger.info("Database backed up to %s", backup_path)


def _get_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    """Get the set of column names for a table.

    Args:
        conn: Open SQLite connection
        table: Table name to inspect

    Returns:
        Set of column name strings
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")  # noqa: S608
    return {row[1] for row in cursor.fetchall()}


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate from schema version 1 to 2: Add chunk_id column.

    This migration is fully idempotent. Each step checks whether it has
    already been applied before executing:

    1. ALTER TABLE to add chunk_id column (skipped if column exists)
    2. Backfill chunk_id for rows where it is NULL
    3. Create unique index on chunk_id (uses IF NOT EXISTS)
    4. Update schema version in meta table
    5. Record migration in migration_history

    SQLite note: ALTER TABLE implicitly commits any open transaction,
    so we cannot wrap DDL + DML in a single transaction. Instead,
    we make each step idempotent so the migration is safe to re-run
    after a partial failure.

    Args:
        conn: Open SQLite connection
    """
    import blake3

    cursor = conn.cursor()

    # Step 1: Add chunk_id column if it does not exist
    columns = _get_column_names(conn, "chunks")
    if "chunk_id" not in columns:
        cursor.execute("ALTER TABLE chunks ADD COLUMN chunk_id TEXT")
        logger.info("Added chunk_id column to chunks table")

    # Step 2: Backfill chunk_id for any rows that still have NULL
    # This handles both fresh migration and recovery from partial failure
    cursor.execute("""
        SELECT id, project_id, path, start_line, end_line
        FROM chunks
        WHERE chunk_id IS NULL
    """)
    rows = cursor.fetchall()

    if rows:
        for row in rows:
            db_id, project_id, path, start_line, end_line = row
            key = f"{project_id}:{path}:{start_line}:{end_line}"
            chunk_id = blake3.blake3(key.encode()).hexdigest()[:16]
            cursor.execute(
                "UPDATE chunks SET chunk_id = ? WHERE id = ?",
                (chunk_id, db_id),
            )
        logger.info("Backfilled chunk_id for %d rows", len(rows))

    # Step 3: Create unique index (IF NOT EXISTS makes this idempotent)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_chunk_id "
        "ON chunks(chunk_id)"
    )

    # Step 4: Update schema version
    cursor.execute(
        "UPDATE meta SET value = ? WHERE key = 'schema_version'",
        (str(2),),
    )

    # Step 5: Record migration in history
    _record_migration(conn, 2, "Add chunk_id column with blake3 hash backfill")

    conn.commit()


def migrate_database(db_path: Path) -> None:
    """Migrate database schema to the latest version.

    Safety guarantees:
    - A backup copy of the database is created before any changes
    - A migration_history table tracks which migrations have been applied
    - All migrations are idempotent (safe to re-run after partial failure)
    - DML changes are committed atomically where possible

    Args:
        db_path: Path to the SQLite database

    Raises:
        sqlite3.Error: If a migration step fails. The database backup
            can be used to restore the original state.
    """
    current_version = check_schema_version(db_path)

    if current_version >= SCHEMA_VERSION:
        return  # Already at latest version

    # Back up the database before making any changes
    _backup_database(db_path, current_version)

    conn = sqlite3.connect(db_path)
    try:
        # Ensure migration tracking table exists
        _ensure_migration_history_table(conn)
        conn.commit()

        # Apply migrations in order
        if current_version < 2 and not _is_migration_applied(conn, 2):
            _migrate_v1_to_v2(conn)
    finally:
        conn.close()
