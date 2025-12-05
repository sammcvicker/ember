"""Result presentation orchestrator for search results.

Coordinates presentation logic by delegating to focused components:
- JsonResultFormatter: JSON serialization
- CompactPreviewRenderer: Compact previews without context
- ContextRenderer: Results with surrounding context
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

import click

from ember.core.presentation.colors import EmberColors
from ember.core.presentation.compact_renderer import CompactPreviewRenderer
from ember.core.presentation.context_renderer import ContextRenderer
from ember.core.presentation.json_formatter import JsonResultFormatter
from ember.ports.fs import FileSystem


class ResultPresenter:
    """Orchestrates presentation of search results in various formats.

    This is a thin coordinator that delegates to specialized renderers
    for different output modes (JSON, compact, with-context).

    Args:
        fs: FileSystem port for reading file contents.
    """

    def __init__(self, fs: FileSystem) -> None:
        """Initialize ResultPresenter with dependencies.

        Args:
            fs: FileSystem port for reading file contents.
        """
        self._fs = fs
        self._json_formatter = JsonResultFormatter(fs)
        self._compact_renderer = CompactPreviewRenderer(fs)
        self._context_renderer = ContextRenderer(fs)

    @staticmethod
    def serialize_for_cache(query: str, results: list[Any]) -> dict[str, Any]:
        """Serialize search results for caching.

        Delegates to JsonResultFormatter.

        Args:
            query: The search query.
            results: List of SearchResult objects.

        Returns:
            Dictionary suitable for JSON serialization and caching.
        """
        return JsonResultFormatter.serialize_for_cache(query, results)

    def format_json_output(
        self, results: list[Any], context: int = 0, repo_root: Path | None = None
    ) -> str:
        """Format results as JSON string.

        Delegates to JsonResultFormatter.

        Args:
            results: List of SearchResult objects.
            context: Number of lines of context to include (default: 0).
            repo_root: Repository root path for reading files (required if context > 0).

        Returns:
            JSON-formatted string.
        """
        return self._json_formatter.format_output(results, context, repo_root)

    def format_human_output(
        self,
        results: list[Any],
        context: int = 0,
        repo_root: Path | None = None,
        config: Any | None = None,
    ) -> None:
        """Format and print results in human-readable ripgrep-style format.

        Coordinates rendering by grouping results by file and delegating
        to appropriate renderers based on context setting.

        Args:
            results: List of SearchResult objects.
            context: Number of lines of context to show around each result (default: 0).
            repo_root: Repository root path for reading files (required if context > 0).
            config: EmberConfig object for display settings (optional).

        Note:
            This method prints directly to stdout using click.echo.
        """
        if not results:
            click.echo("No results found.")
            return

        results_by_file = self._group_results_by_file(results)
        settings = self._get_display_settings(config)

        for file_path, file_results in results_by_file.items():
            # Print filename using centralized color
            click.echo(EmberColors.click_path(str(file_path)))

            for i, result in enumerate(file_results):
                # Add blank line between results when using --context for readability
                if context > 0 and i > 0:
                    click.echo()

                if context > 0 and repo_root is not None:
                    self._context_renderer.render(result, context, repo_root, settings)
                else:
                    self._compact_renderer.render(result, settings, repo_root)

            # Blank line between files
            click.echo()

    @staticmethod
    def _get_display_settings(config: Any | None) -> dict[str, Any]:
        """Extract display settings from config.

        Args:
            config: EmberConfig object or None.

        Returns:
            Dictionary with 'use_highlighting' and 'theme' keys.
        """
        if config is not None and hasattr(config, "display"):
            return {
                "use_highlighting": config.display.syntax_highlighting,
                "theme": config.display.theme,
            }
        return {"use_highlighting": False, "theme": "ansi"}

    @staticmethod
    def _group_results_by_file(results: list[Any]) -> dict[Path, list[Any]]:
        """Group results by file path.

        Args:
            results: List of SearchResult objects.

        Returns:
            Dictionary mapping file paths to lists of results.
        """
        results_by_file = defaultdict(list)
        for result in results:
            results_by_file[result.chunk.path].append(result)
        return dict(results_by_file)

    # === Backward compatibility methods ===
    # These methods delegate to the extracted components but maintain
    # the original API for any code that might be using them directly.

    def _read_file_lines(self, file_path: Path) -> list[str] | None:
        """Read file and return lines.

        Args:
            file_path: Path to file to read.

        Returns:
            List of lines, or None if file doesn't exist or can't be read.
        """
        return self._fs.read_text_lines(file_path)

    @staticmethod
    def _safe_get_lines(file_lines: list[str], start: int, end: int) -> list[str]:
        """Safely extract lines from file content using 1-based line numbers.

        Delegates to CompactPreviewRenderer.

        Args:
            file_lines: List of file lines (0-indexed internally).
            start: Start line number (1-based, inclusive).
            end: End line number (1-based, inclusive).

        Returns:
            List of extracted lines. Empty list if range is invalid.
        """
        return CompactPreviewRenderer._safe_get_lines(file_lines, start, end)

    def _render_compact_preview(
        self,
        result: Any,
        settings: dict[str, Any],
        repo_root: Path | None,
    ) -> None:
        """Render a compact preview of a search result (no context).

        Delegates to CompactPreviewRenderer.

        Args:
            result: SearchResult object.
            settings: Display settings dict with 'use_highlighting' and 'theme'.
            repo_root: Repository root path for reading files.
        """
        self._compact_renderer.render(result, settings, repo_root)

    def _render_with_context(
        self,
        result: Any,
        context: int,
        repo_root: Path,
        settings: dict[str, Any],
    ) -> None:
        """Render a search result with surrounding context lines.

        Delegates to ContextRenderer.

        Args:
            result: SearchResult object.
            context: Number of lines of context around the match start line.
            repo_root: Repository root path.
            settings: Display settings dict with 'use_highlighting' and 'theme'.
        """
        self._context_renderer.render(result, context, repo_root, settings)

    def _get_context(
        self, result: Any, context: int, repo_root: Path
    ) -> dict[str, Any] | None:
        """Get context lines for a search result.

        Delegates to JsonResultFormatter.

        Args:
            result: SearchResult object.
            context: Number of lines of context.
            repo_root: Repository root path.

        Returns:
            Dictionary with context information, or None if file not readable.
        """
        return self._json_formatter._get_context(result, context, repo_root)
