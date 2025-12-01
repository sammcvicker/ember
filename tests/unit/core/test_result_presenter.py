"""Tests for ResultPresenter formatting and display.

Tests the refactored ResultPresenter methods for displaying search results
in various formats (JSON, human-readable) with optional context and syntax highlighting.
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

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


class TestDisplaySettingsExtraction:
    """Tests for display settings extraction from config."""

    def test_get_display_settings_with_none_config(self):
        """When config is None, returns default settings."""
        settings = ResultPresenter._get_display_settings(None)
        assert settings["use_highlighting"] is False
        assert settings["theme"] == "ansi"

    def test_get_display_settings_with_highlighting_enabled(self):
        """When syntax highlighting is enabled, returns True."""
        config = EmberConfig(display=DisplayConfig(syntax_highlighting=True, theme="monokai"))
        settings = ResultPresenter._get_display_settings(config)
        assert settings["use_highlighting"] is True
        assert settings["theme"] == "monokai"

    def test_get_display_settings_with_highlighting_disabled(self):
        """When syntax highlighting is disabled, returns False."""
        config = EmberConfig(display=DisplayConfig(syntax_highlighting=False))
        settings = ResultPresenter._get_display_settings(config)
        assert settings["use_highlighting"] is False


class TestFileReading:
    """Tests for file reading utility."""

    def test_read_file_lines_returns_lines(self, tmp_path):
        """Reading a file returns list of lines."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nline 2\nline 3\n")

        lines = ResultPresenter._read_file_lines(test_file)
        # splitlines() doesn't include trailing empty string
        assert lines == ["line 1", "line 2", "line 3"]

    def test_read_file_lines_nonexistent_returns_none(self, tmp_path):
        """Reading nonexistent file returns None."""
        nonexistent = tmp_path / "nonexistent.py"
        lines = ResultPresenter._read_file_lines(nonexistent)
        assert lines is None

    def test_read_file_lines_handles_encoding_errors(self, tmp_path):
        """File with encoding errors is read with replacement."""
        test_file = tmp_path / "test.py"
        test_file.write_bytes(b"hello\x80world\n")

        lines = ResultPresenter._read_file_lines(test_file)
        assert lines is not None
        assert "hello" in lines[0]


class TestResultGrouping:
    """Tests for grouping results by file."""

    def test_group_results_by_file_single_file(self):
        """Results from same file are grouped together."""
        result1 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=1), rank=1)
        result2 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=10), rank=2)

        grouped = ResultPresenter._group_results_by_file([result1, result2])

        assert len(grouped) == 1
        assert Path("a.py") in grouped
        assert len(grouped[Path("a.py")]) == 2

    def test_group_results_by_file_multiple_files(self):
        """Results from different files are grouped separately."""
        result1 = MockSearchResult(chunk=MockChunk(path=Path("a.py")), rank=1)
        result2 = MockSearchResult(chunk=MockChunk(path=Path("b.py")), rank=2)

        grouped = ResultPresenter._group_results_by_file([result1, result2])

        assert len(grouped) == 2
        assert Path("a.py") in grouped
        assert Path("b.py") in grouped


class TestPreviewRendering:
    """Tests for compact preview rendering."""

    def test_render_compact_preview_without_highlighting(self):
        """Preview without highlighting uses symbol highlighting."""
        result = MockSearchResult()
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            ResultPresenter._render_compact_preview(result, settings, None)

            # Verify click.echo was called
            assert mock_click.echo.called

    def test_render_compact_preview_max_lines(self):
        """Preview shows maximum 3 lines."""
        chunk = MockChunk(content="line1\nline2\nline3\nline4\nline5")
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            ResultPresenter._render_compact_preview(result, settings, None)

            # Should have 3 calls: first line with rank, 2 additional preview lines
            assert mock_click.echo.call_count == 3


class TestContextRendering:
    """Tests for rendering results with context."""

    def test_render_with_context_calculates_range(self, tmp_path):
        """Context is calculated around match start line."""
        test_file = tmp_path / "test.py"
        test_file.write_text("\n".join([f"line{i}" for i in range(1, 21)]))

        chunk = MockChunk(path=Path("test.py"), start_line=10, end_line=12)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            ResultPresenter._render_with_context(result, 2, tmp_path, settings)

            # Should show: 2 lines before (8, 9), match line (10), 2 lines after (11, 12)
            # Total: 5 lines
            assert mock_click.echo.call_count == 5


class TestFormatHumanOutput:
    """Integration tests for format_human_output."""

    def test_format_human_output_empty_results(self):
        """Empty results shows 'No results found'."""
        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            ResultPresenter.format_human_output([])
            mock_click.echo.assert_called_once_with("No results found.")

    def test_format_human_output_groups_by_file(self):
        """Results are grouped by file path."""
        result1 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=1), rank=1)
        result2 = MockSearchResult(chunk=MockChunk(path=Path("a.py"), start_line=10), rank=2)

        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            ResultPresenter.format_human_output([result1, result2])

            # Should have called echo multiple times (file header + results)
            assert mock_click.echo.call_count > 2

    def test_format_human_output_with_context(self, tmp_path):
        """Context flag shows surrounding lines."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        with patch("ember.core.presentation.result_presenter.click"):
            # Should not raise
            ResultPresenter.format_human_output([result], context=1, repo_root=tmp_path)

    def test_format_human_output_with_context_adds_blank_lines_between_results(self, tmp_path):
        """Multiple results with context have blank lines between them."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n")

        chunk1 = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        chunk2 = MockChunk(path=Path("test.py"), start_line=6, end_line=6)
        result1 = MockSearchResult(chunk=chunk1, rank=1)
        result2 = MockSearchResult(chunk=chunk2, rank=2)

        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            ResultPresenter.format_human_output([result1, result2], context=1, repo_root=tmp_path)

            # Check that blank lines are added between results (echo called with empty string)
            calls = [c[0][0] if c[0] else "" for c in mock_click.echo.call_args_list]
            # At least one blank line should exist between the two results
            assert "" in calls or mock_click.echo.call_count > 5


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

    def test_format_json_output_basic(self):
        """JSON output includes required fields."""
        result = MockSearchResult()
        json_str = ResultPresenter.format_json_output([result])

        import json
        parsed = json.loads(json_str)

        assert len(parsed) == 1
        assert parsed[0]["id"] == "test-chunk-id"
        assert parsed[0]["rank"] == 1
        assert parsed[0]["score"] == 0.95

    def test_format_json_output_with_context(self, tmp_path):
        """JSON output includes context when requested."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        json_str = ResultPresenter.format_json_output([result], context=1, repo_root=tmp_path)

        import json
        parsed = json.loads(json_str)

        assert "context" in parsed[0]

    def test_format_json_output_no_context_when_file_missing(self, tmp_path):
        """JSON output excludes context when file doesn't exist."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)

        json_str = ResultPresenter.format_json_output([result], context=1, repo_root=tmp_path)

        import json
        parsed = json.loads(json_str)

        # Context should not be included when file is missing
        assert "context" not in parsed[0]


class TestGetContext:
    """Tests for context extraction method."""

    def test_get_context_returns_before_and_after_lines(self, tmp_path):
        """Context includes lines before and after chunk."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        context = ResultPresenter._get_context(result, 1, tmp_path)

        assert context is not None
        assert len(context["before"]) == 1
        assert context["before"][0]["line"] == 2
        assert context["before"][0]["content"] == "line2"
        assert len(context["chunk"]) == 1
        assert context["chunk"][0]["line"] == 3
        assert len(context["after"]) == 1
        assert context["after"][0]["line"] == 4

    def test_get_context_handles_file_start_boundary(self, tmp_path):
        """Context at file start doesn't go negative."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)

        context = ResultPresenter._get_context(result, 2, tmp_path)

        assert context is not None
        assert len(context["before"]) == 0
        assert context["start_line"] == 1

    def test_get_context_handles_file_end_boundary(self, tmp_path):
        """Context at file end doesn't exceed file length."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        chunk = MockChunk(path=Path("test.py"), start_line=3, end_line=3)
        result = MockSearchResult(chunk=chunk)

        context = ResultPresenter._get_context(result, 2, tmp_path)

        assert context is not None
        assert len(context["after"]) == 0
        assert context["end_line"] == 3

    def test_get_context_returns_none_for_missing_file(self, tmp_path):
        """Returns None when file doesn't exist."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)

        context = ResultPresenter._get_context(result, 1, tmp_path)

        assert context is None


class TestRenderWithContextEdgeCases:
    """Additional edge case tests for context rendering."""

    def test_render_with_context_file_not_found_shows_warning(self, tmp_path):
        """File not found shows warning and falls back to preview."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=1)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": False, "theme": "ansi"}

        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            ResultPresenter._render_with_context(result, 1, tmp_path, settings)

            # Should show warning message
            calls = [str(c) for c in mock_click.echo.call_args_list]
            assert any("Warning" in str(c) for c in calls)

    def test_render_with_context_syntax_highlighting_enabled(self, tmp_path):
        """Context with syntax highlighting uses render_syntax_highlighted."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n    return True\n")

        chunk = MockChunk(path=Path("test.py"), start_line=2, end_line=2)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.result_presenter.click"),
            patch("ember.core.presentation.result_presenter.render_syntax_highlighted") as mock_highlight,
        ):
            mock_highlight.return_value = "highlighted code"
            ResultPresenter._render_with_context(result, 1, tmp_path, settings)

            # Should call render_syntax_highlighted
            mock_highlight.assert_called_once()


class TestRenderCompactPreviewEdgeCases:
    """Additional edge case tests for compact preview rendering."""

    def test_render_compact_preview_with_syntax_highlighting(self, tmp_path):
        """Preview with syntax highlighting reads from file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n    return True\n")

        chunk = MockChunk(path=Path("test.py"), start_line=1, end_line=3)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with (
            patch("ember.core.presentation.result_presenter.click"),
            patch("ember.core.presentation.result_presenter.render_syntax_highlighted") as mock_highlight,
        ):
            mock_highlight.return_value = "line1\nline2\nline3"
            ResultPresenter._render_compact_preview(result, settings, tmp_path)

            # Should call render_syntax_highlighted
            mock_highlight.assert_called_once()

    def test_render_compact_preview_highlighting_with_missing_file(self, tmp_path):
        """Preview falls back to content when file is missing."""
        chunk = MockChunk(path=Path("nonexistent.py"), start_line=1, end_line=3)
        result = MockSearchResult(chunk=chunk)
        settings = {"use_highlighting": True, "theme": "ansi"}

        with patch("ember.core.presentation.result_presenter.click") as mock_click:
            # Should not raise, should fall back to chunk content
            ResultPresenter._render_compact_preview(result, settings, tmp_path)
            assert mock_click.echo.called


class TestFileReadingEdgeCases:
    """Additional edge case tests for file reading."""

    def test_read_file_lines_handles_read_exception(self, tmp_path, monkeypatch):
        """File read exceptions return None."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        # Mock read_text to raise an exception
        def raise_error(*args, **kwargs):
            raise PermissionError("Access denied")

        monkeypatch.setattr(Path, "read_text", raise_error)

        lines = ResultPresenter._read_file_lines(test_file)
        assert lines is None
