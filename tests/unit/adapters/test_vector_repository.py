"""Unit tests for SQLiteVectorRepository."""

import struct
from pathlib import Path

import pytest

from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.schema import init_database
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.domain.entities import Chunk


@pytest.fixture
def vector_repo(tmp_path: Path) -> SQLiteVectorRepository:
    """Create a VectorRepository with an initialized database."""
    db_path = tmp_path / "test.db"
    init_database(db_path)
    return SQLiteVectorRepository(db_path)


def test_vector_encoding_uses_float32(vector_repo: SQLiteVectorRepository) -> None:
    """Test that vector encoding uses float32 (4 bytes per dimension)."""
    # Create a test vector
    test_vector = [1.0, 2.0, 3.0]

    # Encode the vector
    encoded = vector_repo._encode_vector(test_vector)

    # Verify it's using float32 (4 bytes per dimension)
    expected_size = len(test_vector) * 4  # 4 bytes for float32
    assert len(encoded) == expected_size, f"Expected {expected_size} bytes, got {len(encoded)}"

    # Verify it can be decoded as float32
    decoded = list(struct.unpack(f"{len(test_vector)}f", encoded))
    assert len(decoded) == len(test_vector)


def test_vector_round_trip_preserves_precision(vector_repo: SQLiteVectorRepository) -> None:
    """Test that encoding and decoding a vector preserves float32 precision."""
    # Create a test vector with various float values
    test_vector = [
        1.0,
        -1.0,
        0.0,
        3.141592653589793,  # pi
        2.718281828459045,  # e
        0.000001,  # small number
        1000000.0,  # large number
    ]

    # Encode then decode
    encoded = vector_repo._encode_vector(test_vector)
    decoded = vector_repo._decode_vector(encoded, len(test_vector))

    # Verify same length
    assert len(decoded) == len(test_vector)

    # Verify values are preserved within float32 precision
    # Float32 has ~7 decimal digits of precision
    for original, decoded_val in zip(test_vector, decoded, strict=False):
        # Use relative tolerance for float32 precision
        assert abs(decoded_val - original) < abs(original) * 1e-6 or abs(decoded_val - original) < 1e-6


def test_vector_round_trip_realistic_embedding(vector_repo: SQLiteVectorRepository) -> None:
    """Test round-trip with realistic embedding dimensions (768)."""
    # Create a 768-dimensional vector (like Jina v2 Code embeddings)
    import random
    random.seed(42)  # For reproducibility
    test_vector = [random.uniform(-1.0, 1.0) for _ in range(768)]

    # Encode then decode
    encoded = vector_repo._encode_vector(test_vector)
    decoded = vector_repo._decode_vector(encoded, len(test_vector))

    # Verify dimensions match
    assert len(decoded) == 768

    # Verify all values are preserved within float32 precision
    for original, decoded_val in zip(test_vector, decoded, strict=False):
        assert abs(decoded_val - original) < abs(original) * 1e-6 or abs(decoded_val - original) < 1e-6


def test_vector_encoding_consistency_with_sqlite_vec(vector_repo: SQLiteVectorRepository) -> None:
    """Test that VectorRepository encoding is consistent with SqliteVecAdapter.

    Both should use float32 to avoid precision loss during sync.
    """
    test_vector = [1.0, 2.0, 3.0]

    # VectorRepository encoding
    encoded = vector_repo._encode_vector(test_vector)

    # Verify it's float32 (same as what SqliteVecAdapter expects)
    # This is the same format: struct.pack(f"{len(vector)}f", *vector)
    expected_encoding = struct.pack(f"{len(test_vector)}f", *test_vector)

    assert encoded == expected_encoding, "VectorRepository should use same float32 encoding as SqliteVecAdapter"


def test_dimension_validation_accepts_correct_dimension(tmp_path: Path) -> None:
    """Test that validation passes when embedding has correct dimension."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    # Create vector repo with expected dimension
    vector_repo = SQLiteVectorRepository(db_path, expected_dim=768)
    chunk_repo = SQLiteChunkRepository(db_path)

    # Create a test chunk with all required fields
    content = "test content"
    chunk = Chunk(
        id=Chunk.compute_id("test_proj", Path("test.py"), 1, 10),
        project_id="test_proj",
        path=Path("test.py"),
        start_line=1,
        end_line=10,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash=Chunk.compute_content_hash("file1"),
        lang="py",
        symbol=None,
        tree_sha="a" * 40,
        rev="worktree",
    )
    chunk_repo.add(chunk)

    # Create embedding with correct dimension
    embedding = [1.0] * 768

    # Should not raise
    vector_repo.add(chunk.id, embedding, "test-model-v1")


def test_dimension_validation_rejects_wrong_dimension(tmp_path: Path) -> None:
    """Test that validation raises ValueError for wrong dimension."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    # Create vector repo with expected dimension
    vector_repo = SQLiteVectorRepository(db_path, expected_dim=768)
    chunk_repo = SQLiteChunkRepository(db_path)

    # Create a test chunk with all required fields
    content = "test content 2"
    chunk = Chunk(
        id=Chunk.compute_id("test_proj", Path("test.py"), 1, 10),
        project_id="test_proj",
        path=Path("test.py"),
        start_line=1,
        end_line=10,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash=Chunk.compute_content_hash("file2"),
        lang="py",
        symbol=None,
        tree_sha="b" * 40,
        rev="worktree",
    )
    chunk_repo.add(chunk)

    # Create embedding with WRONG dimension
    wrong_embedding = [1.0] * 512  # Wrong! Expected 768

    # Should raise ValueError with clear message
    with pytest.raises(ValueError) as exc_info:
        vector_repo.add(chunk.id, wrong_embedding, "test-model-v1")

    error_message = str(exc_info.value)
    assert "Invalid embedding dimension" in error_message
    assert "expected 768" in error_message
    assert "got 512" in error_message
    assert chunk.id in error_message


def test_dimension_validation_skipped_when_not_configured(tmp_path: Path) -> None:
    """Test that validation is skipped when expected_dim is None."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    # Create vector repo WITHOUT expected dimension
    vector_repo = SQLiteVectorRepository(db_path, expected_dim=None)
    chunk_repo = SQLiteChunkRepository(db_path)

    # Create a test chunk with all required fields
    content = "test content 3"
    chunk = Chunk(
        id=Chunk.compute_id("test_proj", Path("test.py"), 1, 10),
        project_id="test_proj",
        path=Path("test.py"),
        start_line=1,
        end_line=10,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash=Chunk.compute_content_hash("file3"),
        lang="py",
        symbol=None,
        tree_sha="c" * 40,
        rev="worktree",
    )
    chunk_repo.add(chunk)

    # Create embedding with any dimension (validation is disabled)
    embedding = [1.0] * 512  # Any size works

    # Should not raise even though dimension != 768
    vector_repo.add(chunk.id, embedding, "test-model-v1")
