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
"""

import sqlite3
from pathlib import Path

# Schema version for migrations
SCHEMA_VERSION = 1


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
