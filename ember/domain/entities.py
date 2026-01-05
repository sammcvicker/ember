"""Domain entities and value objects.

Core domain models representing the business concepts of Ember.
These are pure Python dataclasses with no dependencies on infrastructure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import blake3

from ember.domain.value_objects import (
    SUPPORTED_LANGUAGES,
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

    Domain Invariants:
        - Line numbers are 1-indexed and start_line <= end_line
        - Content must be non-empty (not just whitespace)
        - content_hash and file_hash must be valid blake3 hashes (64 lowercase hex)
        - tree_sha must be empty or a valid git SHA (40 lowercase hex)
        - lang must be in SUPPORTED_LANGUAGES

    Raises:
        ValueError: If any field fails validation.
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

    @staticmethod
    def _validate_line_numbers(start_line: int, end_line: int) -> None:
        """Validate line number constraints."""
        if start_line < 1 or end_line < 1:
            raise ValueError("Line numbers must be >= 1")
        if start_line > end_line:
            raise ValueError(f"start_line ({start_line}) > end_line ({end_line})")

    @staticmethod
    def _validate_content(content: str) -> None:
        """Validate content is non-empty."""
        if not content or not content.strip():
            raise ValueError("content cannot be empty")

    @classmethod
    def _validate_blake3_hash(cls, value: str, field_name: str) -> None:
        """Validate a blake3 hash field."""
        if not cls._BLAKE3_PATTERN.match(value):
            raise ValueError(
                f"Invalid blake3 hash for {field_name}: must be 64 lowercase hex chars, "
                f"got: {value!r}"
            )

    @classmethod
    def _validate_tree_sha(cls, tree_sha: str) -> None:
        """Validate tree SHA (empty or 40 hex chars)."""
        if tree_sha and not cls._GIT_SHA_PATTERN.match(tree_sha):
            raise ValueError(
                f"Invalid git SHA for tree_sha: must be empty or 40 lowercase hex chars, "
                f"got: {tree_sha!r}"
            )

    @staticmethod
    def _validate_language(lang: str) -> None:
        """Validate language code."""
        if lang not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(f"Unknown language '{lang}'. Supported languages: {supported}")

    def __post_init__(self) -> None:
        """Validate chunk data after initialization."""
        self._validate_line_numbers(self.start_line, self.end_line)
        self._validate_content(self.content)
        self._validate_blake3_hash(self.content_hash, "content_hash")
        self._validate_blake3_hash(self.file_hash, "file_hash")
        self._validate_tree_sha(self.tree_sha)
        self._validate_language(self.lang)

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


@dataclass(frozen=True)
class SearchExplanation:
    """Explanation of why a search result matched the query.

    Provides typed access to scoring details from hybrid search.

    Attributes:
        fused_score: Combined score from reciprocal rank fusion (0.0-1.0).
        bm25_score: Raw BM25 full-text search score from FTS5 (non-negative, unbounded).
        vector_score: Semantic vector similarity score (0.0-1.0).

    Raises:
        ValueError: If fused_score or vector_score is outside [0.0, 1.0],
            or if bm25_score is negative.
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
        if self.bm25_score < 0.0:
            raise ValueError(
                f"bm25_score must be non-negative, got: {self.bm25_score}"
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


@dataclass(frozen=True)
class Query:
    """Search query with parameters (immutable).

    This is a frozen dataclass - instances cannot be modified after creation.
    Use Query.from_strings() factory method to create instances from string inputs.

    Attributes:
        text: Query text.
        topk: Maximum number of results to return.
        path_filter: Optional PathFilter to filter by file path.
        lang_filter: Optional LanguageFilter to filter by language.
        json_output: Whether to output JSON instead of human-readable text.

    Domain Invariants:
        - text must be non-empty (not just whitespace)
        - topk must be positive
        - path_filter (if provided) must be a PathFilter instance
        - lang_filter (if provided) must be a LanguageFilter instance

    Raises:
        ValueError: If text is empty or topk is not positive.
    """

    text: str
    topk: int = 20
    path_filter: PathFilter | None = None
    lang_filter: LanguageFilter | None = None
    json_output: bool = False

    @staticmethod
    def _validate_text(text: str) -> None:
        """Validate query text is non-empty."""
        if not text or not text.strip():
            raise ValueError("Query text cannot be empty")

    @staticmethod
    def _validate_topk(topk: int) -> None:
        """Validate topk is positive."""
        if topk <= 0:
            raise ValueError(f"topk must be positive, got {topk}")

    def __post_init__(self) -> None:
        """Validate query data after initialization."""
        self._validate_text(self.text)
        self._validate_topk(self.topk)

    @classmethod
    def from_strings(
        cls,
        text: str,
        topk: int = 20,
        path_filter: str | None = None,
        lang_filter: str | None = None,
        json_output: bool = False,
    ) -> Query:
        """Create a Query from string inputs.

        Factory method that converts string filter values to their respective
        value objects (PathFilter, LanguageFilter).

        Args:
            text: Query text (must be non-empty).
            topk: Maximum number of results to return (must be positive).
            path_filter: Optional glob pattern string for path filtering.
            lang_filter: Optional language code string for language filtering.
            json_output: Whether to output JSON format.

        Returns:
            A new Query instance with validated and converted fields.

        Raises:
            ValueError: If text is empty, topk is not positive, or filters are invalid.
        """
        return cls(
            text=text,
            topk=topk,
            path_filter=PathFilter(path_filter) if path_filter else None,
            lang_filter=LanguageFilter(lang_filter) if lang_filter else None,
            json_output=json_output,
        )

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
