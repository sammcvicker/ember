"""Unit tests for interactive search UI.

Tests for:
- Preview pane syntax highlighting
- Error handling when search functions fail
"""

from pathlib import Path

import pytest

from ember.adapters.tui.search_ui import InteractiveSearchUI
from ember.core.retrieval.interactive import InteractiveSearchSession
from ember.domain.config import DisplayConfig, EmberConfig
from ember.domain.entities import Chunk, Query, SearchResult


@pytest.fixture
def mock_config() -> EmberConfig:
    """Create a mock config with syntax highlighting enabled."""
    return EmberConfig.default()


@pytest.fixture
def mock_config_no_highlighting() -> EmberConfig:
    """Create a mock config with syntax highlighting disabled."""
    config = EmberConfig.default()
    # Create new config with syntax_highlighting disabled
    return EmberConfig(
        index=config.index,
        search=config.search,
        redaction=config.redaction,
        model=config.model,
        display=DisplayConfig(
            syntax_highlighting=False,
            color_scheme=config.display.color_scheme,
            theme=config.display.theme,
        ),
    )


@pytest.fixture
def sample_python_chunk() -> Chunk:
    """Create a sample Python code chunk for testing."""
    from pathlib import Path
    content = '''def calculate_sum(a, b):
    """Calculate the sum of two numbers."""
    result = a + b
    return result'''
    return Chunk(
        id="test_chunk_1",
        project_id="test_project",
        path=Path("example.py"),
        lang="py",
        symbol="calculate_sum",
        start_line=1,
        end_line=4,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash="file_hash_123",
        tree_sha="abc123",
        rev="worktree",
    )


@pytest.fixture
def sample_search_result(sample_python_chunk: Chunk) -> SearchResult:
    """Create a sample search result for testing."""
    return SearchResult(
        chunk=sample_python_chunk,
        score=0.95,
        rank=1,
    )


class TestInteractiveSearchUIPreviewHighlighting:
    """Tests for syntax highlighting in the interactive search preview pane."""

    def test_get_preview_text_applies_highlighting_when_enabled(
        self, mock_config: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that _get_preview_text applies syntax highlighting when config enables it."""
        # Create mock search function
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        # Create UI with config
        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
            show_preview=True,
        )

        # Set up session with a result
        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0

        # Get preview text
        preview_text = ui._get_preview_text()

        # Verify it's a list of tuples (style, text)
        assert isinstance(preview_text, list)
        assert len(preview_text) > 0

        # When syntax highlighting is enabled, we should get ANSI formatted text
        # ANSI() converts ANSI escape codes to formatted text tuples
        # The result should be a list of (style, text) tuples
        assert len(preview_text) > 0
        # Verify we got formatted text (list of tuples)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in preview_text)

    def test_get_preview_text_respects_syntax_highlighting_disabled(
        self, mock_config_no_highlighting: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that _get_preview_text respects config when syntax highlighting is disabled."""
        # Create mock search function
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        # Create UI with config that has highlighting disabled
        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config_no_highlighting,
            initial_query="test",
            show_preview=True,
        )

        # Set up session with a result
        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0

        # Get preview text
        preview_text = ui._get_preview_text()

        # Verify it returns formatted text
        assert isinstance(preview_text, list)
        assert len(preview_text) > 0

        # Should still have line numbers and content
        full_text = "".join(text for _, text in preview_text)
        assert "calculate_sum" in full_text
        # Should have line numbers in plain format (N │ content)
        assert "│" in full_text

    def test_get_preview_text_handles_empty_results(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that _get_preview_text handles empty results gracefully."""
        # Create mock search function
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return []

        # Create UI
        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
            show_preview=True,
        )

        # Get preview text with no results
        preview_text = ui._get_preview_text()

        # Should return empty or placeholder text
        assert isinstance(preview_text, list)

    def test_get_preview_text_detects_language_from_file_path(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that preview text uses file extension for language detection."""
        # Create a TypeScript chunk
        content = '''interface User {
    name: string;
    age: number;
}'''
        ts_chunk = Chunk(
            id="test_chunk_ts",
            project_id="test_project",
            path=Path("app.ts"),
            lang="ts",
            symbol="User",
            start_line=1,
            end_line=4,
            content=content,
            content_hash=Chunk.compute_content_hash(content),
            file_hash="file_hash_456",
            tree_sha="def456",
            rev="worktree",
        )
        ts_result = SearchResult(chunk=ts_chunk, score=0.90, rank=1)

        # Create mock search function
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [ts_result]

        # Create UI
        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="interface",
            show_preview=True,
        )

        # Set up session
        ui.session = InteractiveSearchSession(query_text="interface", preview_visible=True)
        ui.session.update_results([ts_result], 10.0)
        ui.session.selected_index = 0

        # Get preview text - should detect TypeScript and apply highlighting
        preview_text = ui._get_preview_text()

        assert isinstance(preview_text, list)
        assert len(preview_text) > 0

        # With highlighting enabled, should have formatted text tuples
        assert len(preview_text) > 0
        # Verify we got formatted text (list of tuples)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in preview_text)

    def test_get_preview_text_uses_configured_theme(
        self, sample_search_result: SearchResult
    ) -> None:
        """Test that preview text respects the configured theme."""
        # Create config with custom theme
        config = EmberConfig(
            display=DisplayConfig(
                syntax_highlighting=True,
                color_scheme="always",
                theme="monokai",
            )
        )

        # Create mock search function
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        # Create UI
        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=config,
            initial_query="test",
            show_preview=True,
        )

        # Set up session
        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0

        # Get preview text
        preview_text = ui._get_preview_text()

        assert isinstance(preview_text, list)
        assert len(preview_text) > 0

        # With custom theme, should still have formatted text tuples
        assert len(preview_text) > 0
        # Verify we got formatted text (list of tuples)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in preview_text)


class TestInteractiveSearchSession:
    """Tests for InteractiveSearchSession error handling."""

    def test_set_error_stores_message(self) -> None:
        """Test that set_error stores the error message."""
        session = InteractiveSearchSession(query_text="test")
        session.set_error("Connection failed")

        assert session.error_message == "Connection failed"

    def test_set_error_clears_results(self) -> None:
        """Test that set_error clears any existing results."""
        session = InteractiveSearchSession(query_text="test")
        # First add some results
        chunk = Chunk(
            id="test",
            project_id="test",
            path=Path("test.py"),
            lang="py",
            symbol=None,
            start_line=1,
            end_line=5,
            content="test content",
            content_hash=Chunk.compute_content_hash("test content"),
            file_hash="test_hash",
            tree_sha="abc123",
            rev="worktree",
        )
        session.update_results([SearchResult(chunk=chunk, score=0.9, rank=1)], 100.0)
        assert session.current_results is not None
        assert len(session.current_results) == 1

        # Then set an error
        session.set_error("Something went wrong")

        assert session.current_results == []
        assert session.last_search_time_ms == 0.0

    def test_update_results_clears_error(self) -> None:
        """Test that update_results clears any existing error."""
        session = InteractiveSearchSession(query_text="test")
        session.set_error("Previous error")
        assert session.error_message == "Previous error"

        # Then update results
        session.update_results([], 50.0)

        assert session.error_message is None


class TestInteractiveSearchUIErrorHandling:
    """Tests for error handling in the interactive search UI."""

    def test_get_error_text_returns_formatted_error(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that _get_error_text returns formatted error message."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return []

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test query",
        )

        # Set an error on the session
        ui.session.set_error("Search error: daemon connection failed")

        # Get error text from dedicated method
        error_text = ui._get_error_text()

        # Should show error message with error style
        assert len(error_text) == 1
        style, text = error_text[0]
        assert style == "class:error"
        assert "Search error: daemon connection failed" in text

    def test_get_error_text_returns_empty_when_no_error(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that _get_error_text returns empty when no error exists."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return []

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test query",
        )

        # No error set
        error_text = ui._get_error_text()

        # Should return empty
        assert error_text == [("", "")]

    def test_get_results_text_does_not_show_error_message(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that _get_results_text does not display error (handled separately)."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return []

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test query",
        )

        # Set an error on the session
        ui.session.set_error("Search error: daemon connection failed")

        # Get results text - should not include error (handled by _get_error_text)
        results_text = ui._get_results_text()

        # Should show empty or no results message, not the error
        assert len(results_text) == 1
        style, text = results_text[0]
        # Error messages are now shown in a separate window
        assert "Search error" not in text

    def test_get_results_text_shows_no_results_when_no_error(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that _get_results_text shows 'No results found' when no error."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return []

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test query",
        )

        # No error set, but empty results
        ui.session.update_results([], 10.0)

        # Get results text
        results_text = ui._get_results_text()

        # Should show "No results found"
        assert len(results_text) == 1
        style, text = results_text[0]
        assert style == ""
        assert "No results found" in text

    def test_error_message_in_separate_window(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that error message is shown in error window, not results window."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return []

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test query",
        )

        # Set error (which clears results)
        ui.session.set_error("Database error")

        # Error is in error window, not results window
        error_text = ui._get_error_text()
        assert len(error_text) == 1
        style, text = error_text[0]
        assert "Database error" in text
        assert style == "class:error"

        # Results window should be empty when error exists
        results_text = ui._get_results_text()
        assert len(results_text) == 1
        style, text = results_text[0]
        assert "No results found" not in text


class TestInteractiveSearchUIResultsListColorSeparation:
    """Tests for color separation in the results list.

    Issue #208: Add clear color coding to results list for better scannability.
    - Red bold for matched symbol name
    - Magenta for file paths
    - Dim for secondary info (scores, line ranges)
    """

    def test_results_list_has_symbol_styling(
        self, mock_config: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that symbol names have class:symbol styling."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
        )

        # Set up session with a result that has a symbol
        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0

        results_text = ui._get_results_text()

        # Should have multiple styled segments
        assert len(results_text) > 1

        # Find the symbol segment - should have class:symbol styling
        symbol_segments = [
            (style, text) for style, text in results_text
            if "symbol" in style and "calculate_sum" in text
        ]
        assert len(symbol_segments) == 1, "Symbol should be styled with class:symbol"

    def test_results_list_has_path_styling(
        self, mock_config: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that file paths have class:path styling."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
        )

        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0

        results_text = ui._get_results_text()

        # Find the path segment - should have class:path styling
        path_segments = [
            (style, text) for style, text in results_text
            if "path" in style and "example.py" in text
        ]
        assert len(path_segments) == 1, "Path should be styled with class:path"

    def test_results_list_has_line_number_styling(
        self, mock_config: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that line ranges have class:line-number styling (matches ember cat)."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
        )

        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0

        results_text = ui._get_results_text()

        # Find the line range segment - should have class:line-number styling
        # Line range is ":1-4" for this chunk
        line_range_segments = [
            (style, text) for style, text in results_text
            if "line-number" in style and ":1-4" in text
        ]
        assert len(line_range_segments) == 1, "Line range should be styled with class:line-number"

    def test_results_list_selected_item_has_underline(
        self, mock_config: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that selected item has underline styling on colored segments."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
        )

        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0  # First item is selected

        results_text = ui._get_results_text()

        # Find the underlined segments - selected items should have underline
        underlined_segments = [
            (style, text) for style, text in results_text
            if "underline" in style
        ]
        assert len(underlined_segments) > 0, "Selected item should have underline styling"

        # Verify symbol has underline
        underlined_symbol = [
            (style, text) for style, text in results_text
            if "underline" in style and "symbol" in style and "calculate_sum" in text
        ]
        assert len(underlined_symbol) == 1, "Selected symbol should have underline"

    def test_results_list_unselected_item_no_underline(
        self, mock_config: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that unselected items don't have underline styling."""
        # Create a second result
        content2 = "def another_func(): pass"
        chunk2 = Chunk(
            id="test_chunk_2",
            project_id="test_project",
            path=Path("other.py"),
            lang="py",
            symbol="another_func",
            start_line=10,
            end_line=10,
            content=content2,
            content_hash=Chunk.compute_content_hash(content2),
            file_hash="file_hash_789",
            tree_sha="xyz789",
            rev="worktree",
        )
        result2 = SearchResult(chunk=chunk2, score=0.85, rank=2)

        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result, result2]

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
        )

        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result, result2], 10.0)
        ui.session.selected_index = 0  # First item selected, second is not

        results_text = ui._get_results_text()

        # Find segments for "other.py" (unselected item)
        unselected_path_segments = [
            (style, text) for style, text in results_text
            if "other.py" in text
        ]
        assert len(unselected_path_segments) == 1
        style, _ = unselected_path_segments[0]
        # Should have path styling but NOT underline
        assert "path" in style, "Unselected path should have class:path"
        assert "underline" not in style, "Unselected item should not have underline"

    def test_results_list_handles_result_without_symbol(
        self, mock_config: EmberConfig
    ) -> None:
        """Test that results without symbols don't show symbol styling."""
        content = "# Just a comment"
        chunk = Chunk(
            id="test_chunk_no_symbol",
            project_id="test_project",
            path=Path("utils.py"),
            lang="py",
            symbol=None,  # No symbol
            start_line=1,
            end_line=1,
            content=content,
            content_hash=Chunk.compute_content_hash(content),
            file_hash="file_hash_nosym",
            tree_sha="nosym123",
            rev="worktree",
        )
        result = SearchResult(chunk=chunk, score=0.75, rank=1)

        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [result]

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
        )

        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([result], 10.0)
        ui.session.selected_index = 0

        results_text = ui._get_results_text()

        # Should still have path styling
        path_segments = [
            (style, text) for style, text in results_text
            if "path" in style and "utils.py" in text
        ]
        assert len(path_segments) == 1, "Path should still be styled"

        # Should NOT have any symbol styling (since no symbol)
        symbol_segments = [
            (style, text) for style, text in results_text
            if "symbol" in style
        ]
        assert len(symbol_segments) == 0, "No symbol styling when symbol is None"

    def test_results_list_does_not_show_scores(
        self, mock_config: EmberConfig, sample_search_result: SearchResult
    ) -> None:
        """Test that scores are not shown in the results list."""
        def mock_search_fn(query: Query) -> list[SearchResult]:
            return [sample_search_result]

        ui = InteractiveSearchUI(
            search_fn=mock_search_fn,
            config=mock_config,
            initial_query="test",
        )

        ui.session = InteractiveSearchSession(query_text="test", preview_visible=True)
        ui.session.update_results([sample_search_result], 10.0)
        ui.session.selected_index = 0

        results_text = ui._get_results_text()

        # Full text should not contain score values
        full_text = "".join(text for _, text in results_text)
        assert "0.950" not in full_text, "Score value should not appear in results list"
