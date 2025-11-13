"""Unit tests for interactive search UI preview pane syntax highlighting.

Tests that the preview pane in InteractiveSearchUI applies syntax highlighting
using the render_syntax_highlighted() infrastructure when enabled via config.
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
