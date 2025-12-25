"""Tests for domain entities."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ember.domain.entities import (
    Chunk,
    Query,
    RepoState,
    SearchExplanation,
    SearchResult,
    SearchResultSet,
    SyncMode,
)
from ember.domain.value_objects import SUPPORTED_LANGUAGES


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
                content_hash=self.VALID_CONTENT_HASH,
                file_hash=self.VALID_FILE_HASH,
                tree_sha=self.VALID_TREE_SHA,
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
                content_hash=self.VALID_CONTENT_HASH,
                file_hash=self.VALID_FILE_HASH,
                tree_sha=self.VALID_TREE_SHA,
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
                content_hash=self.VALID_CONTENT_HASH,
                file_hash=self.VALID_FILE_HASH,
                tree_sha=self.VALID_TREE_SHA,
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

    def test_sync_mode_values(self):
        """Test SyncMode enum has expected values."""
        assert SyncMode.NONE == "none"
        assert SyncMode.WORKTREE == "worktree"
        assert SyncMode.STAGED == "staged"

    def test_sync_mode_from_string(self):
        """Test creating SyncMode from string value."""
        assert SyncMode("none") == SyncMode.NONE
        assert SyncMode("worktree") == SyncMode.WORKTREE
        assert SyncMode("staged") == SyncMode.STAGED

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

    def test_sync_mode_is_commit_sha(self):
        """Test is_commit_sha method for known modes."""
        assert not SyncMode.is_commit_sha("none")
        assert not SyncMode.is_commit_sha("worktree")
        assert not SyncMode.is_commit_sha("staged")
        # Valid commit SHAs
        assert SyncMode.is_commit_sha("abc123def456789012345678901234567890abcd")
        assert SyncMode.is_commit_sha("a" * 40)
        # Short SHAs (7-39 chars) are also valid
        assert SyncMode.is_commit_sha("abc1234")
        # Invalid SHAs
        assert not SyncMode.is_commit_sha("abc")  # Too short
        assert not SyncMode.is_commit_sha("xyz123!")  # Invalid chars


# =============================================================================
# RepoState validation tests (#271)
# =============================================================================


class TestRepoStateValidation:
    """Tests for RepoState entity validation."""

    def test_repo_state_valid_creation_with_sync_mode_enum(self):
        """Test creating a valid RepoState with SyncMode enum."""
        now = datetime.now(UTC).isoformat()
        state = RepoState(
            last_tree_sha="a" * 40,
            last_sync_mode=SyncMode.WORKTREE,
            model_fingerprint="jina-v2-code",
            version="1.0.0",
            indexed_at=now,
        )
        assert state.last_sync_mode == SyncMode.WORKTREE
        assert state.last_tree_sha == "a" * 40

    def test_repo_state_valid_creation_with_string_sync_mode(self):
        """Test creating RepoState with string sync mode (backward compat)."""
        now = datetime.now(UTC).isoformat()
        state = RepoState(
            last_tree_sha="a" * 40,
            last_sync_mode="worktree",
            model_fingerprint="jina-v2-code",
            version="1.0.0",
            indexed_at=now,
        )
        # Should auto-convert to SyncMode enum
        assert state.last_sync_mode == SyncMode.WORKTREE

    def test_repo_state_accepts_commit_sha_as_sync_mode(self):
        """Test that commit SHA is accepted as sync mode."""
        now = datetime.now(UTC).isoformat()
        commit_sha = "abc123def456789012345678901234567890abcd"
        state = RepoState(
            last_tree_sha="b" * 40,
            last_sync_mode=commit_sha,
            model_fingerprint="jina-v2-code",
            version="1.0.0",
            indexed_at=now,
        )
        assert state.last_sync_mode == commit_sha

    def test_repo_state_empty_tree_sha_valid_for_uninitialized(self):
        """Test that empty tree_sha is valid (uninitialized state)."""
        now = datetime.now(UTC).isoformat()
        state = RepoState(
            last_tree_sha="",
            last_sync_mode=SyncMode.NONE,
            model_fingerprint="",
            version="1.0.0",
            indexed_at=now,
        )
        assert state.last_tree_sha == ""
        assert state.is_uninitialized

    def test_repo_state_invalid_tree_sha_format_raises_error(self):
        """Test that malformed tree_sha raises ValueError."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="tree_sha must be empty or a valid"):
            RepoState(
                last_tree_sha="not-a-valid-sha",
                last_sync_mode=SyncMode.WORKTREE,
                model_fingerprint="jina-v2-code",
                version="1.0.0",
                indexed_at=now,
            )

    def test_repo_state_tree_sha_wrong_length_raises_error(self):
        """Test that tree_sha with wrong length raises ValueError."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="tree_sha must be empty or a valid"):
            RepoState(
                last_tree_sha="abc123",  # Too short (not 40 chars)
                last_sync_mode=SyncMode.WORKTREE,
                model_fingerprint="jina-v2-code",
                version="1.0.0",
                indexed_at=now,
            )

    def test_repo_state_invalid_sync_mode_raises_error(self):
        """Test that invalid sync mode raises ValueError."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="sync_mode must be"):
            RepoState(
                last_tree_sha="a" * 40,
                last_sync_mode="invalid_mode",
                model_fingerprint="jina-v2-code",
                version="1.0.0",
                indexed_at=now,
            )

    def test_repo_state_empty_version_raises_error(self):
        """Test that empty version raises ValueError."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="version cannot be empty"):
            RepoState(
                last_tree_sha="a" * 40,
                last_sync_mode=SyncMode.WORKTREE,
                model_fingerprint="jina-v2-code",
                version="",
                indexed_at=now,
            )

    def test_repo_state_invalid_timestamp_raises_error(self):
        """Test that invalid ISO-8601 timestamp raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ISO-8601 timestamp"):
            RepoState(
                last_tree_sha="a" * 40,
                last_sync_mode=SyncMode.WORKTREE,
                model_fingerprint="jina-v2-code",
                version="1.0.0",
                indexed_at="not-a-timestamp",
            )

    def test_repo_state_valid_timestamps(self):
        """Test various valid ISO-8601 timestamp formats."""
        tree_sha = "a" * 40
        # With timezone
        state = RepoState(
            last_tree_sha=tree_sha,
            last_sync_mode=SyncMode.WORKTREE,
            model_fingerprint="model",
            version="1.0.0",
            indexed_at="2025-01-15T10:30:00+00:00",
        )
        # indexed_at is now ISO8601Timestamp, use indexed_at_str for raw string
        assert state.indexed_at_str == "2025-01-15T10:30:00+00:00"

        # With Z suffix
        state = RepoState(
            last_tree_sha=tree_sha,
            last_sync_mode=SyncMode.WORKTREE,
            model_fingerprint="model",
            version="1.0.0",
            indexed_at="2025-01-15T10:30:00Z",
        )
        assert state.indexed_at_str == "2025-01-15T10:30:00Z"


# =============================================================================
# RepoState helper method tests (#271)
# =============================================================================


class TestRepoStateHelperMethods:
    """Tests for RepoState helper methods."""

    @pytest.fixture
    def initialized_state(self) -> RepoState:
        """Create an initialized RepoState for testing."""
        return RepoState.from_sync(
            tree_sha="a" * 40,
            sync_mode=SyncMode.WORKTREE,
            model_fingerprint="jina-v2-code",
            version="1.0.0",
        )

    @pytest.fixture
    def uninitialized_state(self) -> RepoState:
        """Create an uninitialized RepoState for testing."""
        return RepoState.uninitialized(version="1.0.0")

    def test_is_uninitialized_true_when_no_tree_sha(self, uninitialized_state):
        """Test is_uninitialized returns True when tree_sha is empty."""
        assert uninitialized_state.is_uninitialized

    def test_is_uninitialized_false_when_has_tree_sha(self, initialized_state):
        """Test is_uninitialized returns False when tree_sha is set."""
        assert not initialized_state.is_uninitialized

    def test_is_stale_returns_true_when_old(self):
        """Test is_stale returns True when index is older than threshold."""
        old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        state = RepoState(
            last_tree_sha="a" * 40,
            last_sync_mode=SyncMode.WORKTREE,
            model_fingerprint="jina-v2-code",
            version="1.0.0",
            indexed_at=old_time,
        )
        # 1 hour threshold = 3600 seconds
        assert state.is_stale(threshold_seconds=3600)

    def test_is_stale_returns_false_when_fresh(self, initialized_state):
        """Test is_stale returns False when index is newer than threshold."""
        # Default fixture uses current time, should not be stale
        assert not initialized_state.is_stale(threshold_seconds=3600)

    def test_is_stale_with_zero_threshold(self, initialized_state):
        """Test is_stale with zero threshold (any age is stale)."""
        # Even very recent state should be considered stale with 0 threshold
        # after any time passes
        import time

        time.sleep(0.01)  # Ensure some time passes
        assert initialized_state.is_stale(threshold_seconds=0)

    def test_needs_model_update_true_when_different(self, initialized_state):
        """Test needs_model_update returns True when fingerprints differ."""
        assert initialized_state.needs_model_update("different-model")

    def test_needs_model_update_false_when_same(self, initialized_state):
        """Test needs_model_update returns False when fingerprints match."""
        assert not initialized_state.needs_model_update("jina-v2-code")

    def test_needs_model_update_true_when_empty_fingerprint(self, uninitialized_state):
        """Test needs_model_update returns True when current fingerprint is empty."""
        assert uninitialized_state.needs_model_update("any-model")


# =============================================================================
# RepoState factory method tests (#303)
# =============================================================================


class TestRepoStateFactoryMethods:
    """Tests for RepoState factory methods."""

    def test_uninitialized_factory_creates_empty_state(self):
        """Test that uninitialized() creates a state with empty tree_sha."""
        state = RepoState.uninitialized(version="1.2.0")
        assert state.last_tree_sha == ""
        assert state.last_sync_mode == SyncMode.NONE
        assert state.model_fingerprint == ""
        assert state.version == "1.2.0"
        assert state.is_uninitialized

    def test_uninitialized_factory_sets_timestamp(self):
        """Test that uninitialized() sets indexed_at to current time."""
        before = datetime.now(UTC)
        state = RepoState.uninitialized(version="1.2.0")
        after = datetime.now(UTC)

        # indexed_at is ISO8601Timestamp, use .value to get the datetime
        timestamp = state.indexed_at.value
        assert before <= timestamp <= after

    def test_from_sync_factory_creates_initialized_state(self):
        """Test that from_sync() creates a properly initialized state."""
        tree_sha = "a" * 40
        state = RepoState.from_sync(
            tree_sha=tree_sha,
            sync_mode=SyncMode.WORKTREE,
            model_fingerprint="jina-v2-code",
            version="1.2.0",
        )
        assert state.last_tree_sha == tree_sha
        assert state.last_sync_mode == SyncMode.WORKTREE
        assert state.model_fingerprint == "jina-v2-code"
        assert state.version == "1.2.0"
        assert not state.is_uninitialized

    def test_from_sync_factory_accepts_string_sync_mode(self):
        """Test that from_sync() accepts string sync mode."""
        state = RepoState.from_sync(
            tree_sha="b" * 40,
            sync_mode="staged",
            model_fingerprint="model",
            version="1.0.0",
        )
        assert state.last_sync_mode == SyncMode.STAGED

    def test_from_sync_factory_accepts_commit_sha(self):
        """Test that from_sync() accepts commit SHA as sync mode."""
        commit_sha = "abc123def456789012345678901234567890abcd"
        state = RepoState.from_sync(
            tree_sha="c" * 40,
            sync_mode=commit_sha,
            model_fingerprint="model",
            version="1.0.0",
        )
        assert state.last_sync_mode == commit_sha

    def test_from_sync_factory_sets_timestamp(self):
        """Test that from_sync() sets indexed_at to current time."""
        before = datetime.now(UTC)
        state = RepoState.from_sync(
            tree_sha="d" * 40,
            sync_mode=SyncMode.WORKTREE,
            model_fingerprint="model",
            version="1.0.0",
        )
        after = datetime.now(UTC)

        # indexed_at is ISO8601Timestamp, use .value to get the datetime
        timestamp = state.indexed_at.value
        assert before <= timestamp <= after

    def test_from_sync_factory_validates_tree_sha(self):
        """Test that from_sync() validates tree_sha format."""
        with pytest.raises(ValueError, match="tree_sha must be empty or a valid"):
            RepoState.from_sync(
                tree_sha="invalid",
                sync_mode=SyncMode.WORKTREE,
                model_fingerprint="model",
                version="1.0.0",
            )

    def test_from_sync_factory_validates_version(self):
        """Test that from_sync() validates version is not empty."""
        with pytest.raises(ValueError, match="version cannot be empty"):
            RepoState.from_sync(
                tree_sha="e" * 40,
                sync_mode=SyncMode.WORKTREE,
                model_fingerprint="model",
                version="",
            )


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

    def test_chunk_valid_blake3_hash_content(self):
        """Test that valid blake3 content_hash is accepted."""
        chunk = self._make_chunk(content_hash="a" * 64)
        assert chunk.content_hash == "a" * 64

    def test_chunk_valid_blake3_hash_file(self):
        """Test that valid blake3 file_hash is accepted."""
        chunk = self._make_chunk(file_hash="b" * 64)
        assert chunk.file_hash == "b" * 64

    def test_chunk_invalid_content_hash_format_raises_error(self):
        """Test that content_hash with non-hex chars raises ValueError."""
        with pytest.raises(ValueError, match="Invalid blake3 hash.*content_hash"):
            self._make_chunk(content_hash="not-a-valid-hash")

    def test_chunk_invalid_content_hash_length_raises_error(self):
        """Test that content_hash with wrong length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid blake3 hash.*content_hash"):
            self._make_chunk(content_hash="abc123")  # Too short

    def test_chunk_invalid_file_hash_format_raises_error(self):
        """Test that file_hash with non-hex chars raises ValueError."""
        with pytest.raises(ValueError, match="Invalid blake3 hash.*file_hash"):
            self._make_chunk(file_hash="xyz-invalid-hash")

    def test_chunk_invalid_file_hash_length_raises_error(self):
        """Test that file_hash with wrong length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid blake3 hash.*file_hash"):
            self._make_chunk(file_hash="a" * 63)  # One char too short

    def test_chunk_empty_content_hash_raises_error(self):
        """Test that empty content_hash raises ValueError."""
        with pytest.raises(ValueError, match="Invalid blake3 hash.*content_hash"):
            self._make_chunk(content_hash="")

    def test_chunk_empty_file_hash_raises_error(self):
        """Test that empty file_hash raises ValueError."""
        with pytest.raises(ValueError, match="Invalid blake3 hash.*file_hash"):
            self._make_chunk(file_hash="")

    def test_chunk_content_hash_uppercase_rejected(self):
        """Test that uppercase hex in content_hash is rejected."""
        with pytest.raises(ValueError, match="Invalid blake3 hash.*content_hash"):
            self._make_chunk(content_hash="A" * 64)

    def test_chunk_valid_tree_sha_format(self):
        """Test that valid git tree SHA is accepted."""
        chunk = self._make_chunk(tree_sha="a" * 40)
        assert chunk.tree_sha == "a" * 40

    def test_chunk_empty_tree_sha_valid(self):
        """Test that empty tree_sha is valid (worktree mode)."""
        chunk = self._make_chunk(tree_sha="")
        assert chunk.tree_sha == ""

    def test_chunk_invalid_tree_sha_raises_error(self):
        """Test that invalid tree_sha format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid git SHA.*tree_sha"):
            self._make_chunk(tree_sha="not-valid-sha")

    def test_chunk_tree_sha_wrong_length_raises_error(self):
        """Test that tree_sha with wrong length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid git SHA.*tree_sha"):
            self._make_chunk(tree_sha="a" * 39)  # One char too short


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

    def test_negative_fused_score_raises_error(self):
        """Test that negative fused_score raises ValueError."""
        with pytest.raises(ValueError, match="fused_score must be between"):
            SearchExplanation(fused_score=-0.1)

    def test_fused_score_above_one_raises_error(self):
        """Test that fused_score > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="fused_score must be between"):
            SearchExplanation(fused_score=1.5)

    def test_negative_bm25_score_raises_error(self):
        """Test that negative bm25_score raises ValueError."""
        with pytest.raises(ValueError, match="bm25_score must be non-negative"):
            SearchExplanation(fused_score=0.5, bm25_score=-0.1)

    def test_bm25_score_above_one_valid(self):
        """Test that bm25_score > 1.0 is valid (raw FTS5 scores are unbounded)."""
        # BM25 scores from SQLite FTS5 are raw, unbounded positive values
        explanation = SearchExplanation(fused_score=0.5, bm25_score=10.378)
        assert explanation.bm25_score == 10.378

    def test_negative_vector_score_raises_error(self):
        """Test that negative vector_score raises ValueError."""
        with pytest.raises(ValueError, match="vector_score must be between"):
            SearchExplanation(fused_score=0.5, vector_score=-0.5)

    def test_vector_score_above_one_raises_error(self):
        """Test that vector_score > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="vector_score must be between"):
            SearchExplanation(fused_score=0.5, vector_score=2.0)


# =============================================================================
# RepoState invariant validation tests (#322)
# =============================================================================


class TestRepoStateInvariantValidation:
    """Tests for RepoState entity invariant validation."""

    def test_initialized_state_requires_model_fingerprint(self):
        """Test that initialized state (non-empty tree_sha) requires model_fingerprint."""
        now = datetime.now(UTC).isoformat()
        with pytest.raises(ValueError, match="model_fingerprint.*required"):
            RepoState(
                last_tree_sha="a" * 40,  # Initialized (has tree_sha)
                last_sync_mode=SyncMode.WORKTREE,
                model_fingerprint="",  # Empty - should fail
                version="1.0.0",
                indexed_at=now,
            )

    def test_uninitialized_state_allows_empty_model_fingerprint(self):
        """Test that uninitialized state (empty tree_sha) can have empty model_fingerprint."""
        now = datetime.now(UTC).isoformat()
        state = RepoState(
            last_tree_sha="",  # Uninitialized
            last_sync_mode=SyncMode.NONE,
            model_fingerprint="",  # Empty OK for uninitialized
            version="1.0.0",
            indexed_at=now,
        )
        assert state.model_fingerprint == ""

    def test_initialized_state_with_model_fingerprint_valid(self):
        """Test that initialized state with non-empty model_fingerprint is valid."""
        now = datetime.now(UTC).isoformat()
        state = RepoState(
            last_tree_sha="a" * 40,
            last_sync_mode=SyncMode.WORKTREE,
            model_fingerprint="jina-v2-code",
            version="1.0.0",
            indexed_at=now,
        )
        assert state.model_fingerprint == "jina-v2-code"


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

    def test_validate_line_numbers_valid(self):
        """Test _validate_line_numbers accepts valid values."""
        # Should not raise
        Chunk._validate_line_numbers(1, 10)
        Chunk._validate_line_numbers(5, 5)  # Single line

    def test_validate_line_numbers_zero_start(self):
        """Test _validate_line_numbers rejects zero start_line."""
        with pytest.raises(ValueError, match="Line numbers must be >= 1"):
            Chunk._validate_line_numbers(0, 10)

    def test_validate_line_numbers_zero_end(self):
        """Test _validate_line_numbers rejects zero end_line."""
        with pytest.raises(ValueError, match="Line numbers must be >= 1"):
            Chunk._validate_line_numbers(1, 0)

    def test_validate_line_numbers_start_greater_than_end(self):
        """Test _validate_line_numbers rejects start > end."""
        with pytest.raises(ValueError, match="start_line.*>.*end_line"):
            Chunk._validate_line_numbers(20, 10)

    def test_validate_content_valid(self):
        """Test _validate_content accepts non-empty content."""
        # Should not raise
        Chunk._validate_content("code")
        Chunk._validate_content("  code  ")

    def test_validate_content_empty(self):
        """Test _validate_content rejects empty content."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            Chunk._validate_content("")

    def test_validate_content_whitespace_only(self):
        """Test _validate_content rejects whitespace-only content."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            Chunk._validate_content("   \n\t  ")

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


class TestRepoStateValidatorsInIsolation:
    """Tests for RepoState validators called independently of __post_init__.

    These tests verify that validation logic is testable in isolation.
    """

    def test_validate_tree_sha_valid(self):
        """Test _validate_tree_sha accepts valid SHA."""
        # Should not raise
        RepoState._validate_tree_sha("a" * 40)
        RepoState._validate_tree_sha("")  # Empty is valid

    def test_validate_tree_sha_invalid(self):
        """Test _validate_tree_sha rejects invalid SHA."""
        with pytest.raises(ValueError, match="tree_sha must be empty or a valid"):
            RepoState._validate_tree_sha("invalid")

    def test_normalize_sync_mode_enum(self):
        """Test _normalize_sync_mode returns SyncMode enum unchanged."""
        result = RepoState._normalize_sync_mode(SyncMode.WORKTREE)
        assert result == SyncMode.WORKTREE

    def test_normalize_sync_mode_string(self):
        """Test _normalize_sync_mode converts string to SyncMode."""
        result = RepoState._normalize_sync_mode("worktree")
        assert result == SyncMode.WORKTREE

    def test_normalize_sync_mode_commit_sha(self):
        """Test _normalize_sync_mode accepts commit SHA."""
        sha = "abc123def456789012345678901234567890abcd"
        result = RepoState._normalize_sync_mode(sha)
        assert result == sha

    def test_normalize_sync_mode_invalid(self):
        """Test _normalize_sync_mode rejects invalid values."""
        with pytest.raises(ValueError, match="sync_mode must be"):
            RepoState._normalize_sync_mode("invalid_mode")

    def test_validate_version_valid(self):
        """Test _validate_version accepts non-empty version."""
        # Should not raise
        RepoState._validate_version("1.0.0")

    def test_validate_version_empty(self):
        """Test _validate_version rejects empty version."""
        with pytest.raises(ValueError, match="version cannot be empty"):
            RepoState._validate_version("")

    def test_validate_initialized_state_valid(self):
        """Test _validate_initialized_state with valid state."""
        # Should not raise
        RepoState._validate_initialized_state("a" * 40, "model")
        RepoState._validate_initialized_state("", "")  # Uninitialized OK

    def test_validate_initialized_state_missing_fingerprint(self):
        """Test _validate_initialized_state requires fingerprint when initialized."""
        with pytest.raises(ValueError, match="model_fingerprint.*required"):
            RepoState._validate_initialized_state("a" * 40, "")


class TestQueryValidatorsInIsolation:
    """Tests for Query validators called independently of __post_init__.

    These tests verify that validation logic is testable in isolation.
    """

    def test_validate_text_valid(self):
        """Test _validate_text accepts non-empty text."""
        # Should not raise
        Query._validate_text("search term")
        Query._validate_text("  search  ")

    def test_validate_text_empty(self):
        """Test _validate_text rejects empty text."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query._validate_text("")

    def test_validate_text_whitespace_only(self):
        """Test _validate_text rejects whitespace-only text."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            Query._validate_text("   ")

    def test_validate_topk_valid(self):
        """Test _validate_topk accepts positive values."""
        # Should not raise
        Query._validate_topk(1)
        Query._validate_topk(100)

    def test_validate_topk_zero(self):
        """Test _validate_topk rejects zero."""
        with pytest.raises(ValueError, match="topk must be positive"):
            Query._validate_topk(0)

    def test_validate_topk_negative(self):
        """Test _validate_topk rejects negative values."""
        with pytest.raises(ValueError, match="topk must be positive"):
            Query._validate_topk(-5)

    def test_normalize_path_filter_none(self):
        """Test _normalize_path_filter returns None for None input."""
        result = Query._normalize_path_filter(None)
        assert result is None

    def test_normalize_path_filter_string(self):
        """Test _normalize_path_filter converts string to PathFilter."""
        from ember.domain.value_objects import PathFilter

        result = Query._normalize_path_filter("*.py")
        assert isinstance(result, PathFilter)

    def test_normalize_lang_filter_none(self):
        """Test _normalize_lang_filter returns None for None input."""
        result = Query._normalize_lang_filter(None)
        assert result is None

    def test_normalize_lang_filter_string(self):
        """Test _normalize_lang_filter converts string to LanguageFilter."""
        from ember.domain.value_objects import LanguageFilter

        result = Query._normalize_lang_filter("py")
        assert isinstance(result, LanguageFilter)
