"""Tests for domain entities."""

from pathlib import Path

import pytest

from ember.domain.entities import (
    Chunk,
    Query,
    SearchExplanation,
    SearchResult,
    SearchResultSet,
    SyncMode,
)
from ember.domain.value_objects import SUPPORTED_LANGUAGES, LanguageFilter, PathFilter


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

    @pytest.mark.parametrize(
        "text, topk, error_match",
        [
            pytest.param("", 10, "Query text cannot be empty", id="empty-text"),
            pytest.param("   ", 10, "Query text cannot be empty", id="whitespace-text"),
            pytest.param("search", 0, "topk must be positive", id="topk-zero"),
            pytest.param("search", -5, "topk must be positive", id="topk-negative"),
        ],
    )
    def test_query_invalid_creation(self, text, topk, error_match):
        """Test that invalid Query parameters raise ValueError."""
        with pytest.raises(ValueError, match=error_match):
            Query(text=text, topk=topk)

    @pytest.mark.parametrize("topk", [1, 100])
    def test_query_topk_positive_valid(self, topk):
        """Test that positive topk values are valid."""
        query = Query(text="search", topk=topk)
        assert query.topk == topk


class TestQueryImmutability:
    """Tests for Query immutability (frozen dataclass)."""

    @pytest.mark.parametrize(
        "attr, value",
        [
            pytest.param("text", "new text", id="text"),
            pytest.param("topk", 20, id="topk"),
            pytest.param("path_filter", PathFilter("*.py"), id="path-filter"),
        ],
    )
    def test_query_is_frozen(self, attr, value):
        """Test that Query instances cannot be modified after creation."""
        query = Query(text="search term", topk=10)
        with pytest.raises(AttributeError):
            setattr(query, attr, value)

    def test_query_hashable(self):
        """Test that frozen Query is hashable."""
        query1 = Query(text="search term", topk=10)
        query2 = Query(text="search term", topk=10)
        # Frozen dataclasses are hashable
        assert hash(query1) == hash(query2)
        # Can be used in sets
        query_set = {query1, query2}
        assert len(query_set) == 1


class TestQueryFromStrings:
    """Tests for Query.from_strings factory method."""

    def test_from_strings_basic(self):
        """Test creating Query from basic string inputs."""
        query = Query.from_strings(text="search term", topk=10)
        assert query.text == "search term"
        assert query.topk == 10
        assert query.path_filter is None
        assert query.lang_filter is None
        assert query.json_output is False

    def test_from_strings_with_path_filter(self):
        """Test creating Query with path filter string."""
        query = Query.from_strings(text="search", path_filter="*.py")
        assert isinstance(query.path_filter, PathFilter)
        assert str(query.path_filter) == "*.py"

    def test_from_strings_with_lang_filter(self):
        """Test creating Query with language filter string."""
        query = Query.from_strings(text="search", lang_filter="py")
        assert isinstance(query.lang_filter, LanguageFilter)
        assert str(query.lang_filter) == "py"

    def test_from_strings_with_both_filters(self):
        """Test creating Query with both filter strings."""
        query = Query.from_strings(
            text="search",
            topk=5,
            path_filter="src/**/*.py",
            lang_filter="py",
            json_output=True,
        )
        assert query.text == "search"
        assert query.topk == 5
        assert isinstance(query.path_filter, PathFilter)
        assert isinstance(query.lang_filter, LanguageFilter)
        assert query.json_output is True

    def test_from_strings_with_none_filters(self):
        """Test creating Query with explicit None filters."""
        query = Query.from_strings(text="search", path_filter=None, lang_filter=None)
        assert query.path_filter is None
        assert query.lang_filter is None

    def test_from_strings_validates_text(self):
        """Test that from_strings validates text."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query.from_strings(text="")
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query.from_strings(text="   ")

    def test_from_strings_validates_topk(self):
        """Test that from_strings validates topk."""
        with pytest.raises(ValueError, match="topk must be positive"):
            Query.from_strings(text="search", topk=0)
        with pytest.raises(ValueError, match="topk must be positive"):
            Query.from_strings(text="search", topk=-1)

    def test_from_strings_empty_path_filter_becomes_none(self):
        """Test that empty string path_filter becomes None."""
        # Empty string is treated as "no filter" (same as None)
        query = Query.from_strings(text="search", path_filter="")
        assert query.path_filter is None

    def test_from_strings_validates_path_filter(self):
        """Test that from_strings validates invalid path filter patterns."""
        # PathFilter rejects patterns with empty segments
        with pytest.raises(ValueError, match="contains empty path segment"):
            Query.from_strings(text="search", path_filter="foo//bar")

    def test_from_strings_validates_lang_filter(self):
        """Test that from_strings validates language filter."""
        with pytest.raises(ValueError, match="Unknown language"):
            Query.from_strings(text="search", lang_filter="unsupported_lang")


class TestQueryDirectConstruction:
    """Tests for direct Query construction with value objects."""

    def test_direct_construction_with_value_objects(self):
        """Test creating Query directly with PathFilter and LanguageFilter."""
        path_filter = PathFilter("*.py")
        lang_filter = LanguageFilter("py")
        query = Query(
            text="search",
            topk=10,
            path_filter=path_filter,
            lang_filter=lang_filter,
        )
        assert query.path_filter is path_filter
        assert query.lang_filter is lang_filter

    def test_direct_construction_validates(self):
        """Test that direct construction still validates text and topk."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query(text="", topk=10)
        with pytest.raises(ValueError, match="topk must be positive"):
            Query(text="search", topk=0)


# =============================================================================
# Chunk validation tests
# =============================================================================


class TestChunkValidation:
    """Tests for Chunk entity validation."""

    # Valid hash constants for tests
    VALID_CONTENT_HASH = "a" * 64
    VALID_FILE_HASH = "b" * 64
    VALID_TREE_SHA = "c" * 40

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
            content_hash=self.VALID_CONTENT_HASH,
            file_hash=self.VALID_FILE_HASH,
            tree_sha=self.VALID_TREE_SHA,
            rev="HEAD",
        )
        assert chunk.start_line == 1
        assert chunk.end_line == 10

    @pytest.mark.parametrize(
        "start, end, error_match",
        [
            pytest.param(0, 10, "Line numbers must be >= 1", id="start-zero"),
            pytest.param(1, 0, "Line numbers must be >= 1", id="end-zero"),
            pytest.param(-1, 10, "Line numbers must be >= 1", id="start-negative"),
            pytest.param(20, 10, "start_line.*>.*end_line", id="start-gt-end"),
        ],
    )
    def test_chunk_invalid_line_numbers(self, start, end, error_match):
        """Test that invalid line number combinations raise ValueError."""
        with pytest.raises(ValueError, match=error_match):
            Chunk(
                id="test_id",
                project_id="proj",
                path=Path("file.py"),
                lang="py",
                symbol="func",
                start_line=start,
                end_line=end,
                content="code",
                content_hash=self.VALID_CONTENT_HASH,
                file_hash=self.VALID_FILE_HASH,
                tree_sha=self.VALID_TREE_SHA,
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
            content_hash=self.VALID_CONTENT_HASH,
            file_hash=self.VALID_FILE_HASH,
            tree_sha=self.VALID_TREE_SHA,
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
            content_hash="a" * 64,
            file_hash="b" * 64,
            tree_sha="c" * 40,
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


# =============================================================================
# SyncMode enum tests (#271)
# =============================================================================


class TestSyncMode:
    """Tests for SyncMode enum."""

    @pytest.mark.parametrize(
        "member, string_value",
        [
            pytest.param(SyncMode.NONE, "none", id="none"),
            pytest.param(SyncMode.WORKTREE, "worktree", id="worktree"),
            pytest.param(SyncMode.STAGED, "staged", id="staged"),
        ],
    )
    def test_sync_mode_values_and_from_string(self, member, string_value):
        """Test SyncMode enum values and creation from string."""
        assert member == string_value
        assert SyncMode(string_value) == member

    def test_sync_mode_invalid_string_raises_error(self):
        """Test that invalid string raises ValueError."""
        with pytest.raises(ValueError):
            SyncMode("invalid")

    def test_sync_mode_is_string_compatible(self):
        """Test SyncMode can be used as string."""
        mode = SyncMode.WORKTREE
        # Direct comparison works because SyncMode inherits from str
        assert mode == "worktree"
        # .value gives the underlying string
        assert mode.value == "worktree"

    @pytest.mark.parametrize(
        "value, expected",
        [
            pytest.param("none", False, id="mode-none"),
            pytest.param("worktree", False, id="mode-worktree"),
            pytest.param("staged", False, id="mode-staged"),
            pytest.param(
                "abc123def456789012345678901234567890abcd", True, id="full-sha"
            ),
            pytest.param("a" * 40, True, id="40-char-sha"),
            pytest.param("abc1234", True, id="short-sha-7"),
            pytest.param("abc", False, id="too-short"),
            pytest.param("xyz123!", False, id="invalid-chars"),
        ],
    )
    def test_sync_mode_is_commit_sha(self, value, expected):
        """Test is_commit_sha correctly identifies commit SHAs vs mode strings."""
        assert SyncMode.is_commit_sha(value) == expected


# =============================================================================
# SearchExplanation tests (#301)
# =============================================================================


class TestSearchExplanation:
    """Tests for SearchExplanation dataclass."""

    def test_search_explanation_creation(self):
        """Test creating SearchExplanation with all scores."""
        explanation = SearchExplanation(
            fused_score=0.95,
            bm25_score=0.8,
            vector_score=0.7,
        )
        assert explanation.fused_score == 0.95
        assert explanation.bm25_score == 0.8
        assert explanation.vector_score == 0.7

    def test_search_explanation_default_scores(self):
        """Test that bm25_score and vector_score default to 0.0."""
        explanation = SearchExplanation(fused_score=0.5)
        assert explanation.fused_score == 0.5
        assert explanation.bm25_score == 0.0
        assert explanation.vector_score == 0.0

    def test_search_explanation_is_frozen(self):
        """Test that SearchExplanation is immutable (frozen)."""
        explanation = SearchExplanation(fused_score=0.5)
        with pytest.raises(AttributeError):
            explanation.fused_score = 0.9

    def test_search_explanation_to_dict(self):
        """Test to_dict returns all scores."""
        explanation = SearchExplanation(
            fused_score=0.95,
            bm25_score=0.8,
            vector_score=0.7,
        )
        d = explanation.to_dict()
        assert d == {
            "fused_score": 0.95,
            "bm25_score": 0.8,
            "vector_score": 0.7,
        }

    def test_search_explanation_to_dict_with_defaults(self):
        """Test to_dict includes default scores."""
        explanation = SearchExplanation(fused_score=0.5)
        d = explanation.to_dict()
        assert d == {
            "fused_score": 0.5,
            "bm25_score": 0.0,
            "vector_score": 0.0,
        }

    def test_search_explanation_equality(self):
        """Test equality between SearchExplanation instances."""
        exp1 = SearchExplanation(fused_score=0.5, bm25_score=0.3, vector_score=0.2)
        exp2 = SearchExplanation(fused_score=0.5, bm25_score=0.3, vector_score=0.2)
        assert exp1 == exp2

    def test_search_explanation_inequality(self):
        """Test inequality between different SearchExplanation instances."""
        exp1 = SearchExplanation(fused_score=0.5)
        exp2 = SearchExplanation(fused_score=0.6)
        assert exp1 != exp2


class TestSearchResultWithExplanation:
    """Tests for SearchResult with typed SearchExplanation."""

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
            content_hash="a" * 64,
            file_hash="b" * 64,
            tree_sha="c" * 40,
            rev="HEAD",
        )

    def test_search_result_with_explanation(self, sample_chunk: Chunk):
        """Test creating SearchResult with typed explanation."""
        explanation = SearchExplanation(
            fused_score=0.95,
            bm25_score=0.8,
            vector_score=0.7,
        )
        result = SearchResult(
            chunk=sample_chunk,
            score=0.95,
            rank=1,
            explanation=explanation,
        )
        assert result.explanation.fused_score == 0.95
        assert result.explanation.bm25_score == 0.8
        assert result.explanation.vector_score == 0.7

    def test_search_result_default_explanation(self, sample_chunk: Chunk):
        """Test SearchResult has default explanation."""
        result = SearchResult(
            chunk=sample_chunk,
            score=0.5,
            rank=1,
        )
        assert result.explanation.fused_score == 0.0
        assert result.explanation.bm25_score == 0.0
        assert result.explanation.vector_score == 0.0

    def test_search_result_explanation_provides_typed_access(self, sample_chunk: Chunk):
        """Test that explanation provides IDE-friendly typed access."""
        explanation = SearchExplanation(
            fused_score=0.9,
            bm25_score=0.7,
            vector_score=0.6,
        )
        result = SearchResult(
            chunk=sample_chunk,
            score=0.9,
            rank=1,
            explanation=explanation,
        )
        # Type-safe attribute access (IDE autocomplete works)
        fused = result.explanation.fused_score
        bm25 = result.explanation.bm25_score
        vector = result.explanation.vector_score
        assert fused == 0.9
        assert bm25 == 0.7
        assert vector == 0.6


# =============================================================================
# Chunk hash validation tests (#322)
# =============================================================================


class TestChunkHashValidation:
    """Tests for Chunk entity hash field validation."""

    def _make_chunk(self, **kwargs) -> Chunk:
        """Helper to create a chunk with defaults."""
        defaults = {
            "id": "test_id",
            "project_id": "proj",
            "path": Path("file.py"),
            "lang": "py",
            "symbol": "func",
            "start_line": 1,
            "end_line": 10,
            "content": "def foo(): pass",
            "content_hash": "a" * 64,  # Valid blake3 hash
            "file_hash": "b" * 64,  # Valid blake3 hash
            "tree_sha": "c" * 40,  # Valid git SHA
            "rev": "HEAD",
        }
        defaults.update(kwargs)
        return Chunk(**defaults)

    @pytest.mark.parametrize(
        "field, value",
        [
            pytest.param("content_hash", "a" * 64, id="valid-content-hash"),
            pytest.param("file_hash", "b" * 64, id="valid-file-hash"),
        ],
    )
    def test_chunk_valid_blake3_hash(self, field, value):
        """Test that valid blake3 hashes are accepted."""
        chunk = self._make_chunk(**{field: value})
        assert getattr(chunk, field) == value

    @pytest.mark.parametrize(
        "field, value, error_match",
        [
            pytest.param(
                "content_hash",
                "not-a-valid-hash",
                "Invalid blake3 hash.*content_hash",
                id="content-bad-format",
            ),
            pytest.param(
                "content_hash",
                "abc123",
                "Invalid blake3 hash.*content_hash",
                id="content-too-short",
            ),
            pytest.param(
                "content_hash",
                "",
                "Invalid blake3 hash.*content_hash",
                id="content-empty",
            ),
            pytest.param(
                "content_hash",
                "A" * 64,
                "Invalid blake3 hash.*content_hash",
                id="content-uppercase",
            ),
            pytest.param(
                "file_hash",
                "xyz-invalid-hash",
                "Invalid blake3 hash.*file_hash",
                id="file-bad-format",
            ),
            pytest.param(
                "file_hash",
                "a" * 63,
                "Invalid blake3 hash.*file_hash",
                id="file-too-short",
            ),
            pytest.param(
                "file_hash",
                "",
                "Invalid blake3 hash.*file_hash",
                id="file-empty",
            ),
        ],
    )
    def test_chunk_invalid_blake3_hash(self, field, value, error_match):
        """Test that invalid blake3 hashes raise ValueError."""
        with pytest.raises(ValueError, match=error_match):
            self._make_chunk(**{field: value})

    @pytest.mark.parametrize(
        "tree_sha",
        [
            pytest.param("a" * 40, id="valid-40-char"),
            pytest.param("", id="empty-worktree-mode"),
        ],
    )
    def test_chunk_valid_tree_sha(self, tree_sha):
        """Test that valid git tree SHA values are accepted."""
        chunk = self._make_chunk(tree_sha=tree_sha)
        assert chunk.tree_sha == tree_sha

    @pytest.mark.parametrize(
        "tree_sha",
        [
            pytest.param("not-valid-sha", id="bad-format"),
            pytest.param("a" * 39, id="wrong-length"),
        ],
    )
    def test_chunk_invalid_tree_sha(self, tree_sha):
        """Test that invalid tree_sha format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid git SHA.*tree_sha"):
            self._make_chunk(tree_sha=tree_sha)


# =============================================================================
# Chunk language validation tests (#322)
# =============================================================================


class TestChunkLanguageValidation:
    """Tests for Chunk entity language code validation."""

    def _make_chunk(self, **kwargs) -> Chunk:
        """Helper to create a chunk with defaults."""
        defaults = {
            "id": "test_id",
            "project_id": "proj",
            "path": Path("file.py"),
            "lang": "py",
            "symbol": "func",
            "start_line": 1,
            "end_line": 10,
            "content": "def foo(): pass",
            "content_hash": "a" * 64,
            "file_hash": "b" * 64,
            "tree_sha": "c" * 40,
            "rev": "HEAD",
        }
        defaults.update(kwargs)
        return Chunk(**defaults)

    def test_chunk_valid_language_codes(self):
        """Test all supported language codes are accepted."""
        for lang in SUPPORTED_LANGUAGES:
            chunk = self._make_chunk(lang=lang)
            assert chunk.lang == lang

    def test_chunk_invalid_language_code_raises_error(self):
        """Test that invalid language code raises ValueError."""
        with pytest.raises(ValueError, match="Unknown language.*xyz"):
            self._make_chunk(lang="xyz")

    def test_chunk_empty_language_code_raises_error(self):
        """Test that empty language code raises ValueError."""
        with pytest.raises(ValueError, match="Unknown language"):
            self._make_chunk(lang="")


# =============================================================================
# Chunk content validation tests (#322)
# =============================================================================


class TestChunkContentValidation:
    """Tests for Chunk entity content validation."""

    def _make_chunk(self, **kwargs) -> Chunk:
        """Helper to create a chunk with defaults."""
        defaults = {
            "id": "test_id",
            "project_id": "proj",
            "path": Path("file.py"),
            "lang": "py",
            "symbol": "func",
            "start_line": 1,
            "end_line": 10,
            "content": "def foo(): pass",
            "content_hash": "a" * 64,
            "file_hash": "b" * 64,
            "tree_sha": "c" * 40,
            "rev": "HEAD",
        }
        defaults.update(kwargs)
        return Chunk(**defaults)

    def test_chunk_empty_content_raises_error(self):
        """Test that empty content raises ValueError."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            self._make_chunk(content="")

    def test_chunk_whitespace_only_content_raises_error(self):
        """Test that whitespace-only content raises ValueError."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            self._make_chunk(content="   \n\t  ")

    def test_chunk_valid_content_accepted(self):
        """Test that valid content is accepted."""
        chunk = self._make_chunk(content="x")
        assert chunk.content == "x"


# =============================================================================
# SearchExplanation score validation tests (#322)
# =============================================================================


class TestSearchExplanationScoreValidation:
    """Tests for SearchExplanation score validation."""

    def test_valid_scores_in_range(self):
        """Test that valid scores in 0.0-1.0 range are accepted."""
        explanation = SearchExplanation(
            fused_score=0.95,
            bm25_score=0.8,
            vector_score=0.7,
        )
        assert explanation.fused_score == 0.95
        assert explanation.bm25_score == 0.8
        assert explanation.vector_score == 0.7

    def test_scores_at_boundaries(self):
        """Test that scores at 0.0 and 1.0 boundaries are valid."""
        explanation = SearchExplanation(
            fused_score=1.0,
            bm25_score=0.0,
            vector_score=1.0,
        )
        assert explanation.fused_score == 1.0
        assert explanation.bm25_score == 0.0
        assert explanation.vector_score == 1.0

    @pytest.mark.parametrize(
        "kwargs, error_match",
        [
            pytest.param(
                {"fused_score": -0.1},
                "fused_score must be between",
                id="fused-negative",
            ),
            pytest.param(
                {"fused_score": 1.5},
                "fused_score must be between",
                id="fused-above-one",
            ),
            pytest.param(
                {"fused_score": 0.5, "bm25_score": -0.1},
                "bm25_score must be non-negative",
                id="bm25-negative",
            ),
            pytest.param(
                {"fused_score": 0.5, "vector_score": -0.5},
                "vector_score must be between",
                id="vector-negative",
            ),
            pytest.param(
                {"fused_score": 0.5, "vector_score": 2.0},
                "vector_score must be between",
                id="vector-above-one",
            ),
        ],
    )
    def test_invalid_scores_raise_error(self, kwargs, error_match):
        """Test that out-of-range scores raise ValueError."""
        with pytest.raises(ValueError, match=error_match):
            SearchExplanation(**kwargs)

    def test_bm25_score_above_one_valid(self):
        """Test that bm25_score > 1.0 is valid (raw FTS5 scores are unbounded)."""
        explanation = SearchExplanation(fused_score=0.5, bm25_score=10.378)
        assert explanation.bm25_score == 10.378


# =============================================================================
# Chunk.generate_preview tests (#331)
# =============================================================================


class TestChunkGeneratePreview:
    """Tests for Chunk.generate_preview() method."""

    def _make_chunk(self, content: str) -> Chunk:
        """Helper to create a chunk with specific content."""
        return Chunk(
            id="test_id",
            project_id="proj",
            path=Path("file.py"),
            lang="py",
            symbol="func",
            start_line=1,
            end_line=10,
            content=content,
            content_hash="a" * 64,
            file_hash="b" * 64,
            tree_sha="c" * 40,
            rev="HEAD",
        )

    def test_generate_preview_single_line(self):
        """Test preview of single-line content."""
        chunk = self._make_chunk("def foo(): pass")
        preview = chunk.generate_preview()
        assert preview == "def foo(): pass"

    def test_generate_preview_exact_max_lines(self):
        """Test preview when content has exactly max_lines."""
        content = "line 1\nline 2\nline 3"
        chunk = self._make_chunk(content)
        preview = chunk.generate_preview(max_lines=3)
        assert preview == content  # No ellipsis

    def test_generate_preview_exceeds_max_lines(self):
        """Test preview truncates and adds ellipsis."""
        content = "line 1\nline 2\nline 3\nline 4\nline 5"
        chunk = self._make_chunk(content)
        preview = chunk.generate_preview(max_lines=3)
        assert preview == "line 1\nline 2\nline 3\n..."

    def test_generate_preview_default_max_lines(self):
        """Test default max_lines is 3."""
        content = "a\nb\nc\nd\ne"
        chunk = self._make_chunk(content)
        preview = chunk.generate_preview()
        assert preview == "a\nb\nc\n..."

    def test_generate_preview_custom_max_lines(self):
        """Test custom max_lines parameter."""
        content = "a\nb\nc\nd\ne"
        chunk = self._make_chunk(content)
        preview = chunk.generate_preview(max_lines=5)
        assert preview == content  # All 5 lines fit

    def test_generate_preview_empty_lines_preserved(self):
        """Test that empty lines in content are preserved."""
        content = "line 1\n\nline 3"
        chunk = self._make_chunk(content)
        preview = chunk.generate_preview()
        assert preview == content


# =============================================================================
# Chunk.matches_language tests (#331)
# =============================================================================


class TestChunkMatchesLanguage:
    """Tests for Chunk.matches_language() method."""

    def _make_chunk(self, lang: str) -> Chunk:
        """Helper to create a chunk with specific language."""
        return Chunk(
            id="test_id",
            project_id="proj",
            path=Path("file.py"),
            lang=lang,
            symbol="func",
            start_line=1,
            end_line=10,
            content="code",
            content_hash="a" * 64,
            file_hash="b" * 64,
            tree_sha="c" * 40,
            rev="HEAD",
        )

    def test_matches_language_none_filter(self):
        """Test that None filter matches any language."""
        chunk = self._make_chunk("py")
        assert chunk.matches_language(None) is True

    def test_matches_language_exact_match(self):
        """Test that matching language returns True."""
        chunk = self._make_chunk("py")
        assert chunk.matches_language("py") is True

    def test_matches_language_no_match(self):
        """Test that non-matching language returns False."""
        chunk = self._make_chunk("py")
        assert chunk.matches_language("ts") is False

    def test_matches_language_various_languages(self):
        """Test language matching with various languages."""
        for lang in ["py", "ts", "go", "rs", "java"]:
            chunk = self._make_chunk(lang)
            assert chunk.matches_language(lang) is True
            assert chunk.matches_language("other") is False


# =============================================================================
# SearchExplanation.effective_score tests (#331)
# =============================================================================


class TestSearchExplanationEffectiveScore:
    """Tests for SearchExplanation.effective_score property."""

    def test_effective_score_returns_fused_score(self):
        """Test that effective_score returns fused_score."""
        explanation = SearchExplanation(
            fused_score=0.85,
            bm25_score=0.7,
            vector_score=0.6,
        )
        assert explanation.effective_score == 0.85

    def test_effective_score_with_zero_fused(self):
        """Test effective_score when fused_score is zero."""
        explanation = SearchExplanation(fused_score=0.0)
        assert explanation.effective_score == 0.0

    def test_effective_score_with_max_fused(self):
        """Test effective_score when fused_score is 1.0."""
        explanation = SearchExplanation(fused_score=1.0)
        assert explanation.effective_score == 1.0


# =============================================================================
# Isolated validator tests (#352)
# =============================================================================


class TestChunkValidatorsInIsolation:
    """Tests for Chunk validators called independently of __post_init__.

    These tests verify that validation logic is testable in isolation,
    one of the success criteria for #352.
    """

    @pytest.mark.parametrize(
        "start, end",
        [pytest.param(1, 10, id="normal"), pytest.param(5, 5, id="single-line")],
    )
    def test_validate_line_numbers_valid(self, start, end):
        """Test _validate_line_numbers accepts valid values."""
        Chunk._validate_line_numbers(start, end)  # Should not raise

    @pytest.mark.parametrize(
        "start, end, error_match",
        [
            pytest.param(0, 10, "Line numbers must be >= 1", id="zero-start"),
            pytest.param(1, 0, "Line numbers must be >= 1", id="zero-end"),
            pytest.param(20, 10, "start_line.*>.*end_line", id="start-gt-end"),
        ],
    )
    def test_validate_line_numbers_invalid(self, start, end, error_match):
        """Test _validate_line_numbers rejects invalid values."""
        with pytest.raises(ValueError, match=error_match):
            Chunk._validate_line_numbers(start, end)

    @pytest.mark.parametrize(
        "content",
        [pytest.param("code", id="simple"), pytest.param("  code  ", id="padded")],
    )
    def test_validate_content_valid(self, content):
        """Test _validate_content accepts non-empty content."""
        Chunk._validate_content(content)  # Should not raise

    @pytest.mark.parametrize(
        "content",
        [pytest.param("", id="empty"), pytest.param("   \n\t  ", id="whitespace-only")],
    )
    def test_validate_content_invalid(self, content):
        """Test _validate_content rejects empty/whitespace content."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            Chunk._validate_content(content)

    def test_validate_blake3_hash_valid(self):
        """Test _validate_blake3_hash accepts valid hash."""
        # Should not raise
        Chunk._validate_blake3_hash("a" * 64, "content_hash")

    def test_validate_blake3_hash_invalid(self):
        """Test _validate_blake3_hash rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid blake3 hash"):
            Chunk._validate_blake3_hash("invalid", "content_hash")

    def test_validate_tree_sha_valid(self):
        """Test _validate_tree_sha accepts valid SHA."""
        # Should not raise
        Chunk._validate_tree_sha("a" * 40)
        Chunk._validate_tree_sha("")  # Empty is valid

    def test_validate_tree_sha_invalid(self):
        """Test _validate_tree_sha rejects invalid SHA."""
        with pytest.raises(ValueError, match="Invalid git SHA"):
            Chunk._validate_tree_sha("invalid")

    def test_validate_language_valid(self):
        """Test _validate_language accepts supported languages."""
        # Should not raise
        Chunk._validate_language("py")
        Chunk._validate_language("ts")

    def test_validate_language_invalid(self):
        """Test _validate_language rejects unsupported languages."""
        with pytest.raises(ValueError, match="Unknown language"):
            Chunk._validate_language("unknown")


class TestQueryValidatorsInIsolation:
    """Tests for Query validators called independently of __post_init__.

    These tests verify that validation logic is testable in isolation.
    """

    @pytest.mark.parametrize(
        "text",
        [pytest.param("search term", id="normal"), pytest.param("  search  ", id="padded")],
    )
    def test_validate_text_valid(self, text):
        """Test _validate_text accepts non-empty text."""
        Query._validate_text(text)  # Should not raise

    @pytest.mark.parametrize(
        "text",
        [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")],
    )
    def test_validate_text_invalid(self, text):
        """Test _validate_text rejects empty/whitespace text."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query._validate_text(text)

    @pytest.mark.parametrize("topk", [1, 100])
    def test_validate_topk_valid(self, topk):
        """Test _validate_topk accepts positive values."""
        Query._validate_topk(topk)  # Should not raise

    @pytest.mark.parametrize(
        "topk",
        [pytest.param(0, id="zero"), pytest.param(-5, id="negative")],
    )
    def test_validate_topk_invalid(self, topk):
        """Test _validate_topk rejects non-positive values."""
        with pytest.raises(ValueError, match="topk must be positive"):
            Query._validate_topk(topk)

    # Note: _normalize_path_filter and _normalize_lang_filter methods were removed
    # in favor of the from_strings() factory method. See TestQueryFromStrings.


# =============================================================================
# SearchResult validation tests (#399)
# =============================================================================


class TestSearchResultValidation:
    """Tests for SearchResult entity validation."""

    # Valid hash constants for tests
    VALID_CONTENT_HASH = "a" * 64
    VALID_FILE_HASH = "b" * 64
    VALID_TREE_SHA = "c" * 40

    def _make_chunk(self) -> Chunk:
        """Helper to create a valid chunk for testing."""
        return Chunk(
            id="test_id",
            project_id="proj",
            path=Path("file.py"),
            lang="py",
            symbol="func",
            start_line=1,
            end_line=10,
            content="def foo(): pass",
            content_hash=self.VALID_CONTENT_HASH,
            file_hash=self.VALID_FILE_HASH,
            tree_sha=self.VALID_TREE_SHA,
            rev="HEAD",
        )

    def test_valid_search_result(self):
        """Test creating a valid SearchResult."""
        chunk = self._make_chunk()
        result = SearchResult(
            chunk=chunk,
            score=0.95,
            rank=1,
        )
        assert result.score == 0.95
        assert result.rank == 1

    def test_score_at_boundaries(self):
        """Test that scores at 0.0 and 1.0 boundaries are valid."""
        chunk = self._make_chunk()

        result_zero = SearchResult(chunk=chunk, score=0.0, rank=1)
        assert result_zero.score == 0.0

        result_one = SearchResult(chunk=chunk, score=1.0, rank=1)
        assert result_one.score == 1.0

    @pytest.mark.parametrize(
        "score, rank, error_match",
        [
            pytest.param(-0.1, 1, "score must be 0.0-1.0", id="score-negative"),
            pytest.param(1.5, 1, "score must be 0.0-1.0", id="score-above-one"),
            pytest.param(0.5, 0, "rank must be positive", id="rank-zero"),
            pytest.param(0.5, -1, "rank must be positive", id="rank-negative"),
        ],
    )
    def test_invalid_score_or_rank(self, score, rank, error_match):
        """Test that invalid score/rank values raise ValueError."""
        chunk = self._make_chunk()
        with pytest.raises(ValueError, match=error_match):
            SearchResult(chunk=chunk, score=score, rank=rank)

    @pytest.mark.parametrize("rank", [1, 100])
    def test_rank_positive_valid(self, rank):
        """Test that positive rank values are valid."""
        chunk = self._make_chunk()
        result = SearchResult(chunk=chunk, score=0.5, rank=rank)
        assert result.rank == rank

    def test_multiple_invalid_values(self):
        """Test error with both invalid score and rank."""
        chunk = self._make_chunk()
        # Score is validated first, so we get score error
        with pytest.raises(ValueError, match="score must be 0.0-1.0"):
            SearchResult(chunk=chunk, score=-5.0, rank=-1)


class TestSearchResultImmutability:
    """Tests for SearchResult immutability (frozen dataclass)."""

    VALID_CONTENT_HASH = "a" * 64
    VALID_FILE_HASH = "b" * 64
    VALID_TREE_SHA = "c" * 40

    def _make_chunk(self) -> Chunk:
        """Helper to create a valid chunk for testing."""
        return Chunk(
            id="test_id",
            project_id="proj",
            path=Path("file.py"),
            lang="py",
            symbol="func",
            start_line=1,
            end_line=10,
            content="def foo(): pass",
            content_hash=self.VALID_CONTENT_HASH,
            file_hash=self.VALID_FILE_HASH,
            tree_sha=self.VALID_TREE_SHA,
            rev="HEAD",
        )

    @pytest.mark.parametrize(
        "attr, value",
        [
            pytest.param("score", 0.9, id="score"),
            pytest.param("rank", 2, id="rank"),
            pytest.param("preview", "new preview", id="preview"),
        ],
    )
    def test_search_result_is_frozen(self, attr, value):
        """Test that SearchResult instances cannot be modified after creation."""
        chunk = self._make_chunk()
        result = SearchResult(chunk=chunk, score=0.5, rank=1)
        with pytest.raises(AttributeError):
            setattr(result, attr, value)

    def test_search_result_hashable(self):
        """Test that frozen SearchResult is hashable."""
        chunk = self._make_chunk()
        result1 = SearchResult(chunk=chunk, score=0.5, rank=1)
        result2 = SearchResult(chunk=chunk, score=0.5, rank=1)
        # Frozen dataclasses are hashable
        assert hash(result1) == hash(result2)
        # Can be used in sets
        result_set = {result1, result2}
        assert len(result_set) == 1


class TestSearchResultValidatorsInIsolation:
    """Tests for SearchResult validators called independently of __post_init__.

    These tests verify that validation logic is testable in isolation.
    """

    @pytest.mark.parametrize("score", [0.0, 0.5, 1.0])
    def test_validate_score_valid(self, score):
        """Test _validate_score accepts valid values."""
        SearchResult._validate_score(score)  # Should not raise

    @pytest.mark.parametrize(
        "score",
        [pytest.param(-0.1, id="negative"), pytest.param(1.01, id="above-one")],
    )
    def test_validate_score_invalid(self, score):
        """Test _validate_score rejects out-of-range values."""
        with pytest.raises(ValueError, match="score must be 0.0-1.0"):
            SearchResult._validate_score(score)

    @pytest.mark.parametrize("rank", [1, 100])
    def test_validate_rank_valid(self, rank):
        """Test _validate_rank accepts positive values."""
        SearchResult._validate_rank(rank)  # Should not raise

    @pytest.mark.parametrize(
        "rank",
        [pytest.param(0, id="zero"), pytest.param(-5, id="negative")],
    )
    def test_validate_rank_invalid(self, rank):
        """Test _validate_rank rejects non-positive values."""
        with pytest.raises(ValueError, match="rank must be positive"):
            SearchResult._validate_rank(rank)
