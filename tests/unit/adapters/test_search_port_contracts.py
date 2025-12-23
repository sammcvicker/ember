"""Tests for search port contract compliance.

Verifies that TextSearch and VectorSearch implementations correctly implement
the documented contract semantics, including sync() behavior for sync-based
implementations.

Issue #359: VSS and FTS ports have no-op add() methods
"""

from pathlib import Path

import pytest

from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.sqlite.schema import init_database
from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create an initialized database."""
    path = tmp_path / "test.db"
    init_database(path)
    return path


class TestSQLiteFTSContract:
    """Tests for SQLiteFTS TextSearch port compliance."""

    def test_add_is_no_op_for_trigger_based_fts(self, db_path: Path) -> None:
        """Test that add() is a no-op for trigger-based FTS implementation.

        The SQLiteFTS adapter uses database triggers to keep the FTS5 index
        in sync with the chunks table. Therefore add() should be a no-op
        and not raise any errors.
        """
        fts = SQLiteFTS(db_path)

        # add() should be a silent no-op
        fts.add("chunk-1", "test content", {"path": "test.py", "lang": "python"})

        # Should not raise, should not affect query results
        results = fts.query("nonexistent")
        assert results == []

        fts.close()

    def test_sync_is_no_op_for_trigger_based_fts(self, db_path: Path) -> None:
        """Test that sync() is a no-op for trigger-based FTS implementation.

        Since database triggers automatically keep the FTS5 index in sync,
        sync() should be a no-op that can be called safely without side effects.
        """
        fts = SQLiteFTS(db_path)

        # sync() should be a silent no-op
        fts.sync()

        # Multiple calls should be fine (idempotent)
        fts.sync()
        fts.sync()

        fts.close()

    def test_fts_query_works_without_explicit_add(self, db_path: Path) -> None:
        """Test that FTS query works when data comes through triggers.

        When chunks are inserted directly into the chunks table, the FTS5
        triggers should automatically index them for search.
        """
        import time

        fts = SQLiteFTS(db_path)

        # Insert a chunk directly into the chunks table (bypassing add())
        conn = fts._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chunks (
                project_id, path, start_line, end_line, content, chunk_id, lang,
                content_hash, file_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "proj1",
                "test.py",
                1,
                10,
                "def hello_world(): pass",
                "proj1:test.py:1-10",
                "python",
                "abc123",
                "def456",
                time.time(),
            ),
        )
        conn.commit()

        # The FTS trigger should have indexed this chunk
        results = fts.query("hello_world")
        assert len(results) == 1
        assert results[0][0] == "proj1:test.py:1-10"

        fts.close()


class TestSqliteVecAdapterContract:
    """Tests for SqliteVecAdapter VectorSearch port compliance."""

    def test_add_is_no_op_for_sync_based_vec(self, db_path: Path) -> None:
        """Test that add() is a no-op for sync-based vector implementation.

        The SqliteVecAdapter syncs vectors from VectorRepository, so add()
        should be a no-op and not raise any errors.
        """
        vec = SqliteVecAdapter(db_path, vector_dim=384)

        # add() should be a silent no-op
        vec.add("chunk-1", [0.1] * 384)

        # Should not affect query results (no vectors actually added)
        results = vec.query([0.1] * 384, topk=10)
        assert results == []

        vec.close()

    def test_sync_pulls_from_vectors_table(self, db_path: Path) -> None:
        """Test that sync() pulls vectors from the vectors table.

        When vectors are added to the vectors table via VectorRepository,
        calling sync() (or sync_if_needed) should make them searchable.
        """
        import struct
        import time

        vec = SqliteVecAdapter(db_path, vector_dim=384)

        # First verify no results
        results = vec.query([0.1] * 384, topk=10)
        assert results == []

        # Insert a chunk and vector directly (simulating VectorRepository behavior)
        conn = vec._get_connection()
        cursor = conn.cursor()

        # Insert chunk with all required fields
        cursor.execute(
            """
            INSERT INTO chunks (
                project_id, path, start_line, end_line, content, chunk_id, lang,
                content_hash, file_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "proj1",
                "test.py",
                1,
                10,
                "test content",
                "proj1:test.py:1-10",
                "python",
                "abc123",
                "def456",
                time.time(),
            ),
        )
        chunk_id = cursor.lastrowid

        # Insert vector
        embedding = [0.5] * 384
        embedding_blob = struct.pack(f"{384}f", *embedding)
        cursor.execute(
            "INSERT INTO vectors (chunk_id, embedding, dim, model_fingerprint) VALUES (?, ?, ?, ?)",
            (chunk_id, embedding_blob, 384, "test-model-fp"),
        )
        conn.commit()

        # Mark dirty and sync
        vec.mark_dirty()
        vec.sync()

        # Now the vector should be searchable
        results = vec.query([0.5] * 384, topk=10)
        assert len(results) == 1
        assert results[0][0] == "proj1:test.py:1-10"

        vec.close()

    def test_sync_is_idempotent(self, db_path: Path) -> None:
        """Test that sync() is idempotent - multiple calls are safe.

        Calling sync() multiple times without data changes should have no
        effect after the first sync.
        """
        vec = SqliteVecAdapter(db_path, vector_dim=384)

        # Multiple sync calls should be fine
        vec.sync()
        vec.sync()
        vec.sync()

        # Should still work for queries
        results = vec.query([0.1] * 384, topk=10)
        assert results == []

        vec.close()

    def test_sync_if_needed_returns_correct_status(self, db_path: Path) -> None:
        """Test that sync_if_needed() returns whether sync was performed."""
        vec = SqliteVecAdapter(db_path, vector_dim=384)

        # First call after init should sync (dirty by default)
        # Actually on init it already syncs, so it should be False
        result = vec.sync_if_needed()
        assert result is False  # Already synced during __init__

        # Mark dirty and try again
        vec.mark_dirty()
        result = vec.sync_if_needed()
        assert result is True  # Should sync

        # Second call should not sync
        result = vec.sync_if_needed()
        assert result is False  # Already synced

        vec.close()

    def test_sync_via_protocol_method(self, db_path: Path) -> None:
        """Test that the sync() protocol method works correctly.

        The sync() method should wrap sync_if_needed() for protocol compliance.
        """
        vec = SqliteVecAdapter(db_path, vector_dim=384)

        # sync() should not raise
        vec.sync()

        # Mark dirty, then sync via protocol method
        vec.mark_dirty()
        vec.sync()

        # Calling again should be fine (idempotent)
        vec.sync()

        vec.close()
