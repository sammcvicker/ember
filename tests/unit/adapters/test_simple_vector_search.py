"""Unit tests for SimpleVectorSearch adapter."""

import sqlite3
import struct
from pathlib import Path

import pytest

from ember.adapters.sqlite.schema import init_database
from ember.adapters.vss.simple_vector_search import SimpleVectorSearch


@pytest.fixture
def db_with_vectors(tmp_path: Path) -> Path:
    """Create a database with test vectors and chunks."""
    import time

    db_path = tmp_path / "test.db"
    init_database(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    now = time.time()

    # Insert test chunks (with created_at)
    chunks = [
        ("chunk_1", "test_proj", "file1.py", 1, 10, "content 1", "hash1", "fhash1", "python", None, "tree1", "work", now),
        ("chunk_2", "test_proj", "file2.py", 1, 10, "content 2", "hash2", "fhash2", "python", None, "tree1", "work", now),
        ("chunk_3", "test_proj", "file3.py", 1, 10, "content 3", "hash3", "fhash3", "python", None, "tree1", "work", now),
    ]
    cursor.executemany(
        """
        INSERT INTO chunks (chunk_id, project_id, path, start_line, end_line, content,
                           content_hash, file_hash, lang, symbol, tree_sha, rev, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        chunks,
    )

    # Get internal chunk IDs
    chunk_id_map = {}
    for chunk_id in ["chunk_1", "chunk_2", "chunk_3"]:
        cursor.execute("SELECT id FROM chunks WHERE chunk_id = ?", (chunk_id,))
        chunk_id_map[chunk_id] = cursor.fetchone()[0]

    # Insert test vectors (L2 normalized for cosine similarity = dot product)
    # chunk_1: [1.0, 0.0, 0.0] - points in x direction
    # chunk_2: [0.0, 1.0, 0.0] - points in y direction
    # chunk_3: [0.707, 0.707, 0.0] - points between x and y
    vectors = [
        (chunk_id_map["chunk_1"], struct.pack("3d", 1.0, 0.0, 0.0), 3, "test-model"),
        (chunk_id_map["chunk_2"], struct.pack("3d", 0.0, 1.0, 0.0), 3, "test-model"),
        (chunk_id_map["chunk_3"], struct.pack("3d", 0.707, 0.707, 0.0), 3, "test-model"),
    ]
    cursor.executemany(
        "INSERT INTO vectors (chunk_id, embedding, dim, model_fingerprint) VALUES (?, ?, ?, ?)",
        vectors,
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def search(db_with_vectors: Path) -> SimpleVectorSearch:
    """Create a SimpleVectorSearch instance with test data."""
    return SimpleVectorSearch(db_with_vectors)


class TestSimpleVectorSearchInit:
    """Tests for SimpleVectorSearch initialization."""

    def test_init_stores_db_path(self, tmp_path: Path) -> None:
        """Test that __init__ stores the db_path correctly."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)
        assert search.db_path == db_path

    def test_get_connection_returns_valid_connection(self, db_with_vectors: Path) -> None:
        """Test that _get_connection returns a valid SQLite connection."""
        search = SimpleVectorSearch(db_with_vectors)
        conn = search._get_connection()
        try:
            assert isinstance(conn, sqlite3.Connection)
            # Verify we can execute queries
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
        finally:
            conn.close()


class TestVectorDecoding:
    """Tests for _decode_vector method."""

    def test_decode_vector_returns_correct_values(self, tmp_path: Path) -> None:
        """Test that _decode_vector correctly decodes a binary blob."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        # Create a test blob with known values
        expected = [1.0, 2.0, 3.0]
        blob = struct.pack("3d", *expected)

        result = search._decode_vector(blob, 3)

        assert result == expected

    def test_decode_vector_handles_different_dimensions(self, tmp_path: Path) -> None:
        """Test that _decode_vector handles various dimensions."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        for dim in [1, 10, 100, 768]:
            expected = [float(i) for i in range(dim)]
            blob = struct.pack(f"{dim}d", *expected)
            result = search._decode_vector(blob, dim)
            assert result == expected

    def test_decode_vector_handles_negative_values(self, tmp_path: Path) -> None:
        """Test that _decode_vector handles negative values."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        expected = [-1.0, -0.5, 0.0, 0.5, 1.0]
        blob = struct.pack("5d", *expected)
        result = search._decode_vector(blob, 5)
        assert result == expected


class TestCosineSimilarity:
    """Tests for _cosine_similarity method."""

    def test_cosine_similarity_identical_vectors(self, tmp_path: Path) -> None:
        """Test that identical normalized vectors have similarity 1.0."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        vec = [1.0, 0.0, 0.0]  # L2 normalized
        similarity = search._cosine_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal_vectors(self, tmp_path: Path) -> None:
        """Test that orthogonal vectors have similarity 0.0."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = search._cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(0.0)

    def test_cosine_similarity_opposite_vectors(self, tmp_path: Path) -> None:
        """Test that opposite vectors have similarity -1.0."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        similarity = search._cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(-1.0)

    def test_cosine_similarity_45_degree_angle(self, tmp_path: Path) -> None:
        """Test vectors at 45 degrees have similarity ~0.707."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        vec1 = [1.0, 0.0, 0.0]
        # Normalized vector at 45 degrees from x-axis
        vec2 = [0.7071067811865476, 0.7071067811865476, 0.0]
        similarity = search._cosine_similarity(vec1, vec2)
        # cos(45 degrees) = sqrt(2)/2 ≈ 0.707
        assert similarity == pytest.approx(0.7071067811865476, rel=1e-6)


class TestAddMethod:
    """Tests for add method."""

    def test_add_is_noop(self, tmp_path: Path) -> None:
        """Test that add() is a no-op (vectors managed by VectorRepository)."""
        db_path = tmp_path / "test.db"
        search = SimpleVectorSearch(db_path)

        # Should not raise any exceptions
        search.add("chunk_id", [1.0, 2.0, 3.0])

        # Nothing to verify - it's a no-op by design


class TestQueryMethod:
    """Tests for query method."""

    def test_query_returns_top_k_results(self, search: SimpleVectorSearch) -> None:
        """Test that query returns the correct number of results."""
        query_vector = [1.0, 0.0, 0.0]  # Same as chunk_1

        results = search.query(query_vector, topk=2)

        assert len(results) == 2
        # Results should be tuples of (chunk_id, similarity)
        for chunk_id, similarity in results:
            assert isinstance(chunk_id, str)
            assert isinstance(similarity, float)

    def test_query_returns_results_sorted_by_similarity(self, search: SimpleVectorSearch) -> None:
        """Test that results are sorted by similarity (descending)."""
        query_vector = [1.0, 0.0, 0.0]  # Same as chunk_1

        results = search.query(query_vector, topk=3)

        similarities = [sim for _, sim in results]
        assert similarities == sorted(similarities, reverse=True)

    def test_query_finds_exact_match_first(self, search: SimpleVectorSearch) -> None:
        """Test that exact match has highest similarity."""
        query_vector = [1.0, 0.0, 0.0]  # Same as chunk_1

        results = search.query(query_vector, topk=3)

        # chunk_1 should be first with similarity ~1.0
        assert results[0][0] == "chunk_1"
        assert results[0][1] == pytest.approx(1.0, rel=1e-6)

    def test_query_orthogonal_vector_has_zero_similarity(self, search: SimpleVectorSearch) -> None:
        """Test that orthogonal vectors have zero similarity."""
        query_vector = [0.0, 0.0, 1.0]  # z-direction, orthogonal to all stored vectors

        results = search.query(query_vector, topk=3)

        # All similarities should be ~0.0
        for _, similarity in results:
            assert similarity == pytest.approx(0.0, abs=1e-6)

    def test_query_with_empty_index(self, tmp_path: Path) -> None:
        """Test query returns empty list when no vectors exist."""
        db_path = tmp_path / "test.db"
        init_database(db_path)
        search = SimpleVectorSearch(db_path)

        query_vector = [1.0, 0.0, 0.0]
        results = search.query(query_vector, topk=10)

        assert results == []

    def test_query_default_topk_is_100(self, search: SimpleVectorSearch) -> None:
        """Test that default topk is 100."""
        query_vector = [1.0, 0.0, 0.0]

        # With only 3 vectors, should return all 3
        results = search.query(query_vector)

        assert len(results) == 3

    def test_query_topk_larger_than_available(self, search: SimpleVectorSearch) -> None:
        """Test that topk larger than available vectors returns all vectors."""
        query_vector = [1.0, 0.0, 0.0]

        # Request more than available
        results = search.query(query_vector, topk=1000)

        # Should return all 3 vectors
        assert len(results) == 3

    def test_query_topk_one(self, search: SimpleVectorSearch) -> None:
        """Test that topk=1 returns only the best match."""
        query_vector = [1.0, 0.0, 0.0]  # Same as chunk_1

        results = search.query(query_vector, topk=1)

        assert len(results) == 1
        assert results[0][0] == "chunk_1"

    def test_query_similarity_ordering_with_diagonal_vector(self, search: SimpleVectorSearch) -> None:
        """Test similarity ordering with a query between x and y axes."""
        # Query vector same as chunk_3 (diagonal)
        query_vector = [0.707, 0.707, 0.0]

        results = search.query(query_vector, topk=3)

        # chunk_3 should be first (exact match)
        assert results[0][0] == "chunk_3"
        # chunk_1 and chunk_2 should have equal similarity (~0.707)
        similarities = {results[1][0]: results[1][1], results[2][0]: results[2][1]}
        assert similarities["chunk_1"] == pytest.approx(similarities["chunk_2"], rel=1e-2)


class TestIntegration:
    """Integration tests for SimpleVectorSearch."""

    def test_full_workflow_with_realistic_dimensions(self, tmp_path: Path) -> None:
        """Test with realistic 768-dimensional vectors."""
        import random
        import time

        random.seed(42)
        now = time.time()

        db_path = tmp_path / "test.db"
        init_database(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Insert chunks
        for i in range(5):
            cursor.execute(
                """
                INSERT INTO chunks (chunk_id, project_id, path, start_line, end_line, content,
                                   content_hash, file_hash, lang, symbol, tree_sha, rev, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"chunk_{i}", "proj", f"file{i}.py", 1, 10, f"content {i}",
                 f"hash{i}", f"fhash{i}", "python", None, "tree1", "work", now),
            )

        # Get internal IDs and create vectors
        for i in range(5):
            cursor.execute("SELECT id FROM chunks WHERE chunk_id = ?", (f"chunk_{i}",))
            internal_id = cursor.fetchone()[0]

            # Create normalized 768-dim vector
            vector = [random.gauss(0, 1) for _ in range(768)]
            norm = sum(x * x for x in vector) ** 0.5
            vector = [x / norm for x in vector]

            blob = struct.pack("768d", *vector)
            cursor.execute(
                "INSERT INTO vectors (chunk_id, embedding, dim, model_fingerprint) VALUES (?, ?, ?, ?)",
                (internal_id, blob, 768, "test-model"),
            )

        conn.commit()
        conn.close()

        # Query with random vector
        search = SimpleVectorSearch(db_path)
        query_vector = [random.gauss(0, 1) for _ in range(768)]
        norm = sum(x * x for x in query_vector) ** 0.5
        query_vector = [x / norm for x in query_vector]

        results = search.query(query_vector, topk=3)

        assert len(results) == 3
        # All results should have similarities in valid range
        for _, similarity in results:
            assert -1.0 <= similarity <= 1.0
