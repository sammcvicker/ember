"""Integration tests for SQLite FileRepository adapter.

These tests exercise file tracking functionality with a real SQLite database.
"""

import time
from pathlib import Path

import pytest

from ember.adapters.sqlite import SQLiteFileRepository

# Note: db_path fixture is now in tests/conftest.py


@pytest.fixture
def file_repo(db_path: Path) -> SQLiteFileRepository:
    """Create a FileRepository instance for testing."""
    return SQLiteFileRepository(db_path)


def test_track_file(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test tracking a file stores all metadata correctly."""
    file_path = tmp_path / "test_file.py"
    file_hash = "abc123"
    size = 1024
    mtime = time.time()

    # Track the file
    file_repo.track_file(file_path, file_hash, size, mtime)

    # Retrieve and verify
    state = file_repo.get_file_state(file_path)
    assert state is not None
    assert state["file_hash"] == file_hash
    assert state["size"] == size
    assert state["mtime"] == mtime
    assert "last_indexed_at" in state


def test_track_file_updates_existing(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test tracking same file again updates the record (UPSERT)."""
    file_path = tmp_path / "test_file.py"

    # Initial tracking
    file_repo.track_file(file_path, "hash1", 100, 1000.0)

    # Update with new values
    file_repo.track_file(file_path, "hash2", 200, 2000.0)

    # Should have updated, not created duplicate
    state = file_repo.get_file_state(file_path)
    assert state is not None
    assert state["file_hash"] == "hash2"
    assert state["size"] == 200
    assert state["mtime"] == 2000.0


def test_get_file_state_nonexistent(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test getting state for untracked file returns None."""
    file_path = tmp_path / "nonexistent.py"
    state = file_repo.get_file_state(file_path)
    assert state is None


def test_get_all_tracked_files_empty(file_repo: SQLiteFileRepository):
    """Test getting all files when none are tracked returns empty list."""
    files = file_repo.get_all_tracked_files()
    assert files == []


def test_get_all_tracked_files(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test getting all tracked files returns correct list."""
    # Track multiple files
    file1 = tmp_path / "file1.py"
    file2 = tmp_path / "file2.py"
    file3 = tmp_path / "dir" / "file3.py"

    file_repo.track_file(file1, "hash1", 100, 1000.0)
    file_repo.track_file(file2, "hash2", 200, 2000.0)
    file_repo.track_file(file3, "hash3", 300, 3000.0)

    # Get all files
    tracked = file_repo.get_all_tracked_files()

    # Should return all 3 files as Path objects
    assert len(tracked) == 3
    assert all(isinstance(p, Path) for p in tracked)

    # Convert to strings for easier comparison
    tracked_strs = [str(p) for p in tracked]
    assert str(file1) in tracked_strs
    assert str(file2) in tracked_strs
    assert str(file3) in tracked_strs


def test_get_all_tracked_files_sorted(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test that get_all_tracked_files returns paths in sorted order."""
    # Track files in non-alphabetical order
    file_c = tmp_path / "c.py"
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"

    file_repo.track_file(file_c, "hash", 100, 1000.0)
    file_repo.track_file(file_a, "hash", 100, 1000.0)
    file_repo.track_file(file_b, "hash", 100, 1000.0)

    # Get all files
    tracked = file_repo.get_all_tracked_files()

    # Should be sorted by path
    tracked_names = [p.name for p in tracked]
    assert tracked_names == ["a.py", "b.py", "c.py"]


def test_last_indexed_at_timestamp(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test that last_indexed_at is automatically set to current time."""
    file_path = tmp_path / "test.py"

    before = time.time()
    file_repo.track_file(file_path, "hash", 100, 1000.0)
    after = time.time()

    state = file_repo.get_file_state(file_path)
    assert state is not None

    last_indexed = state["last_indexed_at"]
    assert isinstance(last_indexed, (int, float))
    # Should be between before and after timestamps
    assert before <= last_indexed <= after


def test_track_file_with_absolute_path(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test tracking works with absolute paths."""
    file_path = (tmp_path / "subdir" / "file.py").resolve()
    file_repo.track_file(file_path, "hash", 100, 1000.0)

    # Should be able to retrieve by same path
    state = file_repo.get_file_state(file_path)
    assert state is not None


def test_track_multiple_files_independence(file_repo: SQLiteFileRepository, tmp_path: Path):
    """Test that tracking multiple files maintains independence."""
    file1 = tmp_path / "file1.py"
    file2 = tmp_path / "file2.py"

    # Track two files with different metadata
    file_repo.track_file(file1, "hash1", 100, 1000.0)
    file_repo.track_file(file2, "hash2", 200, 2000.0)

    # Verify both have correct independent state
    state1 = file_repo.get_file_state(file1)
    state2 = file_repo.get_file_state(file2)

    assert state1["file_hash"] == "hash1"
    assert state1["size"] == 100

    assert state2["file_hash"] == "hash2"
    assert state2["size"] == 200


def test_file_repository_connection_cleanup(db_path: Path, tmp_path: Path):
    """Test that repository properly manages database connections."""
    # Create repo and perform operations
    repo = SQLiteFileRepository(db_path)
    file_path = tmp_path / "test.py"

    # Multiple operations should work without connection issues
    for i in range(5):
        repo.track_file(file_path, f"hash{i}", i * 100, i * 1000.0)

    # Final state should reflect last update
    state = repo.get_file_state(file_path)
    assert state["file_hash"] == "hash4"
