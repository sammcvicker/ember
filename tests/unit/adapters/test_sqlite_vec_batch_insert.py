"""Unit tests for SqliteVecAdapter batch insert optimization.

Tests for issue #296: use batch inserts in sqlite_vec_adapter._sync_vectors()
"""

import sqlite3
import struct
import time
from pathlib import Path

import pytest
import sqlite_vec

from ember.adapters.sqlite.schema import init_database
from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter


def _get_vec_connection(db_path: Path) -> sqlite3.Connection:
    """Get a connection with sqlite-vec extension loaded."""
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create an initialized database."""
    path = tmp_path / "test.db"
    init_database(path)
    return path


def _insert_test_chunks_and_vectors(
    db_path: Path,
    num_vectors: int,
    vector_dim: int = 384,
) -> None:
    """Insert test chunks and vectors into the database.

    Creates chunks and vectors entries that will be synced by SqliteVecAdapter.

    Args:
        db_path: Path to the test database.
        num_vectors: Number of vectors to insert.
        vector_dim: Dimension of vectors.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for i in range(num_vectors):
        # Insert chunk
        cursor.execute(
            """
            INSERT INTO chunks (
                chunk_id, project_id, path, lang, symbol,
                start_line, end_line, content, content_hash, file_hash,
                tree_sha, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"chunk_{i:06d}",
                "test_project",
                f"src/file_{i}.py",
                "python",
                f"function_{i}",
                1,
                10,
                f"def function_{i}(): pass",
                f"content_hash_{i}",
                f"file_hash_{i}",
                "abc123",
                0.0,
            ),
        )
        chunk_db_id = cursor.lastrowid

        # Insert vector - create a simple normalized vector
        vector = [1.0 / (vector_dim ** 0.5)] * vector_dim
        blob = struct.pack(f"{vector_dim}f", *vector)
        cursor.execute(
            """
            INSERT INTO vectors (chunk_id, embedding, dim, model_fingerprint)
            VALUES (?, ?, ?, ?)
            """,
            (chunk_db_id, blob, vector_dim, "test_model"),
        )

    conn.commit()
    conn.close()


def test_sync_vectors_correctness_small_batch(db_path: Path) -> None:
    """Test that batch sync correctly populates vec_chunks for small batches."""
    num_vectors = 10
    vector_dim = 384

    _insert_test_chunks_and_vectors(db_path, num_vectors, vector_dim)

    # Create adapter - this triggers _sync_vectors()
    adapter = SqliteVecAdapter(db_path, vector_dim=vector_dim)

    # Verify all vectors were synced
    conn = _get_vec_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vec_chunks")
    vec_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM vec_chunk_mapping")
    mapping_count = cursor.fetchone()[0]
    conn.close()

    assert vec_count == num_vectors, f"Expected {num_vectors} vec_chunks, got {vec_count}"
    assert mapping_count == num_vectors, f"Expected {num_vectors} mappings, got {mapping_count}"

    adapter.close()


def test_sync_vectors_correctness_large_batch(db_path: Path) -> None:
    """Test that batch sync correctly populates vec_chunks for larger batches."""
    num_vectors = 500
    vector_dim = 384

    _insert_test_chunks_and_vectors(db_path, num_vectors, vector_dim)

    # Create adapter - this triggers _sync_vectors()
    adapter = SqliteVecAdapter(db_path, vector_dim=vector_dim)

    # Verify all vectors were synced
    conn = _get_vec_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vec_chunks")
    vec_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM vec_chunk_mapping")
    mapping_count = cursor.fetchone()[0]
    conn.close()

    assert vec_count == num_vectors, f"Expected {num_vectors} vec_chunks, got {vec_count}"
    assert mapping_count == num_vectors, f"Expected {num_vectors} mappings, got {mapping_count}"

    adapter.close()


def test_sync_vectors_mapping_integrity(db_path: Path) -> None:
    """Test that vec_chunk_mapping correctly maps to chunks."""
    num_vectors = 50
    vector_dim = 384

    _insert_test_chunks_and_vectors(db_path, num_vectors, vector_dim)

    adapter = SqliteVecAdapter(db_path, vector_dim=vector_dim)

    # Verify mappings point to valid chunks
    conn = _get_vec_connection(db_path)
    cursor = conn.cursor()

    # Check that all mappings have valid chunk references
    cursor.execute("""
        SELECT COUNT(*)
        FROM vec_chunk_mapping m
        JOIN chunks c ON m.chunk_db_id = c.id
    """)
    valid_mappings = cursor.fetchone()[0]

    # Check that vec_rowids match actual vec_chunks rows
    cursor.execute("""
        SELECT COUNT(*)
        FROM vec_chunk_mapping m
        JOIN vec_chunks v ON m.vec_rowid = v.rowid
    """)
    valid_vec_refs = cursor.fetchone()[0]

    conn.close()

    assert valid_mappings == num_vectors, "All mappings should reference valid chunks"
    assert valid_vec_refs == num_vectors, "All mappings should reference valid vec_chunks rows"

    adapter.close()


def test_sync_vectors_query_works_after_sync(db_path: Path) -> None:
    """Test that queries work correctly after batch sync."""
    num_vectors = 100
    vector_dim = 384

    _insert_test_chunks_and_vectors(db_path, num_vectors, vector_dim)

    adapter = SqliteVecAdapter(db_path, vector_dim=vector_dim)

    # Query with a similar vector
    query_vector = [1.0 / (vector_dim ** 0.5)] * vector_dim
    results = adapter.query(query_vector, topk=10)

    # Should get results
    assert len(results) == 10, f"Expected 10 results, got {len(results)}"

    # Results should have valid chunk_ids
    for chunk_id, similarity in results:
        assert chunk_id.startswith("chunk_"), f"Invalid chunk_id: {chunk_id}"
        assert 0.0 <= similarity <= 1.0, f"Similarity out of range: {similarity}"

    adapter.close()


def test_sync_vectors_incremental_sync(db_path: Path) -> None:
    """Test that incremental sync works (only syncs new vectors)."""
    vector_dim = 384

    # First batch
    _insert_test_chunks_and_vectors(db_path, 50, vector_dim)
    adapter = SqliteVecAdapter(db_path, vector_dim=vector_dim)

    # Verify first batch
    conn = _get_vec_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vec_chunks")
    count1 = cursor.fetchone()[0]
    conn.close()

    assert count1 == 50

    # Add more vectors directly to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for i in range(50, 100):
        cursor.execute(
            """
            INSERT INTO chunks (
                chunk_id, project_id, path, lang, symbol,
                start_line, end_line, content, content_hash, file_hash,
                tree_sha, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"chunk_{i:06d}",
                "test_project",
                f"src/file_{i}.py",
                "python",
                f"function_{i}",
                1,
                10,
                f"def function_{i}(): pass",
                f"content_hash_{i}",
                f"file_hash_{i}",
                "abc123",
                0.0,
            ),
        )
        chunk_db_id = cursor.lastrowid
        vector = [1.0 / (vector_dim ** 0.5)] * vector_dim
        blob = struct.pack(f"{vector_dim}f", *vector)
        cursor.execute(
            """
            INSERT INTO vectors (chunk_id, embedding, dim, model_fingerprint)
            VALUES (?, ?, ?, ?)
            """,
            (chunk_db_id, blob, vector_dim, "test_model"),
        )
    conn.commit()
    conn.close()

    # Mark dirty to trigger sync on next query (simulates external vector addition)
    adapter.mark_dirty()

    # Query triggers sync
    query_vector = [1.0 / (vector_dim ** 0.5)] * vector_dim
    adapter.query(query_vector, topk=10)

    # Verify all vectors now synced
    conn = _get_vec_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vec_chunks")
    count2 = cursor.fetchone()[0]
    conn.close()

    assert count2 == 100, f"Expected 100 vectors after incremental sync, got {count2}"

    adapter.close()


@pytest.mark.benchmark
def test_sync_vectors_performance_benchmark(db_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Benchmark test for batch insert performance.

    This test measures the sync time for different batch sizes to verify
    that the batch insert optimization provides performance improvement.

    Run with: pytest -v -k benchmark --capture=no
    """
    vector_dim = 384
    batch_sizes = [100, 500, 1000]

    results = []

    for batch_size in batch_sizes:
        # Create fresh database
        test_db = db_path.parent / f"test_batch_{batch_size}.db"
        init_database(test_db)

        # Insert test data
        _insert_test_chunks_and_vectors(test_db, batch_size, vector_dim)

        # Measure sync time
        start = time.perf_counter()
        adapter = SqliteVecAdapter(test_db, vector_dim=vector_dim)
        elapsed = time.perf_counter() - start

        adapter.close()
        results.append((batch_size, elapsed))

    # Print results
    with capsys.disabled():
        print("\n\nBatch Insert Performance:")
        print("-" * 40)
        for batch_size, elapsed in results:
            rate = batch_size / elapsed
            print(f"  {batch_size:5d} vectors: {elapsed:.3f}s ({rate:.0f} vec/s)")
        print("-" * 40)

    # Basic performance assertion: should handle 100 vectors in under 2 seconds
    # This is a very conservative threshold to avoid flaky tests
    assert results[0][1] < 2.0, "Sync of 100 vectors should take less than 2 seconds"
