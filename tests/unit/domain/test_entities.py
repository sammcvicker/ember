"""Tests for domain entities."""

from pathlib import Path

from ember.domain.entities import Chunk


def test_chunk_compute_content_hash():
    """Test content hash computation is deterministic."""
    content = "def foo():\n    pass"
    hash1 = Chunk.compute_content_hash(content)
    hash2 = Chunk.compute_content_hash(content)
    assert hash1 == hash2
    assert len(hash1) == 64  # blake3 produces 256-bit hash = 64 hex chars


def test_chunk_compute_id_deterministic():
    """Test chunk ID computation is deterministic."""
    chunk_id1 = Chunk.compute_id("proj", Path("file.py"), 1, 10)
    chunk_id2 = Chunk.compute_id("proj", Path("file.py"), 1, 10)
    assert chunk_id1 == chunk_id2


def test_chunk_compute_id_unique_for_different_inputs():
    """Test chunk IDs differ for different inputs."""
    id1 = Chunk.compute_id("proj", Path("file.py"), 1, 10)
    id2 = Chunk.compute_id("proj", Path("file.py"), 2, 10)
    id3 = Chunk.compute_id("proj", Path("other.py"), 1, 10)
    assert id1 != id2
    assert id1 != id3


def test_chunk_creation(sample_chunk):
    """Test chunk can be created with all fields."""
    assert sample_chunk.id == "test_chunk_123"
    assert sample_chunk.lang == "py"
    assert sample_chunk.symbol == "test_function"
    assert sample_chunk.start_line == 10
    assert sample_chunk.end_line == 20
