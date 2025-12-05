"""Compact preview rendering for search results.

Renders search results in a condensed format without surrounding context.
Shows 3-line previews with symbol-only highlighting (red bold for matches).
"""

from pathlib import Path
from typing import Any

import click

from ember.core.presentation.colors import (
    EmberColors,
    highlight_symbol,
)
from ember.ports.fs import FileSystem


class CompactPreviewRenderer:
    """Renders compact previews of search results.

    Shows a brief preview (up to 3 lines) of each result.
    Uses symbol-only highlighting (red bold) for fast scanning.

    Note:
        This renderer intentionally does NOT use syntax highlighting.
        The find command is for quickly locating symbols, so it uses
        red bold for matches only, with dim line numbers and regular text.

    Args:
        fs: FileSystem port for reading file contents.
    """

    MAX_PREVIEW_LINES = 3

    def __init__(self, fs: FileSystem) -> None:
        """Initialize CompactPreviewRenderer with dependencies.

        Args:
            fs: FileSystem port for reading file contents.
        """
        self._fs = fs

    def render(
        self,
        result: Any,
        settings: dict[str, Any],
        repo_root: Path | None,
    ) -> None:
        """Render a compact preview of a search result (no context).

        Uses plain rendering with symbol-only highlighting for fast scanning.
        The settings parameter is accepted for API compatibility but
        syntax highlighting is intentionally not applied.

        Args:
            result: SearchResult object.
            settings: Display settings dict (unused, kept for API compatibility).
            repo_root: Repository root path (unused, kept for API compatibility).
        """
        rank = EmberColors.click_rank(f"[{result.rank}]")
        line_num_str = EmberColors.click_line_number(f"{result.chunk.start_line}")

        # Always use plain preview with symbol-only highlighting
        # Syntax highlighting is intentionally disabled for find command
        self._render_plain_preview(
            result.chunk.content,
            result.chunk.symbol,
            rank,
            line_num_str,
        )

    @staticmethod
    def _safe_get_lines(file_lines: list[str], start: int, end: int) -> list[str]:
        """Safely extract lines from file content using 1-based line numbers.

        Args:
            file_lines: List of file lines (0-indexed internally).
            start: Start line number (1-based, inclusive).
            end: End line number (1-based, inclusive).

        Returns:
            List of extracted lines. Empty list if range is invalid.
        """
        if not file_lines:
            return []
        start = max(1, start)
        end = min(len(file_lines), end)
        if start > end:
            return []
        return file_lines[start - 1 : end]

    def _render_plain_preview(
        self,
        content: str,
        symbol: str | None,
        rank: str,
        line_num_str: str,
    ) -> None:
        """Render preview without syntax highlighting.

        Args:
            content: Chunk content to display.
            symbol: Symbol to highlight (if any).
            rank: Formatted rank string.
            line_num_str: Formatted line number string.
        """
        content_lines = content.split("\n")
        preview_lines = content_lines[: self.MAX_PREVIEW_LINES]

        if preview_lines:
            first_line = highlight_symbol(preview_lines[0], symbol)
            click.echo(f"{rank} {line_num_str}:{first_line}")

            for line in preview_lines[1:]:
                highlighted_line = highlight_symbol(line, symbol)
                click.echo(f"    {highlighted_line}")
