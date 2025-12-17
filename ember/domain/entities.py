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


@dataclass(frozen=True)
class Chunk:
    """A chunk of code with metadata.

    Represents a semantically meaningful unit of code (function, class, etc.)
    or a line-based chunk for files without structure.

    Attributes:
        id: Unique identifier (blake3 of project_id + path + start_line + end_line).
        project_id: Project identifier (typically repo root path hash).
        path: File path relative to project root.
        lang: Language identifier (py, ts, go, rs, etc.).
        symbol: Symbol name (function/class name) or None for line chunks.
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (inclusive).
        content: The actual code content.
        content_hash: blake3 hash of content (for deduplication).
        file_hash: blake3 hash of entire file (for change detection).
        tree_sha: Git tree SHA when chunk was indexed.
        rev: Git revision (commit SHA) when indexed, or "worktree".

    Raises:
        ValueError: If line numbers are invalid (< 1 or start > end).
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

    def __post_init__(self) -> None:
        """Validate chunk data after initialization."""
        if self.start_line < 1 or self.end_line < 1:
            raise ValueError("Line numbers must be >= 1")
        if self.start_line > self.end_line:
            raise ValueError(
                f"start_line ({self.start_line}) > end_line ({self.end_line})"
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
        fused_score: Combined score from reciprocal rank fusion.
        bm25_score: BM25 full-text search score.
        vector_score: Semantic vector similarity score.
    """

    fused_score: float
    bm25_score: float = 0.0
    vector_score: float = 0.0

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
