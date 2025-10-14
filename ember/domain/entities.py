"""Domain entities and value objects.

Core domain models representing the business concepts of Ember.
These are pure Python dataclasses with no dependencies on infrastructure.
"""

from dataclasses import dataclass, field
from pathlib import Path

import blake3


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
        last_tree_sha: Git tree SHA that was last indexed.
        last_sync_mode: Sync mode used (worktree, staged, or commit SHA).
        model_fingerprint: Fingerprint of embedding model used.
        version: Ember version that created the index.
        indexed_at: ISO-8601 timestamp of last indexing.
    """

    last_tree_sha: str
    last_sync_mode: str
    model_fingerprint: str
    version: str
    indexed_at: str


@dataclass
class Query:
    """Search query with parameters.

    Attributes:
        text: Query text.
        topk: Maximum number of results to return.
        path_filter: Optional glob pattern to filter by file path.
        lang_filter: Optional language code to filter by.
        json_output: Whether to output JSON instead of human-readable text.
    """

    text: str
    topk: int = 20
    path_filter: str | None = None
    lang_filter: str | None = None
    json_output: bool = False


@dataclass
class SearchResult:
    """A single search result.

    Attributes:
        chunk: The matching chunk.
        score: Relevance score (higher is better).
        rank: Result rank (1-indexed).
        preview: Short preview of matching content.
        explanation: Optional explanation of why this matched.
    """

    chunk: Chunk
    score: float
    rank: int
    preview: str = field(default="")
    explanation: dict[str, float | str] = field(default_factory=dict)

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
