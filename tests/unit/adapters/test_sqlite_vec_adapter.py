"""Unit tests for SqliteVecAdapter dimension handling.

Tests for issue #249: SqliteVecAdapter hardcodes 768 dimensions, breaks non-Jina models.
"""

import sqlite3
from pathlib import Path

import pytest

from ember.adapters.sqlite.schema import init_database
from ember.adapters.vss.sqlite_vec_adapter import DimensionMismatchError, SqliteVecAdapter


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create an initialized database."""
    path = tmp_path / "test.db"
    init_database(path)
    return path


def test_sqlite_vec_adapter_uses_default_768_dimension(db_path: Path) -> None:
    """Test that default dimension is 768 (Jina)."""
    adapter = SqliteVecAdapter(db_path)
    assert adapter.vector_dim == 768


def test_sqlite_vec_adapter_accepts_custom_dimension(db_path: Path) -> None:
    """Test that custom dimension can be passed."""
    adapter = SqliteVecAdapter(db_path, vector_dim=384)
    assert adapter.vector_dim == 384


def test_sqlite_vec_adapter_creates_table_with_correct_dimension(tmp_path: Path) -> None:
    """Test that vec_chunks table is created with the specified dimension.

    This is the key bug fix test for issue #249. The vec0 table should be
    created with the dimension specified at construction time, not hardcoded 768.
    """
    db_path = tmp_path / "test.db"
    init_database(db_path)

    # Create adapter with 384 dimensions (MiniLM/BGE)
    adapter = SqliteVecAdapter(db_path, vector_dim=384)

    # Verify the table was created with correct dimension by checking schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query the table schema - vec0 tables store their config in the internal schema
    cursor.execute("SELECT sql FROM sqlite_master WHERE name = 'vec_chunks'")
    row = cursor.fetchone()
    conn.close()
    adapter.close()

    # The CREATE statement should contain float[384]
    assert row is not None, "vec_chunks table should exist"
    create_sql = row[0]
    assert "float[384]" in create_sql, f"Expected float[384] in: {create_sql}"


def test_sqlite_vec_adapter_dimension_mismatch_raises_custom_error(tmp_path: Path) -> None:
    """Test that querying with wrong dimension raises DimensionMismatchError.

    This ensures users get a clear, actionable error when model dimensions don't match.
    """
    db_path = tmp_path / "test.db"
    init_database(db_path)

    # Create adapter with 384 dimensions
    adapter = SqliteVecAdapter(db_path, vector_dim=384)

    # Try to query with a 768-dimensional vector (wrong!)
    wrong_dim_vector = [0.1] * 768

    with pytest.raises(DimensionMismatchError) as exc_info:
        adapter.query(wrong_dim_vector, topk=10)

    # Check error attributes
    assert exc_info.value.expected == 384
    assert exc_info.value.received == 768

    # Check error message is helpful
    error_msg = str(exc_info.value)
    assert "384" in error_msg
    assert "768" in error_msg
    assert "ember sync --force" in error_msg


def test_sqlite_vec_adapter_correct_dimension_succeeds(tmp_path: Path) -> None:
    """Test that querying with correct dimension works."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    # Create adapter with 384 dimensions
    adapter = SqliteVecAdapter(db_path, vector_dim=384)

    # Query with correct dimension (384)
    correct_dim_vector = [0.1] * 384

    # Should not raise - no vectors yet so empty results
    results = adapter.query(correct_dim_vector, topk=10)
    assert isinstance(results, list)
    adapter.close()


def test_sqlite_vec_adapter_dimension_384_for_minilm(db_path: Path) -> None:
    """Test that MiniLM's 384 dimensions work correctly."""
    adapter = SqliteVecAdapter(db_path, vector_dim=384)

    # Query with 384-dim vector
    vector = [0.5] * 384
    results = adapter.query(vector, topk=5)

    # Should succeed without dimension errors
    assert isinstance(results, list)
    adapter.close()


def test_sqlite_vec_adapter_dimension_768_for_jina(db_path: Path) -> None:
    """Test that Jina's 768 dimensions work correctly."""
    adapter = SqliteVecAdapter(db_path, vector_dim=768)

    # Query with 768-dim vector
    vector = [0.5] * 768
    results = adapter.query(vector, topk=5)

    # Should succeed without dimension errors
    assert isinstance(results, list)
    adapter.close()
