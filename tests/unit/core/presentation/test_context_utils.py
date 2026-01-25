"""Tests for context_utils module.

Tests the shared utility functions for extracting context lines around search results.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from ember.core.presentation.context_utils import (
    ContextData,
    ContextLine,
    get_context_for_result,
)
from ember.domain.entities import SearchExplanation


@dataclass
class MockChunk:
    """Mock Chunk for testing."""

    id: str = "test-chunk-id"
    project_id: str = "test-project"
    path: Path = field(default_factory=lambda: Path("src/example.py"))
    lang: str = "py"
    symbol: str | None = "test_function"
    start_line: int = 10
    end_line: int = 15
    content: str = "def test_function():\n    pass\n    return True"
    content_hash: str = "abc123"
    file_hash: str = "def456"
    tree_sha: str = "sha123"
    rev: str = "worktree"


@dataclass
class MockSearchResult:
    """Mock SearchResult for testing."""

    chunk: MockChunk = field(default_factory=MockChunk)
    score: float = 0.95
    rank: int = 1
    preview: str = "def test_function():"
    explanation: SearchExplanation = field(
        default_factory=lambda: SearchExplanation(fused_score=0.0)
    )


class MockFileSystem:
    """Mock FileSystem for testing."""

    def __init__(self, file_contents: dict[Path, list[str]] | None = None):
        """Initialize with optional file contents mapping.

        Args:
            file_contents: Dict mapping paths to list of lines.
        """
        self._files = file_contents or {}

    def read_text_lines(self, path: Path) -> list[str] | None:
        """Return mocked file lines or None."""
        return self._files.get(path)


class TestContextDataDataclass:
    """Tests for ContextData dataclass."""

    def test_context_data_creation(self):
        """ContextData can be created with all fields."""
        before = [ContextLine(line=1, content="line1")]
        chunk = [ContextLine(line=2, content="line2")]
        after = [ContextLine(line=3, content="line3")]

        data = ContextData(
            before=before,
            chunk=chunk,
            after=after,
            start_line=1,
            end_line=3,
        )

        assert data.before == before
        assert data.chunk == chunk
        assert data.after == after
        assert data.start_line == 1
        assert data.end_line == 3

    def test_context_data_to_dict(self):
        """ContextData can be converted to dictionary."""
        before = [ContextLine(line=1, content="line1")]
        chunk = [ContextLine(line=2, content="line2")]
        after = [ContextLine(line=3, content="line3")]

        data = ContextData(
            before=before,
            chunk=chunk,
            after=after,
            start_line=1,
            end_line=3,
        )

        result = data.to_dict()

        assert result == {
            "before": [{"line": 1, "content": "line1"}],
            "chunk": [{"line": 2, "content": "line2"}],
            "after": [{"line": 3, "content": "line3"}],
            "start_line": 1,
            "end_line": 3,
        }


class TestContextLineDataclass:
    """Tests for ContextLine dataclass."""

    def test_context_line_creation(self):
        """ContextLine can be created with line number and content."""
        line = ContextLine(line=5, content="hello world")

        assert line.line == 5
        assert line.content == "hello world"

    def test_context_line_to_dict(self):
        """ContextLine can be converted to dictionary."""
        line = ContextLine(line=5, content="hello world")

        result = line.to_dict()

        assert result == {"line": 5, "content": "hello world"}


class TestGetContextForResult:
    """Tests for get_context_for_result function."""

    def test_returns_context_with_before_and_after_lines(self):
        """Returns ContextData with proper before/chunk/after partitioning."""
        file_contents = {
            Path("/repo/test.py"): ["line1", "line2", "line3", "line4", "line5"]
        }
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=1,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert len(context.before) == 1
        assert context.before[0].line == 2
        assert context.before[0].content == "line2"
        assert len(context.chunk) == 1
        assert context.chunk[0].line == 3
        assert context.chunk[0].content == "line3"
        assert len(context.after) == 1
        assert context.after[0].line == 4
        assert context.after[0].content == "line4"

    def test_handles_multi_line_chunk(self):
        """Handles chunks spanning multiple lines."""
        file_contents = {
            Path("/repo/test.py"): [
                "line1",
                "line2",
                "line3",
                "line4",
                "line5",
                "line6",
            ]
        }
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=4)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=1,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert len(context.before) == 1
        assert context.before[0].line == 2
        assert len(context.chunk) == 2
        assert context.chunk[0].line == 3
        assert context.chunk[1].line == 4
        assert len(context.after) == 1
        assert context.after[0].line == 5

    def test_handles_file_start_boundary(self):
        """Handles context request at the start of file."""
        file_contents = {Path("/repo/test.py"): ["line1", "line2", "line3"]}
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=2,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert len(context.before) == 0
        assert context.start_line == 1
        assert len(context.chunk) == 1
        assert len(context.after) == 2

    def test_handles_file_end_boundary(self):
        """Handles context request at the end of file."""
        file_contents = {Path("/repo/test.py"): ["line1", "line2", "line3"]}
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=2,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert len(context.before) == 2
        assert len(context.chunk) == 1
        assert len(context.after) == 0
        assert context.end_line == 3

    def test_returns_none_for_missing_file(self):
        """Returns None when file doesn't exist."""
        mock_fs = MockFileSystem()  # Empty - no files

        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=1,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is None

    def test_returns_correct_start_and_end_lines(self):
        """Returns correct context start and end line numbers."""
        file_contents = {
            Path("/repo/test.py"): [f"line{i}" for i in range(1, 21)]
        }
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=10, end_line=12)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=3,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert context.start_line == 7  # 10 - 3
        assert context.end_line == 15  # 12 + 3

    def test_zero_context_lines(self):
        """With zero context lines, only returns chunk lines."""
        file_contents = {
            Path("/repo/test.py"): ["line1", "line2", "line3", "line4", "line5"]
        }
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=4)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=0,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert len(context.before) == 0
        assert len(context.chunk) == 3
        assert len(context.after) == 0
        assert context.start_line == 2
        assert context.end_line == 4

    def test_large_context_clamped_to_file_bounds(self):
        """Large context request is clamped to file boundaries."""
        file_contents = {Path("/repo/test.py"): ["line1", "line2", "line3"]}
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=100,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert context.start_line == 1
        assert context.end_line == 3
        assert len(context.before) == 1
        assert len(context.chunk) == 1
        assert len(context.after) == 1

    def test_uses_custom_file_reader(self):
        """Can use custom file reader function instead of filesystem."""
        custom_lines = ["custom1", "custom2", "custom3"]

        def custom_reader(path: Path) -> list[str]:
            return custom_lines

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=1,
            repo_root=Path("/repo"),
            file_reader=custom_reader,
        )

        assert context is not None
        assert context.chunk[0].content == "custom2"

    def test_custom_file_reader_returning_none(self):
        """Returns None when custom file reader returns None."""

        def failing_reader(path: Path) -> list[str] | None:
            return None

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=1,
            repo_root=Path("/repo"),
            file_reader=failing_reader,
        )

        assert context is None

    def test_fs_parameter_is_used_when_file_reader_not_provided(self):
        """Uses fs.read_text_lines when file_reader is not provided."""
        file_contents = {Path("/repo/test.py"): ["fs_line1", "fs_line2", "fs_line3"]}
        mock_fs = MockFileSystem(file_contents)

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        context = get_context_for_result(
            result=result,
            context_lines=1,
            repo_root=Path("/repo"),
            fs=mock_fs,
        )

        assert context is not None
        assert context.chunk[0].content == "fs_line2"


class TestContextDataIntegration:
    """Integration tests for ContextData usage patterns."""

    def test_context_data_works_with_json_serialization(self):
        """ContextData.to_dict() output is JSON serializable."""
        import json

        data = ContextData(
            before=[ContextLine(line=1, content="before")],
            chunk=[ContextLine(line=2, content="chunk")],
            after=[ContextLine(line=3, content="after")],
            start_line=1,
            end_line=3,
        )

        # Should not raise
        json_str = json.dumps(data.to_dict())
        parsed = json.loads(json_str)

        assert parsed["before"][0]["content"] == "before"
        assert parsed["chunk"][0]["content"] == "chunk"
        assert parsed["after"][0]["content"] == "after"
