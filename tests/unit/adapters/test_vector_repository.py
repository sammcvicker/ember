"""Unit tests for SQLiteVectorRepository."""

import struct
import tempfile
from pathlib import Path

import pytest

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
    for original, decoded_val in zip(test_vector, decoded):
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
    for original, decoded_val in zip(test_vector, decoded):
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
