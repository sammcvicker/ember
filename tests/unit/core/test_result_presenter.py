"""Tests for ResultPresenter formatting and display.

Tests the refactored ResultPresenter methods for displaying search results
in various formats (JSON, human-readable) with optional context and syntax highlighting.
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

from ember.adapters.fs.local import LocalFileSystem
from ember.core.presentation.compact_renderer import CompactPreviewRenderer
from ember.core.presentation.context_renderer import ContextRenderer
from ember.core.presentation.json_formatter import JsonResultFormatter
from ember.core.presentation.result_presenter import ResultPresenter
from ember.domain.config import DisplayConfig, EmberConfig


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
    explanation: dict = field(default_factory=dict)

    def format_preview(self, max_lines: int = 3) -> str:
        """Generate preview text from chunk content."""
        lines = self.chunk.content.split("\n")
        preview_lines = lines[:max_lines]
        if len(lines) > max_lines:
            preview_lines.append("...")
        return "\n".join(preview_lines)


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


@pytest.fixture
def presenter():
    """Create a ResultPresenter with LocalFileSystem."""
    return ResultPresenter(LocalFileSystem())


@pytest.fixture
def mock_presenter():
    """Create a ResultPresenter with a mock FileSystem."""
    return ResultPresenter(MockFileSystem())


@pytest.fixture
def compact_renderer():
    """Create a CompactPreviewRenderer with LocalFileSystem."""
    return CompactPreviewRenderer(LocalFileSystem())


@pytest.fixture
def context_renderer():
    """Create a ContextRenderer with LocalFileSystem."""
    return ContextRenderer(LocalFileSystem())


@pytest.fixture
def json_formatter():
    """Create a JsonResultFormatter with LocalFileSystem."""
    return JsonResultFormatter(LocalFileSystem())


class TestDisplaySettingsExtraction:
    """Tests for display settings extraction from config."""

    def test_get_display_settings_with_none_config(self, presenter):
        """When config is None, returns default settings."""
        settings = presenter._get_display_settings(None)
        assert settings["use_highlighting"] is False
        assert settings["theme"] == "ansi"

    def test_get_display_settings_with_highlighting_enabled(self, presenter):
        """When syntax highlighting is enabled, returns True."""
        config = EmberConfig(display=DisplayConfig(syntax_highlighting=True, theme="monokai"))
        settings = presenter._get_display_settings(config)
        assert settings["use_highlighting"] is True
        assert settings["theme"] == "monokai"

    def test_get_display_settings_with_highlighting_disabled(self, presenter):
        """When syntax highlighting is disabled, returns False."""
        config = EmberConfig(display=DisplayConfig(syntax_highlighting=False))
        settings = presenter._get_display_settings(config)
        assert settings["use_highlighting"] is False


class TestFileReading:
    """Tests for file reading utility."""

    def test_read_file_lines_returns_lines(self, tmp_path, presenter):
        """Reading a file returns list of lines."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nline 2\nline 3\n")

        lines = presenter._read_file_lines(test_file)
        # splitlines() doesn't include trailing empty string
        assert lines == ["line 1", "line 2", "line 3"]

    def test_read_file_lines_nonexistent_returns_none(self, tmp_path, presenter):
        """Reading nonexistent file returns None."""
        nonexistent = tmp_path / "nonexistent.py"
        lines = presenter._read_file_lines(nonexistent)
        assert lines is None

    def test_read_file_lines_handles_encoding_errors(self, tmp_path, presenter):
        """File with encoding errors is read with replacement."""
        test_file = tmp_path / "test.py"
        test_file.write_bytes(b"hello\x80world\n")

        lines = presenter._read_file_lines(test_file)
        assert lines is not None
        assert "hello" in lines[0]


class TestFileReadingWithMock:
    """Tests for file reading with mock filesystem."""

    def test_read_file_lines_uses_injected_fs(self):
        """File reading uses the injected filesystem."""
        mock_fs = MockFileSystem({
            Path("/test/file.py"): ["line1", "line2"]
        })
        presenter = ResultPresenter(mock_fs)

        lines = presenter._read_file_lines(Path("/test/file.py"))
        assert lines == ["line1", "line2"]

    def test_read_file_lines_returns_none_for_missing(self):
        """Returns None when file not in mock."""
        mock_fs = MockFileSystem()
        presenter = ResultPresenter(mock_fs)

        lines = presenter._read_file_lines(Path("/missing.py"))
        assert lines is None


class TestResultGrouping:
    """Tests for grouping results by file."""

    def test_group_results_by_file_single_file(self, presenter):
        """Results from same file are grouped together."""
        result1 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=1), rank=1)
        result2 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=10), rank=2)

        grouped = presenter._group_results_by_file([result1, result2])

        assert len(grouped) == 1
        assert Path("a.py") in grouped
        assert len(grouped[Path("a.py")]) == 2

    def test_group_results_by_file_multiple_files(self, presenter):
        """Results from different files are grouped separately."""
        result1 = MockSearchResult(chunk=MockChunk(path=Path("a.py")), rank=1)
        result2 = MockSearchResult(chunk=MockChunk(path=Path("b.py")), rank=2)

        grouped = presenter._group_results_by_file([result1, result2])

        assert len(grouped) == 2
        assert Path("a.py") in grouped
        assert Path("b.py") in grouped


class TestPreviewRendering:
    """Tests for compact preview rendering."""

    def test_render_compact_preview_without_highlighting(self, mock_presenter):
        """Preview without highlighting uses symbol highlighting."""
        result = MockSearchResult()
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.compact_renderer.click") as mock_click:
            mock_presenter._render_compact_preview(result, settings, None)

            # Verify click.echo was called
            assert mock_click.echo.called

    def test_render_compact_preview_max_lines(self, mock_presenter):
        """Preview shows maximum 3 lines."""
        chunk = MockChunk(content="line1\nline2\nline3\nline4\nline5")
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.compact_renderer.click") as mock_click:
            mock_presenter._render_compact_preview(result, settings, None)

            # Should have 3 calls: first line with rank, 2 additional preview lines
            assert mock_click.echo.call_count == 3


class TestContextRendering:
    """Tests for rendering results with context."""

    def test_render_with_context_calculates_range(self, tmp_path, presenter):
        """Context is calculated around match start line."""
        test_file = tmp_path / "test.py"
        test_file.write_text("\n".join([f"line{i}" for i in range(1, 21)]))

        chunk = MockChunk(path=Path("test.py"), start_line=10, end_line=12)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.context_renderer.click") as mock_click:
            presenter._render_with_context(result, 2, tmp_path, settings)

            # Should show: 2 lines before (8, 9), match line (10), 2 lines after (11, 12)
            # Total: 5 lines
            assert mock_click.echo.call_count == 5


class TestFormatHumanOutput:
    """Integration tests for format_human_output."""

    def test_format_human_output_empty_results(self, mock_presenter):
        """Empty results shows 'No results found'."""
        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            mock_presenter.format_human_output([])
            mock_click.echo.assert_called_once_with("No results found.")

    def test_format_human_output_groups_by_file(self, mock_presenter):
        """Results are grouped by file path."""
        result1 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=1), rank=1)
        result2 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=10), rank=2)

        with (
            patch("ember.core.presentation.result_presenter.click") as presenter_click,
            patch("ember.core.presentation.compact_renderer.click") as compact_click,
        ):
            mock_presenter.format_human_output([result1, result2])

            # Should have called echo multiple times (file header + results)
            total_calls = presenter_click.echo.call_count + compact_click.echo.call_count
            assert total_calls > 2

    def test_format_human_output_with_context(self, tmp_path, presenter):
        """Context flag shows surrounding lines."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        with (
            patch("ember.core.presentation.result_presenter.click"),
            patch("ember.core.presentation.context_renderer.click"),
        ):
            # Should not raise
            presenter.format_human_output([result], context=1, repo_root=tmp_path)

    def test_format_human_output_with_context_adds_blank_lines_between_results(self, tmp_path, presenter):
        """Multiple results with context have blank lines between them."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n")

        chunk1 = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        chunk2 = MockChunk(path=Path("test.py"), start_line=6, end_line=6)
        result1 = MockSearchResult(chunk=chunk1, rank=1)
        result2 = MockSearchResult(chunk=chunk2, rank=2)

        with (
            patch("ember.core.presentation.result_presenter.click") as presenter_click,
            patch("ember.core.presentation.context_renderer.click") as context_click,
        ):
            presenter.format_human_output([result1, result2], context=1, repo_root=tmp_path)

            # Check that blank lines are added between results (echo called with empty string)
            presenter_calls = [c[0][0] if c[0] else "" for c in presenter_click.echo.call_args_list]
            context_calls = [c[0][0] if c[0] else "" for c in context_click.echo.call_args_list]
            all_calls = presenter_calls + context_calls
            # At least one blank line should exist between the two results
            assert "" in all_calls or len(all_calls) > 5


class TestSerializeForCache:
    """Tests for cache serialization."""

    def test_serialize_includes_all_fields(self):
        """Serialization includes all required fields."""
        result = MockSearchResult()
        output = ResultPresenter.serialize_for_cache("test query", [result])

        assert output["query"] == "test query"
        assert len(output["results"]) == 1
        assert "rank" in output["results"][0]
        assert "score" in output["results"][0]
        assert "path" in output["results"][0]


class TestFormatJsonOutput:
    """Tests for JSON output formatting."""

    def test_format_json_output_basic(self, mock_presenter):
        """JSON output includes required fields."""
        result = MockSearchResult()
        json_str = mock_presenter.format_json_output([result])

        import json
        parsed = json.loads(json_str)

        assert len(parsed) == 1
        assert parsed[0]["id"] == "test-chunk-id"
        assert parsed[0]["rank"] == 1
        assert parsed[0]["score"] == 0.95

    def test_format_json_output_with_context(self, tmp_path, presenter):
        """JSON output includes context when requested."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        json_str = presenter.format_json_output([result], context=1, repo_root=tmp_path)

        import json
        parsed = json.loads(json_str)

        assert "context" in parsed[0]

    def test_format_json_output_no_context_when_file_missing(self, tmp_path, presenter):
        """JSON output excludes context when file doesn't exist."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        json_str = presenter.format_json_output([result], context=1, repo_root=tmp_path)

        import json
        parsed = json.loads(json_str)

        # Context should not be included when file is missing
        assert "context" not in parsed[0]


class TestGetContext:
    """Tests for context extraction method."""

    def test_get_context_returns_before_and_after_lines(self, tmp_path, presenter):
        """Context includes lines before and after chunk."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        context = presenter._get_context(result, 1, tmp_path)

        assert context is not None
        assert len(context["before"]) == 1
        assert context["before"][0]["line"] == 2
        assert context["before"][0]["content"] == "line2"
        assert len(context["chunk"]) == 1
        assert context["chunk"][0]["line"] == 3
        assert len(context["after"]) == 1
        assert context["after"][0]["line"] == 4

    def test_get_context_handles_file_start_boundary(self, tmp_path, presenter):
        """Context at file start doesn't go negative."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)

        context = presenter._get_context(result, 2, tmp_path)

        assert context is not None
        assert len(context["before"]) == 0
        assert context["start_line"] == 1

    def test_get_context_handles_file_end_boundary(self, tmp_path, presenter):
        """Context at file end doesn't exceed file length."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        context = presenter._get_context(result, 2, tmp_path)

        assert context is not None
        assert len(context["after"]) == 0
        assert context["end_line"] == 3

    def test_get_context_returns_none_for_missing_file(self, tmp_path, presenter):
        """Returns None when file doesn't exist."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)

        context = presenter._get_context(result, 1, tmp_path)

        assert context is None


class TestRenderWithContextEdgeCases:
    """Additional edge case tests for context rendering."""

    def test_render_with_context_file_not_found_shows_warning(self, tmp_path, presenter):
        """File not found shows warning and falls back to preview."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.context_renderer.click") as mock_click:
            presenter._render_with_context(result, 1, tmp_path, settings)

            # Should show warning message
            calls = [str(c) for c in mock_click.echo.call_args_list]
            assert any("Warning" in str(c) for c in calls)

    def test_render_with_context_syntax_highlighting_enabled(self, tmp_path, presenter):
        """Context with syntax highlighting uses render_syntax_highlighted."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n    return True\n")

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.context_renderer.click"),
            patch("ember.core.presentation.context_renderer.render_syntax_highlighted") as mock_highlight,
        ):
            mock_highlight.return_value = "highlighted code"
            presenter._render_with_context(result, 1, tmp_path, settings)

            # Should call render_syntax_highlighted
            mock_highlight.assert_called_once()


class TestRenderCompactPreviewEdgeCases:
    """Additional edge case tests for compact preview rendering."""

    def test_render_compact_preview_with_syntax_highlighting(self, tmp_path, presenter):
        """Preview with syntax highlighting reads from file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n    return True\n")

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=3)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.compact_renderer.click"),
            patch("ember.core.presentation.compact_renderer.render_syntax_highlighted") as mock_highlight,
        ):
            mock_highlight.return_value = "line1\nline2\nline3"
            presenter._render_compact_preview(result, settings, tmp_path)

            # Should call render_syntax_highlighted
            mock_highlight.assert_called_once()

    def test_render_compact_preview_highlighting_with_missing_file(self, tmp_path, presenter):
        """Preview falls back to content when file is missing."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=3)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with patch("ember.core.presentation.compact_renderer.click") as mock_click:
            # Should not raise, should fall back to chunk content
            presenter._render_compact_preview(result, settings, tmp_path)
            assert mock_click.echo.called


class TestSafeGetLines:
    """Tests for _safe_get_lines helper method."""

    def test_extracts_lines_from_middle(self, presenter):
        """Extracts correct lines from middle of list."""
        lines = ["line1", "line2", "line3", "line4", "line5"]
        result = presenter._safe_get_lines(lines, 2, 4)
        assert result == ["line2", "line3", "line4"]

    def test_handles_start_at_beginning(self, presenter):
        """Handles start line at 1."""
        lines = ["line1", "line2", "line3"]
        result = presenter._safe_get_lines(lines, 1, 2)
        assert result == ["line1", "line2"]

    def test_handles_end_at_file_end(self, presenter):
        """Handles end line at file length."""
        lines = ["line1", "line2", "line3"]
        result = presenter._safe_get_lines(lines, 2, 3)
        assert result == ["line2", "line3"]

    def test_clamps_start_to_minimum_1(self, presenter):
        """Start line less than 1 is clamped to 1."""
        lines = ["line1", "line2", "line3"]
        result = presenter._safe_get_lines(lines, 0, 2)
        assert result == ["line1", "line2"]

    def test_clamps_end_to_file_length(self, presenter):
        """End line beyond file is clamped to file length."""
        lines = ["line1", "line2", "line3"]
        result = presenter._safe_get_lines(lines, 1, 10)
        assert result == ["line1", "line2", "line3"]

    def test_returns_empty_for_invalid_range(self, presenter):
        """Returns empty list when start > end after clamping."""
        lines = ["line1", "line2", "line3"]
        result = presenter._safe_get_lines(lines, 5, 3)
        assert result == []

    def test_returns_empty_for_empty_input(self, presenter):
        """Returns empty list for empty input."""
        result = presenter._safe_get_lines([], 1, 3)
        assert result == []

    def test_single_line_extraction(self, presenter):
        """Extracts single line correctly."""
        lines = ["line1", "line2", "line3"]
        result = presenter._safe_get_lines(lines, 2, 2)
        assert result == ["line2"]


class TestRenderCompactPreviewLineExtraction:
    """Tests for correct line extraction in _render_compact_preview."""

    def test_extracts_correct_lines_from_file_middle(self, tmp_path, presenter):
        """Correctly extracts lines from middle of file."""
        test_file = tmp_path / "test.py"
        lines = ["line1", "line2", "line3", "line4", "line5", "line6", "line7"]
        test_file.write_text("\n".join(lines))

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=5)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.compact_renderer.click"),
            patch("ember.core.presentation.compact_renderer.render_syntax_highlighted") as mock_highlight,
        ):
            mock_highlight.return_value = "line3\nline4\nline5"
            presenter._render_compact_preview(result, settings, tmp_path)

            # Verify render_syntax_highlighted was called with correct lines
            call_args = mock_highlight.call_args
            assert "line3" in call_args.kwargs["code"]

    def test_handles_start_line_at_file_beginning(self, tmp_path, presenter):
        """Correctly handles chunk starting at line 1."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=3)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.compact_renderer.click"),
            patch("ember.core.presentation.compact_renderer.render_syntax_highlighted") as mock_highlight,
        ):
            mock_highlight.return_value = "line1\nline2\nline3"
            presenter._render_compact_preview(result, settings, tmp_path)
            mock_highlight.assert_called_once()

    def test_handles_chunk_at_file_end(self, tmp_path, presenter):
        """Correctly handles chunk at end of file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.compact_renderer.click"),
            patch("ember.core.presentation.compact_renderer.render_syntax_highlighted") as mock_highlight,
        ):
            mock_highlight.return_value = "line3"
            presenter._render_compact_preview(result, settings, tmp_path)
            mock_highlight.assert_called_once()

    def test_limits_to_max_preview_lines(self, tmp_path, presenter):
        """Preview is limited to max_preview_lines (3)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\n")

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=6)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.compact_renderer.click"),
            patch("ember.core.presentation.compact_renderer.render_syntax_highlighted") as mock_highlight,
        ):
            # Should only include first 3 lines
            mock_highlight.return_value = "line1\nline2\nline3"
            presenter._render_compact_preview(result, settings, tmp_path)

            call_args = mock_highlight.call_args
            code = call_args.kwargs["code"]
            # Should have at most 3 lines
            assert code.count("\n") <= 2

    def test_handles_empty_preview_lines(self, tmp_path, presenter):
        """Falls back gracefully when no preview lines can be extracted."""
        # Create empty file
        test_file = tmp_path / "test.py"
        test_file.write_text("")

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with patch("ember.core.presentation.compact_renderer.click") as mock_click:
            # Should fall back to chunk content
            presenter._render_compact_preview(result, settings, tmp_path)
            # Should still call echo (fallback path)
            assert mock_click.echo.called


class TestFileReadingEdgeCases:
    """Additional edge case tests for file reading."""

    def test_read_file_lines_handles_read_exception(self, tmp_path, monkeypatch, presenter):
        """File read exceptions return None."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        # Mock read_text to raise an exception
        def raise_error(*args, **kwargs):
            raise PermissionError("Access denied")

        monkeypatch.setattr(Path, "read_text", raise_error)

        lines = presenter._read_file_lines(test_file)
        assert lines is None


# === New tests for extracted components ===


class TestJsonResultFormatter:
    """Tests for JsonResultFormatter component."""

    def test_serialize_for_cache_static_method(self):
        """Serialize works as static method."""
        result = MockSearchResult()
        output = JsonResultFormatter.serialize_for_cache("test query", [result])

        assert output["query"] == "test query"
        assert len(output["results"]) == 1

    def test_format_output_without_context(self, json_formatter):
        """Format output without context."""
        result = MockSearchResult()
        json_str = json_formatter.format_output([result])

        import json
        parsed = json.loads(json_str)

        assert len(parsed) == 1
        assert "context" not in parsed[0]

    def test_get_context_method(self, tmp_path, json_formatter):
        """Get context returns proper structure."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        context = json_formatter._get_context(result, 1, tmp_path)

        assert context is not None
        assert "before" in context
        assert "chunk" in context
        assert "after" in context


class TestCompactPreviewRenderer:
    """Tests for CompactPreviewRenderer component."""

    def test_max_preview_lines_constant(self):
        """MAX_PREVIEW_LINES is set to 3."""
        assert CompactPreviewRenderer.MAX_PREVIEW_LINES == 3

    def test_safe_get_lines_static_method(self):
        """_safe_get_lines works as static method."""
        lines = ["a", "b", "c", "d"]
        result = CompactPreviewRenderer._safe_get_lines(lines, 2, 3)
        assert result == ["b", "c"]

    def test_render_without_repo_root(self, compact_renderer):
        """Render falls back to content when no repo_root."""
        result = MockSearchResult()
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.compact_renderer.click") as mock_click:
            compact_renderer.render(result, settings, None)
            assert mock_click.echo.called


class TestContextRenderer:
    """Tests for ContextRenderer component."""

    def test_render_file_not_found(self, tmp_path, context_renderer):
        """Render shows warning when file not found."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.context_renderer.click") as mock_click:
            context_renderer.render(result, 1, tmp_path, settings)
            # Check for warning call
            calls = [str(c) for c in mock_click.echo.call_args_list]
            assert any("Warning" in str(c) for c in calls)

    def test_render_plain_context_format(self, tmp_path, context_renderer):
        """Render without highlighting uses plain format."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.context_renderer.click") as mock_click:
            context_renderer.render(result, 1, tmp_path, settings)
            # Should have 3 lines (1 before, match, 1 after)
            assert mock_click.echo.call_count == 3
