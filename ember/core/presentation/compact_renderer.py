"""Compact preview rendering for search results.

Renders search results in a condensed format without surrounding context.
Shows 3-line previews with syntax highlighting support.
"""

from pathlib import Path
from typing import Any

import click

from ember.core.presentation.colors import (
    EmberColors,
    highlight_symbol,
    render_syntax_highlighted,
)
from ember.ports.fs import FileSystem


class CompactPreviewRenderer:
    """Renders compact previews of search results.

    Shows a brief preview (up to 3 lines) of each result,
    with optional syntax highlighting.

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

        Args:
            result: SearchResult object.
            settings: Display settings dict with 'use_highlighting' and 'theme'.
            repo_root: Repository root path for reading files.
        """
        rank = EmberColors.click_rank(f"[{result.rank}]")
        line_num_str = EmberColors.click_line_number(f"{result.chunk.start_line}")

        # Try to get preview lines from file (for syntax highlighting)
        preview_lines: list[str] | None = None
        file_path: Path | None = None

        if settings["use_highlighting"] and repo_root is not None:
            file_path = repo_root / result.chunk.path
            file_lines = self._fs.read_text_lines(file_path)
            if file_lines is not None:
                end_line = min(
                    result.chunk.start_line + self.MAX_PREVIEW_LINES - 1,
                    result.chunk.end_line,
                )
                preview_lines = self._safe_get_lines(
                    file_lines, result.chunk.start_line, end_line
                )

        # Render with syntax highlighting if we have file content
        if preview_lines and file_path is not None:
            self._render_highlighted_preview(
                preview_lines,
                file_path,
                result.chunk.start_line,
                settings["theme"],
                rank,
                line_num_str,
            )
            return

        # Fallback: render from chunk content without highlighting
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

    def _render_highlighted_preview(
        self,
        preview_lines: list[str],
        file_path: Path,
        start_line: int,
        theme: str,
        rank: str,
        line_num_str: str,
    ) -> None:
        """Render preview with syntax highlighting.

        Args:
            preview_lines: Lines to render.
            file_path: Path for language detection.
            start_line: Starting line number for highlighting.
            theme: Syntax highlighting theme.
            rank: Formatted rank string.
            line_num_str: Formatted line number string.
        """
        code_block = "\n".join(preview_lines)
        highlighted = render_syntax_highlighted(
            code=code_block,
            file_path=file_path,
            start_line=start_line,
            theme=theme,
        )
        output_lines = highlighted.splitlines() if highlighted else preview_lines

        if output_lines:
            click.echo(f"{rank} {line_num_str}:{output_lines[0]}")
            for line in output_lines[1:]:
                click.echo(f"    {line}")

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
