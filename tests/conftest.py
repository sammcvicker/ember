"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest

from ember.domain.entities import Chunk


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for tests.

    Yields:
        Path to temporary directory (cleaned up after test).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunk() -> Chunk:
    """Create a sample chunk for testing.

    Returns:
        A Chunk instance with test data.
    """
    return Chunk(
        id="test_chunk_123",
        project_id="test_project",
        path=Path("src/example.py"),
        lang="py",
        symbol="test_function",
        start_line=10,
        end_line=20,
        content='def test_function():\n    return "hello"',
        content_hash=Chunk.compute_content_hash('def test_function():\n    return "hello"'),
        file_hash="abc123",
        tree_sha="def456",
        rev="HEAD",
    )


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """Create multiple sample chunks for testing.

    Returns:
        List of Chunk instances.
    """
    chunks = []
    for i in range(5):
        chunk = Chunk(
            id=f"chunk_{i}",
            project_id="test_project",
            path=Path(f"src/file_{i}.py"),
            lang="py",
            symbol=f"function_{i}",
            start_line=i * 10,
            end_line=(i * 10) + 10,
            content=f"def function_{i}():\n    pass",
            content_hash=Chunk.compute_content_hash(f"def function_{i}():\n    pass"),
            file_hash=f"hash_{i}",
            tree_sha="tree_sha_test",
            rev="HEAD",
        )
        chunks.append(chunk)
    return chunks
