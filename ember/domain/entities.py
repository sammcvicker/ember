"""Domain entities and value objects.

Core domain models representing the business concepts of Ember.
These are pure Python dataclasses with no dependencies on infrastructure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import blake3

from ember.domain.value_objects import (
    SUPPORTED_LANGUAGES,
    ISO8601Timestamp,
    LanguageFilter,
    PathFilter,
)


class SyncMode(str, Enum):
    """Sync mode for repository indexing.

    Defines how the repository should be indexed:
    - NONE: Initial state, no sync performed yet
    - WORKTREE: Index working directory (including unstaged changes)
    - STAGED: Index only staged changes

    Note: Commit SHAs can also be used as sync_mode values but are not
    enumerated since they are dynamic. Use is_commit_sha() to check.
    """

    NONE = "none"
    WORKTREE = "worktree"
    STAGED = "staged"

    @staticmethod
    def is_commit_sha(value: str) -> bool:
        """Check if a string is a valid git commit SHA.

        Args:
            value: String to check.

        Returns:
            True if value looks like a valid commit SHA (7-40 hex chars).
        """
        if value in (SyncMode.NONE.value, SyncMode.WORKTREE.value, SyncMode.STAGED.value):
            return False
        # Git SHAs are 40 hex chars, but short SHAs (7+) are also valid
        return bool(re.match(r"^[a-f0-9]{7,40}$", value))


class SyncErrorType(str, Enum):
    """Classification of sync errors.

    Allows callers to distinguish between different failure modes and respond
    appropriately (e.g., warn vs. fail, retry vs. abort).
    """

    NONE = "none"  # No error occurred
    GIT_ERROR = "git_error"  # Problem with git operations
    DATABASE_ERROR = "database_error"  # Problem with SQLite database
    PERMISSION_ERROR = "permission_error"  # File/directory access denied
    UNKNOWN = "unknown"  # Unclassified error


@dataclass
class SyncResult:
    """Result of a sync operation.

    Provides information about whether a sync was performed and its outcome.

    Attributes:
        synced: True if a sync was performed, False if index was already up to date.
        files_indexed: Number of files that were indexed (0 if no sync).
        error: Error message if sync failed, None otherwise.
        error_type: Classification of the error for programmatic handling.
    """

    synced: bool = False
    files_indexed: int = 0
    error: str | None = None
    error_type: SyncErrorType = field(default=SyncErrorType.NONE)


@dataclass(frozen=True)
class Chunk:
    """A chunk of code with metadata.

    Represents a semantically meaningful unit of code (function, class, etc.)
    or a line-based chunk for files without structure.

    Attributes:
        id: Unique identifier (blake3 of project_id + path + start_line + end_line).
        project_id: Project identifier (typically repo root path hash).
        path: File path relative to project root.
        lang: Language identifier from SUPPORTED_LANGUAGES (py, ts, go, rs, etc.).
        symbol: Symbol name (function/class name) or None for line chunks.
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (inclusive).
        content: The actual code content (must not be empty).
        content_hash: blake3 hash of content (64 lowercase hex chars).
        file_hash: blake3 hash of entire file (64 lowercase hex chars).
        tree_sha: Git tree SHA when chunk was indexed (40 hex chars or empty).
        rev: Git revision (commit SHA) when indexed, or "worktree".

    Raises:
        ValueError: If any field fails validation (invalid hashes, unknown language,
            empty content, or invalid line numbers).
    """

    id: str
    project_id: str
    path: Path
    lang: str
    symbol: str | None
    start_line: int
    end_line: int
    content: str
    content_hash: str
    file_hash: str
    tree_sha: str
    rev: str

    # Regex for validating blake3 hashes (64 lowercase hex chars)
    _BLAKE3_PATTERN = re.compile(r"^[a-f0-9]{64}$")
    # Regex for validating git SHAs (40 lowercase hex chars)
    _GIT_SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")

    def __post_init__(self) -> None:
        """Validate chunk data after initialization."""
        # Validate line numbers
        if self.start_line < 1 or self.end_line < 1:
            raise ValueError("Line numbers must be >= 1")
        if self.start_line > self.end_line:
            raise ValueError(
                f"start_line ({self.start_line}) > end_line ({self.end_line})"
            )

        # Validate content is not empty
        if not self.content or not self.content.strip():
            raise ValueError("content cannot be empty")

        # Validate content_hash (required, 64 lowercase hex chars)
        if not self._BLAKE3_PATTERN.match(self.content_hash):
            raise ValueError(
                f"Invalid blake3 hash for content_hash: must be 64 lowercase hex chars, "
                f"got: {self.content_hash!r}"
            )

        # Validate file_hash (required, 64 lowercase hex chars)
        if not self._BLAKE3_PATTERN.match(self.file_hash):
            raise ValueError(
                f"Invalid blake3 hash for file_hash: must be 64 lowercase hex chars, "
                f"got: {self.file_hash!r}"
            )

        # Validate tree_sha (empty or 40 lowercase hex chars)
        if self.tree_sha and not self._GIT_SHA_PATTERN.match(self.tree_sha):
            raise ValueError(
                f"Invalid git SHA for tree_sha: must be empty or 40 lowercase hex chars, "
                f"got: {self.tree_sha!r}"
            )

        # Validate language code
        if self.lang not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(
                f"Unknown language '{self.lang}'. Supported languages: {supported}"
            )

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute blake3 hash of content.

        Args:
            content: Text content to hash.

        Returns:
            Hex-encoded blake3 hash.
        """
        return blake3.blake3(content.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_id(
        project_id: str,
        path: Path,
        start_line: int,
        end_line: int,
    ) -> str:
        """Compute deterministic chunk ID.

        Args:
            project_id: Project identifier.
            path: File path.
            start_line: Starting line number.
            end_line: Ending line number.

        Returns:
            Hex-encoded blake3 hash serving as chunk ID.
        """
        key = f"{project_id}:{path}:{start_line}:{end_line}"
        return blake3.blake3(key.encode("utf-8")).hexdigest()

    def generate_preview(self, max_lines: int = 3) -> str:
        """Generate a preview of this chunk's content.

        Creates a shortened version of the chunk content suitable for display
        in search results.

        Args:
            max_lines: Maximum number of lines to include in preview.

        Returns:
            Preview string with truncation indicator if content exceeds max_lines.
        """
        lines = self.content.split("\n")
        preview_lines = lines[:max_lines]
        if len(lines) > max_lines:
            preview_lines.append("...")
        return "\n".join(preview_lines)

    def matches_language(self, lang_filter: str | None) -> bool:
        """Check if this chunk matches the given language filter.

        Args:
            lang_filter: Language code to filter by, or None for no filtering.

        Returns:
            True if lang_filter is None or matches this chunk's language.
        """
        if lang_filter is None:
            return True
        return self.lang == lang_filter


@dataclass
class RepoState:
    """Repository indexing state.

    Tracks what has been indexed and with which model.

    Attributes:
        last_tree_sha: Git tree SHA that was last indexed (empty if uninitialized).
        last_sync_mode: Sync mode used (SyncMode enum or commit SHA string).
        model_fingerprint: Fingerprint of embedding model used.
        version: Ember version that created the index.
        indexed_at: ISO-8601 timestamp of last indexing.
            Accepts either a string (validated and converted to ISO8601Timestamp)
            or an ISO8601Timestamp instance.

    Raises:
        ValueError: If any field fails validation (invalid SHA format,
            invalid sync mode, empty version, or invalid timestamp).
    """

    last_tree_sha: str
    last_sync_mode: str | SyncMode
    model_fingerprint: str
    version: str
    indexed_at: ISO8601Timestamp | str

    # Regex for validating git SHA (40 hex characters)
    _SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")

    def __post_init__(self) -> None:
        """Validate RepoState fields after initialization."""
        # Validate tree_sha: must be empty or valid 40-char hex SHA
        if self.last_tree_sha and not self._SHA_PATTERN.match(self.last_tree_sha):
            raise ValueError(
                f"tree_sha must be empty or a valid 40-character hex SHA, "
                f"got: {self.last_tree_sha!r}"
            )

        # Validate and normalize sync_mode
        if isinstance(self.last_sync_mode, SyncMode):
            pass  # Already a SyncMode enum
        elif isinstance(self.last_sync_mode, str):
            # Try to convert string to SyncMode enum
            try:
                object.__setattr__(self, "last_sync_mode", SyncMode(self.last_sync_mode))
            except ValueError:
                # Not a known SyncMode - check if it's a commit SHA
                if not SyncMode.is_commit_sha(self.last_sync_mode):
                    raise ValueError(
                        f"sync_mode must be 'none', 'worktree', 'staged', or a valid "
                        f"commit SHA (7-40 hex chars), got: {self.last_sync_mode!r}"
                    ) from None
        else:
            raise ValueError(
                f"sync_mode must be SyncMode enum or string, "
                f"got: {type(self.last_sync_mode).__name__}"
            )

        # Validate version is not empty
        if not self.version:
            raise ValueError("version cannot be empty")

        # Validate invariant: initialized state requires model_fingerprint
        # An initialized state has a non-empty tree_sha, and must have a model_fingerprint
        if self.last_tree_sha and not self.model_fingerprint:
            raise ValueError(
                "model_fingerprint is required when tree_sha is set (initialized state)"
            )

        # Validate and convert indexed_at to ISO8601Timestamp
        if not isinstance(self.indexed_at, ISO8601Timestamp):
            object.__setattr__(
                self, "indexed_at", ISO8601Timestamp.from_string(self.indexed_at)
            )

    @property
    def is_uninitialized(self) -> bool:
        """Check if the repository has never been indexed.

        Returns:
            True if no indexing has been performed (empty tree_sha).
        """
        return not self.last_tree_sha

    @property
    def indexed_at_str(self) -> str:
        """Get indexed_at as string for serialization."""
        return str(self.indexed_at)

    def is_stale(self, threshold_seconds: int) -> bool:
        """Check if the index is older than a threshold.

        Args:
            threshold_seconds: Age threshold in seconds.

        Returns:
            True if the index is older than threshold_seconds.
        """
        # Use the pre-parsed timestamp from ISO8601Timestamp
        return self.indexed_at.is_older_than(threshold_seconds)

    def needs_model_update(self, current_model_fingerprint: str) -> bool:
        """Check if the index needs updating due to model change.

        Args:
            current_model_fingerprint: Fingerprint of current embedding model.

        Returns:
            True if the stored fingerprint differs from current model.
        """
        return self.model_fingerprint != current_model_fingerprint

    @classmethod
    def uninitialized(cls, version: str) -> RepoState:
        """Create an uninitialized repo state.

        Factory method for creating a RepoState representing a repository
        that has never been indexed.

        Args:
            version: Ember version string (e.g., "1.2.0").

        Returns:
            RepoState with empty tree_sha and default values.
        """
        return cls(
            last_tree_sha="",
            last_sync_mode=SyncMode.NONE,
            model_fingerprint="",
            version=version,
            indexed_at=datetime.now(UTC).isoformat(),
        )

    @classmethod
    def from_sync(
        cls,
        tree_sha: str,
        sync_mode: str | SyncMode,
        model_fingerprint: str,
        version: str,
    ) -> RepoState:
        """Create state after a successful sync.

        Factory method for creating a RepoState representing a repository
        that has been successfully indexed.

        Args:
            tree_sha: Git tree SHA that was indexed.
            sync_mode: Sync mode used (SyncMode enum or commit SHA string).
            model_fingerprint: Fingerprint of embedding model used.
            version: Ember version string (e.g., "1.2.0").

        Returns:
            RepoState with the provided sync information and current timestamp.
        """
        return cls(
            last_tree_sha=tree_sha,
            last_sync_mode=sync_mode,
            model_fingerprint=model_fingerprint,
            version=version,
            indexed_at=datetime.now(UTC).isoformat(),
        )


@dataclass(frozen=True)
class SearchExplanation:
    """Explanation of why a search result matched the query.

    Provides typed access to scoring details from hybrid search.

    Attributes:
        fused_score: Combined score from reciprocal rank fusion (0.0-1.0).
        bm25_score: BM25 full-text search score (0.0-1.0).
        vector_score: Semantic vector similarity score (0.0-1.0).

    Raises:
        ValueError: If any score is outside the valid range [0.0, 1.0].
    """

    fused_score: float
    bm25_score: float = 0.0
    vector_score: float = 0.0

    def __post_init__(self) -> None:
        """Validate score ranges after initialization."""
        if not 0.0 <= self.fused_score <= 1.0:
            raise ValueError(
                f"fused_score must be between 0.0 and 1.0, got: {self.fused_score}"
            )
        if not 0.0 <= self.bm25_score <= 1.0:
            raise ValueError(
                f"bm25_score must be between 0.0 and 1.0, got: {self.bm25_score}"
            )
        if not 0.0 <= self.vector_score <= 1.0:
            raise ValueError(
                f"vector_score must be between 0.0 and 1.0, got: {self.vector_score}"
            )

    @property
    def effective_score(self) -> float:
        """Get the primary score for ranking.

        The fused score is the combined score from RRF fusion and should be
        used for ranking search results.

        Returns:
            The fused score value.
        """
        return self.fused_score

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with all score fields.
        """
        return {
            "fused_score": self.fused_score,
            "bm25_score": self.bm25_score,
            "vector_score": self.vector_score,
        }


@dataclass
class Query:
    """Search query with parameters.

    Attributes:
        text: Query text.
        topk: Maximum number of results to return.
        path_filter: Optional glob pattern to filter by file path.
            Accepts either a string (validated and converted to PathFilter)
            or a PathFilter instance.
        lang_filter: Optional language code to filter by.
            Accepts either a string (validated and converted to LanguageFilter)
            or a LanguageFilter instance.
        json_output: Whether to output JSON instead of human-readable text.

    Raises:
        ValueError: If text is empty, topk is not positive, or filters are invalid.
    """

    text: str
    topk: int = 20
    path_filter: PathFilter | str | None = None
    lang_filter: LanguageFilter | str | None = None
    json_output: bool = False

    def __post_init__(self) -> None:
        """Validate query data after initialization."""
        if not self.text or not self.text.strip():
            raise ValueError("Query text cannot be empty")
        if self.topk <= 0:
            raise ValueError(f"topk must be positive, got {self.topk}")

        # Validate and convert path_filter
        if self.path_filter is not None and not isinstance(self.path_filter, PathFilter):
            object.__setattr__(self, "path_filter", PathFilter(self.path_filter))

        # Validate and convert lang_filter
        if self.lang_filter is not None and not isinstance(self.lang_filter, LanguageFilter):
            object.__setattr__(self, "lang_filter", LanguageFilter(self.lang_filter))

    @property
    def path_filter_str(self) -> str | None:
        """Get path filter as string for use in queries."""
        if self.path_filter is None:
            return None
        return str(self.path_filter)

    @property
    def lang_filter_str(self) -> str | None:
        """Get language filter as string for use in queries."""
        if self.lang_filter is None:
            return None
        return str(self.lang_filter)


@dataclass
class SearchResult:
    """A single search result.

    Attributes:
        chunk: The matching chunk.
        score: Relevance score (higher is better).
        rank: Result rank (1-indexed).
        preview: Short preview of matching content.
        explanation: Explanation of scoring breakdown.
    """

    chunk: Chunk
    score: float
    rank: int
    preview: str = field(default="")
    explanation: SearchExplanation = field(
        default_factory=lambda: SearchExplanation(fused_score=0.0)
    )

    def format_preview(self, max_lines: int = 3) -> str:
        """Generate preview text from chunk content.

        Args:
            max_lines: Maximum number of lines to include.

        Returns:
            Preview string.
        """
        lines = self.chunk.content.split("\n")
        preview_lines = lines[:max_lines]
        if len(lines) > max_lines:
            preview_lines.append("...")
        return "\n".join(preview_lines)


@dataclass
class SearchResultSet:
    """Collection of search results with metadata.

    Wraps search results with information about retrieval quality,
    particularly for detecting index degradation when chunks are missing.

    Attributes:
        results: List of search results.
        requested_count: Number of results originally requested.
        missing_chunks: Number of chunks that couldn't be retrieved.
        warning: User-facing warning message if results are degraded.
    """

    results: list[SearchResult]
    requested_count: int = 0
    missing_chunks: int = 0
    warning: str | None = None

    @property
    def is_degraded(self) -> bool:
        """Check if results are degraded due to missing chunks."""
        return self.missing_chunks > 0

    def __iter__(self):
        """Allow iteration over results for backward compatibility."""
        return iter(self.results)

    def __len__(self) -> int:
        """Return number of results for backward compatibility."""
        return len(self.results)
