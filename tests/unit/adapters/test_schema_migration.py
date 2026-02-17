"""Tests for schema migration safety and rollback behavior.

Tests that:
1. Migration creates a version tracking table (migration_history)
2. Migrations are idempotent (safe to re-run)
3. Failed migration does not leave database in inconsistent state
4. Database backup is created before migration
5. Migration version tracking records which migrations were applied

Addresses GitHub issue #436: Schema migration lacks transaction rollback on failure.
"""

import sqlite3
import time
from pathlib import Path

import pytest

from ember.adapters.sqlite.schema import (
    SCHEMA_VERSION,
    check_schema_version,
    init_database,
    migrate_database,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def v1_database(tmp_path: Path) -> Path:
    """Create a version 1 database (without chunk_id column).

    This simulates a database created before the v1->v2 migration
    was introduced.
    """
    db_path = tmp_path / "v1_test.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create the original v1 schema (no chunk_id column)
    cursor.execute("""
        CREATE TABLE chunks (
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

    cursor.execute("""
        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE vectors (
            chunk_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            dim INTEGER NOT NULL,
            model_fingerprint TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE tags (
            chunk_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (chunk_id, key),
            FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            last_indexed_at REAL NOT NULL
        )
    """)

    # Set schema version to 1
    cursor.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', '1')"
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def v1_database_with_data(v1_database: Path) -> Path:
    """Create a version 1 database with some chunk data to migrate."""
    conn = sqlite3.connect(v1_database)
    cursor = conn.cursor()

    for i in range(5):
        cursor.execute(
            """
            INSERT INTO chunks
            (project_id, path, lang, symbol, start_line, end_line,
             content, content_hash, file_hash, tree_sha, rev, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "test_project",
                f"src/file_{i}.py",
                "py",
                f"func_{i}",
                i * 10 + 1,
                (i + 1) * 10,
                f"def func_{i}(): pass",
                f"hash_{i}",
                f"fhash_{i}",
                "a" * 40,
                "HEAD",
                time.time(),
            ),
        )

    conn.commit()
    conn.close()
    return v1_database


# =============================================================================
# Migration version tracking tests
# =============================================================================


class TestMigrationVersionTracking:
    """Tests for migration history tracking table."""

    def test_migration_creates_history_table(
        self, v1_database: Path
    ) -> None:
        """After migration, a migration_history table should exist."""
        migrate_database(v1_database)

        conn = sqlite3.connect(v1_database)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='migration_history'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "migration_history table was not created"

    def test_migration_records_applied_version(
        self, v1_database: Path
    ) -> None:
        """Applied migrations should be recorded in migration_history."""
        migrate_database(v1_database)

        conn = sqlite3.connect(v1_database)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT version, description FROM migration_history ORDER BY version"
        )
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) >= 1
        versions = [row[0] for row in rows]
        assert 2 in versions, "Migration to version 2 should be recorded"

    def test_migration_records_timestamp(self, v1_database: Path) -> None:
        """Migration history should include when the migration was applied."""
        migrate_database(v1_database)

        conn = sqlite3.connect(v1_database)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT applied_at FROM migration_history WHERE version = 2"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] is not None, "applied_at timestamp should be set"

    def test_already_migrated_skips_gracefully(
        self, v1_database: Path
    ) -> None:
        """Running migration twice should not fail or duplicate records."""
        migrate_database(v1_database)
        migrate_database(v1_database)

        conn = sqlite3.connect(v1_database)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM migration_history WHERE version = 2"
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, "Migration should only be recorded once"

    def test_current_version_database_skips_migration(
        self, tmp_path: Path
    ) -> None:
        """A database already at the current version should not be migrated."""
        db_path = tmp_path / "current.db"
        init_database(db_path)

        # Should be a no-op
        migrate_database(db_path)

        # Schema version should remain at SCHEMA_VERSION
        assert check_schema_version(db_path) == SCHEMA_VERSION


# =============================================================================
# Idempotency tests
# =============================================================================


class TestMigrationIdempotency:
    """Tests that migrations are safe to re-run."""

    def test_migration_is_idempotent_without_data(
        self, v1_database: Path
    ) -> None:
        """Running migration multiple times on empty database is safe."""
        migrate_database(v1_database)
        migrate_database(v1_database)
        migrate_database(v1_database)

        # Should end up at current version
        assert check_schema_version(v1_database) == SCHEMA_VERSION

    def test_migration_is_idempotent_with_data(
        self, v1_database_with_data: Path
    ) -> None:
        """Running migration multiple times on database with data is safe."""
        migrate_database(v1_database_with_data)
        migrate_database(v1_database_with_data)

        # Check data is intact
        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 5, "All original chunks should still exist"

    def test_chunk_ids_not_duplicated_on_rerun(
        self, v1_database_with_data: Path
    ) -> None:
        """chunk_id values should not change if migration is re-run."""
        migrate_database(v1_database_with_data)

        # Get chunk_ids after first migration
        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT id, chunk_id FROM chunks ORDER BY id")
        first_run_ids = cursor.fetchall()
        conn.close()

        # Run migration again
        migrate_database(v1_database_with_data)

        # Get chunk_ids after second migration
        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT id, chunk_id FROM chunks ORDER BY id")
        second_run_ids = cursor.fetchall()
        conn.close()

        assert first_run_ids == second_run_ids, (
            "chunk_ids should be identical across migration re-runs"
        )

    def test_index_not_duplicated_on_rerun(
        self, v1_database_with_data: Path
    ) -> None:
        """The unique index on chunk_id should not cause errors on re-run."""
        migrate_database(v1_database_with_data)
        # Second run should not raise due to CREATE UNIQUE INDEX IF NOT EXISTS
        migrate_database(v1_database_with_data)

        # Verify index exists
        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_chunks_chunk_id'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "Index on chunk_id should exist"


# =============================================================================
# Failure recovery tests
# =============================================================================


class TestMigrationFailureRecovery:
    """Tests that a partially-applied migration can be recovered from.

    SQLite has limitations with DDL in transactions (ALTER TABLE commits
    implicitly in some versions). Instead of relying on full transactional
    rollback of DDL, we ensure migrations are idempotent so they can be
    safely re-run after a partial failure.
    """

    def test_partial_migration_column_added_but_no_data(
        self, v1_database_with_data: Path
    ) -> None:
        """Simulate crash after ALTER TABLE but before data backfill.

        The chunk_id column exists but has all NULL values and schema
        version is still 1. Re-running migration should complete successfully.
        """
        # Manually apply only the ALTER TABLE step (simulating partial failure)
        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE chunks ADD COLUMN chunk_id TEXT")
        conn.commit()
        conn.close()

        # Schema version is still 1 since we didn't update it
        assert check_schema_version(v1_database_with_data) == 1

        # Re-running migration should complete all remaining steps
        migrate_database(v1_database_with_data)

        # Should now be at current version
        assert check_schema_version(v1_database_with_data) == SCHEMA_VERSION

        # All chunks should have chunk_ids
        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE chunk_id IS NULL")
        null_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chunks")
        total_count = cursor.fetchone()[0]
        conn.close()

        assert null_count == 0, "All chunks should have chunk_ids"
        assert total_count == 5, "All original chunks should still exist"

    def test_partial_migration_some_chunk_ids_filled(
        self, v1_database_with_data: Path
    ) -> None:
        """Simulate crash after some chunk_ids were backfilled but not all.

        Column exists, some rows have chunk_id, some are NULL.
        Re-running migration should fill in the remaining NULLs.
        """
        import blake3

        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()

        # Add column
        cursor.execute("ALTER TABLE chunks ADD COLUMN chunk_id TEXT")

        # Backfill only the first 2 rows (simulating partial completion)
        cursor.execute(
            "SELECT id, project_id, path, start_line, end_line "
            "FROM chunks ORDER BY id LIMIT 2"
        )
        rows = cursor.fetchall()
        for row in rows:
            db_id, project_id, path, start_line, end_line = row
            key = f"{project_id}:{path}:{start_line}:{end_line}"
            chunk_id = blake3.blake3(key.encode()).hexdigest()[:16]
            cursor.execute(
                "UPDATE chunks SET chunk_id = ? WHERE id = ?",
                (chunk_id, db_id),
            )
        conn.commit()
        conn.close()

        # Schema version is still 1
        assert check_schema_version(v1_database_with_data) == 1

        # Re-running migration should complete
        migrate_database(v1_database_with_data)

        assert check_schema_version(v1_database_with_data) == SCHEMA_VERSION

        # All 5 chunks should have chunk_ids
        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE chunk_id IS NULL")
        null_count = cursor.fetchone()[0]
        conn.close()

        assert null_count == 0, "All chunks should have chunk_ids after recovery"

    def test_partial_migration_column_and_index_but_no_version_update(
        self, v1_database_with_data: Path
    ) -> None:
        """Simulate crash after index creation but before version update.

        Column exists, data backfilled, index created, but schema_version
        not yet updated. Re-running should just update the version.
        """
        import blake3

        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()

        # Add column
        cursor.execute("ALTER TABLE chunks ADD COLUMN chunk_id TEXT")

        # Backfill all rows
        cursor.execute(
            "SELECT id, project_id, path, start_line, end_line FROM chunks"
        )
        rows = cursor.fetchall()
        for row in rows:
            db_id, project_id, path, start_line, end_line = row
            key = f"{project_id}:{path}:{start_line}:{end_line}"
            chunk_id = blake3.blake3(key.encode()).hexdigest()[:16]
            cursor.execute(
                "UPDATE chunks SET chunk_id = ? WHERE id = ?",
                (chunk_id, db_id),
            )

        # Create index
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_chunk_id "
            "ON chunks(chunk_id)"
        )

        conn.commit()
        conn.close()

        # Schema version still 1
        assert check_schema_version(v1_database_with_data) == 1

        # Re-running migration should just update version
        migrate_database(v1_database_with_data)

        assert check_schema_version(v1_database_with_data) == SCHEMA_VERSION

    def test_schema_version_only_updated_on_success(
        self, v1_database: Path
    ) -> None:
        """Schema version should only be updated when migration fully succeeds."""
        migrate_database(v1_database)

        assert check_schema_version(v1_database) == SCHEMA_VERSION

        # Verify version was properly updated
        conn = sqlite3.connect(v1_database)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM meta WHERE key = 'schema_version'")
        row = cursor.fetchone()
        conn.close()

        assert int(row[0]) == SCHEMA_VERSION


# =============================================================================
# Database backup tests
# =============================================================================


class TestMigrationBackup:
    """Tests that database is backed up before migration."""

    def test_backup_created_before_migration(
        self, v1_database_with_data: Path
    ) -> None:
        """A backup file should be created before migration starts."""
        original_size = v1_database_with_data.stat().st_size

        migrate_database(v1_database_with_data)

        # Look for backup file
        backup_files = list(
            v1_database_with_data.parent.glob("*.db.backup_v1")
        )
        assert len(backup_files) == 1, (
            "Exactly one backup file should be created"
        )

        # Backup should be the same size as the original
        backup_size = backup_files[0].stat().st_size
        assert backup_size == original_size

    def test_backup_is_valid_database(
        self, v1_database_with_data: Path
    ) -> None:
        """The backup should be a valid, usable SQLite database."""
        migrate_database(v1_database_with_data)

        backup_files = list(
            v1_database_with_data.parent.glob("*.db.backup_v1")
        )
        assert len(backup_files) == 1

        # Should be able to open and query the backup
        conn = sqlite3.connect(backup_files[0])
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 5, "Backup should contain original data"

    def test_no_backup_when_already_current(self, tmp_path: Path) -> None:
        """No backup should be created if database is already at current version."""
        db_path = tmp_path / "current.db"
        init_database(db_path)

        migrate_database(db_path)

        backup_files = list(db_path.parent.glob("*.backup_*"))
        assert len(backup_files) == 0, (
            "No backup should be created for current databases"
        )

    def test_backup_not_overwritten_on_rerun(
        self, v1_database_with_data: Path
    ) -> None:
        """If a backup already exists, it should not be overwritten.

        This protects the original backup if migration fails and is retried.
        """
        # Create first backup via migration
        migrate_database(v1_database_with_data)

        backup_files = list(
            v1_database_with_data.parent.glob("*.db.backup_v1")
        )
        assert len(backup_files) == 1
        first_backup_mtime = backup_files[0].stat().st_mtime

        # Running migration again should not recreate backup
        # (already at current version)
        migrate_database(v1_database_with_data)

        backup_files = list(
            v1_database_with_data.parent.glob("*.db.backup_v1")
        )
        assert len(backup_files) == 1
        assert backup_files[0].stat().st_mtime == first_backup_mtime


# =============================================================================
# Data integrity tests
# =============================================================================


class TestMigrationDataIntegrity:
    """Tests that migration preserves existing data correctly."""

    def test_existing_chunks_preserved(
        self, v1_database_with_data: Path
    ) -> None:
        """All existing chunks should be preserved after migration."""
        migrate_database(v1_database_with_data)

        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT path, symbol, content FROM chunks ORDER BY path"
        )
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 5
        for i, row in enumerate(rows):
            assert row[0] == f"src/file_{i}.py"
            assert row[1] == f"func_{i}"
            assert row[2] == f"def func_{i}(): pass"

    def test_chunk_ids_computed_correctly(
        self, v1_database_with_data: Path
    ) -> None:
        """chunk_id values should be computed using blake3 hash."""
        import blake3

        migrate_database(v1_database_with_data)

        conn = sqlite3.connect(v1_database_with_data)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT project_id, path, start_line, end_line, chunk_id "
            "FROM chunks"
        )
        rows = cursor.fetchall()
        conn.close()

        for project_id, path, start_line, end_line, chunk_id in rows:
            key = f"{project_id}:{path}:{start_line}:{end_line}"
            expected_id = blake3.blake3(key.encode()).hexdigest()[:16]
            assert chunk_id == expected_id, (
                f"chunk_id mismatch for {path}: "
                f"expected {expected_id}, got {chunk_id}"
            )

    def test_meta_table_version_updated(
        self, v1_database_with_data: Path
    ) -> None:
        """Schema version in meta table should be updated to current version."""
        migrate_database(v1_database_with_data)
        assert check_schema_version(v1_database_with_data) == SCHEMA_VERSION
