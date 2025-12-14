"""Tests for domain entities."""

from pathlib import Path

import pytest

from ember.domain.entities import Chunk, Query, SearchResult, SearchResultSet


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


# =============================================================================
# Query validation tests
# =============================================================================


class TestQueryValidation:
    """Tests for Query entity validation."""

    def test_query_valid_creation(self):
        """Test creating a valid Query."""
        query = Query(text="search term", topk=10)
        assert query.text == "search term"
        assert query.topk == 10

    def test_query_default_topk(self):
        """Test Query uses default topk of 20."""
        query = Query(text="search term")
        assert query.topk == 20

    def test_query_empty_text_raises_error(self):
        """Test that empty query text raises ValueError."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query(text="")

    def test_query_whitespace_only_text_raises_error(self):
        """Test that whitespace-only query text raises ValueError."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query(text="   ")

    def test_query_topk_zero_raises_error(self):
        """Test that topk=0 raises ValueError."""
        with pytest.raises(ValueError, match="topk must be positive"):
            Query(text="search", topk=0)

    def test_query_topk_negative_raises_error(self):
        """Test that negative topk raises ValueError."""
        with pytest.raises(ValueError, match="topk must be positive"):
            Query(text="search", topk=-5)

    def test_query_topk_positive_valid(self):
        """Test that positive topk values are valid."""
        query = Query(text="search", topk=1)
        assert query.topk == 1

        query = Query(text="search", topk=100)
        assert query.topk == 100


# =============================================================================
# Chunk validation tests
# =============================================================================


class TestChunkValidation:
    """Tests for Chunk entity validation."""

    def test_chunk_valid_creation(self):
        """Test creating a valid Chunk."""
        chunk = Chunk(
            id="test_id",
            project_id="proj",
            path=Path("file.py"),
            lang="py",
            symbol="func",
            start_line=1,
            end_line=10,
            content="code",
            content_hash="hash",
            file_hash="fhash",
            tree_sha="tree",
            rev="HEAD",
        )
        assert chunk.start_line == 1
        assert chunk.end_line == 10

    def test_chunk_start_line_zero_raises_error(self):
        """Test that start_line=0 raises ValueError (1-indexed)."""
        with pytest.raises(ValueError, match="Line numbers must be >= 1"):
            Chunk(
                id="test_id",
                project_id="proj",
                path=Path("file.py"),
                lang="py",
                symbol="func",
                start_line=0,
                end_line=10,
                content="code",
                content_hash="hash",
                file_hash="fhash",
                tree_sha="tree",
                rev="HEAD",
            )

    def test_chunk_end_line_zero_raises_error(self):
        """Test that end_line=0 raises ValueError (1-indexed)."""
        with pytest.raises(ValueError, match="Line numbers must be >= 1"):
            Chunk(
                id="test_id",
                project_id="proj",
                path=Path("file.py"),
                lang="py",
                symbol="func",
                start_line=1,
                end_line=0,
                content="code",
                content_hash="hash",
                file_hash="fhash",
                tree_sha="tree",
                rev="HEAD",
            )

    def test_chunk_negative_line_numbers_raises_error(self):
        """Test that negative line numbers raise ValueError."""
        with pytest.raises(ValueError, match="Line numbers must be >= 1"):
            Chunk(
                id="test_id",
                project_id="proj",
                path=Path("file.py"),
                lang="py",
                symbol="func",
                start_line=-1,
                end_line=10,
                content="code",
                content_hash="hash",
                file_hash="fhash",
                tree_sha="tree",
                rev="HEAD",
            )

    def test_chunk_start_greater_than_end_raises_error(self):
        """Test that start_line > end_line raises ValueError."""
        with pytest.raises(ValueError, match="start_line.*>.*end_line"):
            Chunk(
                id="test_id",
                project_id="proj",
                path=Path("file.py"),
                lang="py",
                symbol="func",
                start_line=20,
                end_line=10,
                content="code",
                content_hash="hash",
                file_hash="fhash",
                tree_sha="tree",
                rev="HEAD",
            )

    def test_chunk_start_equals_end_valid(self):
        """Test that start_line == end_line is valid (single line chunk)."""
        chunk = Chunk(
            id="test_id",
            project_id="proj",
            path=Path("file.py"),
            lang="py",
            symbol="func",
            start_line=5,
            end_line=5,
            content="code",
            content_hash="hash",
            file_hash="fhash",
            tree_sha="tree",
            rev="HEAD",
        )
        assert chunk.start_line == chunk.end_line == 5


# =============================================================================
# SearchResultSet tests (#265)
# =============================================================================


class TestSearchResultSet:
    """Tests for SearchResultSet entity."""

    @pytest.fixture
    def sample_chunk(self) -> Chunk:
        """Create a sample chunk for testing."""
        return Chunk(
            id="test_id",
            project_id="proj",
            path=Path("file.py"),
            lang="py",
            symbol="func",
            start_line=1,
            end_line=10,
            content="def foo(): pass",
            content_hash="hash",
            file_hash="fhash",
            tree_sha="tree",
            rev="HEAD",
        )

    @pytest.fixture
    def sample_result(self, sample_chunk: Chunk) -> SearchResult:
        """Create a sample search result for testing."""
        return SearchResult(
            chunk=sample_chunk,
            score=0.95,
            rank=1,
            preview="def foo(): pass",
        )

    def test_search_result_set_empty(self):
        """Test creating empty SearchResultSet."""
        result_set = SearchResultSet(results=[])
        assert len(result_set) == 0
        assert not result_set.is_degraded
        assert result_set.warning is None

    def test_search_result_set_with_results(self, sample_result: SearchResult):
        """Test SearchResultSet with results."""
        result_set = SearchResultSet(
            results=[sample_result],
            requested_count=10,
            missing_chunks=0,
        )
        assert len(result_set) == 1
        assert not result_set.is_degraded
        assert result_set.warning is None

    def test_search_result_set_is_degraded(self, sample_result: SearchResult):
        """Test is_degraded property when chunks are missing."""
        result_set = SearchResultSet(
            results=[sample_result],
            requested_count=10,
            missing_chunks=5,
            warning="Some chunks missing",
        )
        assert result_set.is_degraded
        assert result_set.warning == "Some chunks missing"

    def test_search_result_set_iteration(self, sample_result: SearchResult):
        """Test that SearchResultSet is iterable."""
        result_set = SearchResultSet(
            results=[sample_result, sample_result],
            requested_count=10,
        )
        results_list = list(result_set)
        assert len(results_list) == 2
        assert all(r == sample_result for r in results_list)

    def test_search_result_set_len(self, sample_result: SearchResult):
        """Test __len__ returns number of results."""
        result_set = SearchResultSet(
            results=[sample_result, sample_result, sample_result],
            requested_count=10,
        )
        assert len(result_set) == 3
