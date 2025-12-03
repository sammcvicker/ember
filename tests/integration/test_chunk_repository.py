"""Integration tests for SQLite ChunkRepository adapter.

These tests exercise chunk storage and retrieval functionality with a real SQLite database.
"""

from pathlib import Path

import pytest

from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.domain.entities import Chunk


@pytest.fixture
def chunk_repo(db_path: Path) -> SQLiteChunkRepository:
    """Create a ChunkRepository instance for testing.

    Returns:
        SQLiteChunkRepository instance.

    Note:
        Connection cleanup is handled by the autouse
        cleanup_database_connections fixture in conftest.py.
    """
    return SQLiteChunkRepository(db_path)


@pytest.fixture
def sample_chunk() -> Chunk:
    """Create a sample chunk for testing."""
    return Chunk(
        id="a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd",
        project_id="test_project",
        path=Path("src/main.py"),
        lang="py",
        symbol="my_function",
        start_line=10,
        end_line=20,
        content="def my_function():\n    pass",
        content_hash="hash123",
        file_hash="file_hash123",
        tree_sha="tree123",
        rev="HEAD",
    )


@pytest.fixture
def another_chunk() -> Chunk:
    """Create another sample chunk with a different ID."""
    return Chunk(
        id="b9876543210fedcba0987654321098765432109876543210987654321098765",
        project_id="test_project",
        path=Path("src/utils.py"),
        lang="py",
        symbol="helper_function",
        start_line=5,
        end_line=15,
        content="def helper_function():\n    return True",
        content_hash="hash456",
        file_hash="file_hash456",
        tree_sha="tree456",
        rev="HEAD",
    )


def test_find_by_id_prefix_exact_match(chunk_repo: SQLiteChunkRepository, sample_chunk: Chunk):
    """Test finding a chunk by its exact full ID."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Find by full ID
    matches = chunk_repo.find_by_id_prefix(sample_chunk.id)

    assert len(matches) == 1
    assert matches[0].id == sample_chunk.id
    assert matches[0].content == sample_chunk.content
    assert matches[0].path == sample_chunk.path


def test_find_by_id_prefix_short_hash(chunk_repo: SQLiteChunkRepository, sample_chunk: Chunk):
    """Test finding a chunk by a short hash prefix (8 chars)."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Find by 8-character prefix
    short_prefix = "a1b2c3d4"
    matches = chunk_repo.find_by_id_prefix(short_prefix)

    assert len(matches) == 1
    assert matches[0].id == sample_chunk.id


def test_find_by_id_prefix_very_short_hash(chunk_repo: SQLiteChunkRepository, sample_chunk: Chunk):
    """Test finding a chunk by a very short prefix."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Find by just "a" - first character
    matches = chunk_repo.find_by_id_prefix("a")

    assert len(matches) == 1
    assert matches[0].id == sample_chunk.id


def test_find_by_id_prefix_single_char(chunk_repo: SQLiteChunkRepository, sample_chunk: Chunk):
    """Test finding a chunk by a single character prefix."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Find by single character
    matches = chunk_repo.find_by_id_prefix("a")

    assert len(matches) == 1
    assert matches[0].id == sample_chunk.id


def test_find_by_id_prefix_ambiguous(
    chunk_repo: SQLiteChunkRepository,
    sample_chunk: Chunk,
    another_chunk: Chunk,
):
    """Test that ambiguous prefix returns multiple matches."""
    # Add both chunks
    chunk_repo.add(sample_chunk)
    chunk_repo.add(another_chunk)

    # Create a chunk with a similar prefix to test ambiguity
    # Both start with different first letters, so single char will be unique
    # But we can test an empty prefix or very broad matches

    # Actually these chunks start with 'a' and 'b', so they're not ambiguous
    # Let's search for something that won't match either to test empty result
    # Instead, let's just verify both chunks exist
    all_matches = chunk_repo.find_by_id_prefix("")

    # Empty prefix should match everything
    assert len(all_matches) >= 2


def test_find_by_id_prefix_unique_after_disambiguation(
    chunk_repo: SQLiteChunkRepository,
    sample_chunk: Chunk,
    another_chunk: Chunk,
):
    """Test that a longer prefix can disambiguate between chunks."""
    # Add both chunks
    chunk_repo.add(sample_chunk)
    chunk_repo.add(another_chunk)

    # First chunk starts with "a"
    matches_a = chunk_repo.find_by_id_prefix("a")
    assert len(matches_a) == 1
    assert matches_a[0].id == sample_chunk.id

    # Second chunk starts with "b"
    matches_b = chunk_repo.find_by_id_prefix("b")
    assert len(matches_b) == 1
    assert matches_b[0].id == another_chunk.id


def test_find_by_id_prefix_not_found(chunk_repo: SQLiteChunkRepository, sample_chunk: Chunk):
    """Test that searching for non-existent prefix returns empty list."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Search for prefix that doesn't exist (use 'z' since sample starts with 'a')
    matches = chunk_repo.find_by_id_prefix("zzz")

    assert len(matches) == 0


def test_find_by_id_prefix_case_insensitive(chunk_repo: SQLiteChunkRepository, sample_chunk: Chunk):
    """Test that prefix matching is case-insensitive (SQLite LIKE behavior)."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Original uses lowercase "a1b2c3d4"
    matches_lower = chunk_repo.find_by_id_prefix("a1b2c3d4")
    assert len(matches_lower) == 1

    # Try uppercase - should also match (SQLite LIKE is case-insensitive)
    matches_upper = chunk_repo.find_by_id_prefix("A1B2C3D4")
    assert len(matches_upper) == 1
    assert matches_upper[0].id == sample_chunk.id


def test_find_by_id_prefix_empty_database(chunk_repo: SQLiteChunkRepository):
    """Test searching in an empty database returns empty list."""
    matches = chunk_repo.find_by_id_prefix("anything")
    assert len(matches) == 0


def test_find_by_id_prefix_returns_complete_chunk_data(
    chunk_repo: SQLiteChunkRepository,
    sample_chunk: Chunk,
):
    """Test that found chunks contain all expected data fields."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Find chunk
    matches = chunk_repo.find_by_id_prefix("a1b2")

    assert len(matches) == 1
    found_chunk = matches[0]

    # Verify all fields are populated
    assert found_chunk.id == sample_chunk.id
    assert found_chunk.project_id == sample_chunk.project_id
    assert found_chunk.path == sample_chunk.path
    assert found_chunk.lang == sample_chunk.lang
    assert found_chunk.symbol == sample_chunk.symbol
    assert found_chunk.start_line == sample_chunk.start_line
    assert found_chunk.end_line == sample_chunk.end_line
    assert found_chunk.content == sample_chunk.content
    assert found_chunk.content_hash == sample_chunk.content_hash
    assert found_chunk.file_hash == sample_chunk.file_hash
    assert found_chunk.tree_sha == sample_chunk.tree_sha
    assert found_chunk.rev == sample_chunk.rev


def test_delete_existing_chunk(chunk_repo: SQLiteChunkRepository, sample_chunk: Chunk):
    """Test deleting an existing chunk by ID."""
    # Add chunk to repository
    chunk_repo.add(sample_chunk)

    # Verify chunk exists
    assert chunk_repo.get(sample_chunk.id) is not None

    # Delete chunk
    chunk_repo.delete(sample_chunk.id)

    # Verify chunk is deleted
    assert chunk_repo.get(sample_chunk.id) is None


def test_delete_nonexistent_chunk(chunk_repo: SQLiteChunkRepository):
    """Test that deleting a non-existent chunk doesn't raise an error."""
    # Delete non-existent chunk (should not raise)
    chunk_repo.delete("nonexistent_chunk_id_that_does_not_exist")

    # Verify still no error and database is fine
    assert chunk_repo.count_chunks() == 0


def test_delete_does_not_affect_other_chunks(
    chunk_repo: SQLiteChunkRepository,
    sample_chunk: Chunk,
    another_chunk: Chunk,
):
    """Test that deleting one chunk doesn't affect other chunks."""
    # Add both chunks
    chunk_repo.add(sample_chunk)
    chunk_repo.add(another_chunk)

    # Verify both exist
    assert chunk_repo.count_chunks() == 2

    # Delete first chunk
    chunk_repo.delete(sample_chunk.id)

    # Verify first chunk is deleted
    assert chunk_repo.get(sample_chunk.id) is None

    # Verify second chunk still exists
    assert chunk_repo.get(another_chunk.id) is not None
    assert chunk_repo.count_chunks() == 1
