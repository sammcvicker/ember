"""Context rendering for search results.

Renders search results with surrounding context lines,
similar to ripgrep's context display.
"""

from pathlib import Path
from typing import Any

import click

from ember.core.presentation.colors import (
    EmberColors,
    highlight_symbol,
)
from ember.ports.fs import FileSystem


class ContextRenderer:
    """Renders search results with surrounding context.

    Shows the match line with configurable lines of context
    before and after. Uses symbol-only highlighting (red bold) for fast scanning.

    Note:
        This renderer intentionally does NOT use syntax highlighting.
        The find command is for quickly locating symbols, so it uses
        red bold for matches only, with dim line numbers and regular text.

    Args:
        fs: FileSystem port for reading file contents.
    """

    def __init__(self, fs: FileSystem) -> None:
        """Initialize ContextRenderer with dependencies.

        Args:
            fs: FileSystem port for reading file contents.
        """
        self._fs = fs

    def render(
        self,
        result: Any,
        context: int,
        repo_root: Path,
        settings: dict[str, Any],
    ) -> None:
        """Render a search result with surrounding context lines.

        Uses plain rendering with symbol-only highlighting for fast scanning.
        The settings parameter is accepted for API compatibility but
        syntax highlighting is intentionally not applied.

        Args:
            result: SearchResult object.
            context: Number of lines of context around the match start line.
            repo_root: Repository root path.
            settings: Display settings dict (unused, kept for API compatibility).
        """
        file_path = repo_root / result.chunk.path
        file_lines = self._fs.read_text_lines(file_path)

        if file_lines is None:
            # Fall back to preview if file not found
            click.echo(
                EmberColors.click_warning("Warning: File not found, showing preview only")
            )
            preview = result.preview or result.format_preview(max_lines=5)
            click.echo(preview)
            return

        match_line = result.chunk.start_line  # The primary match line

        # Calculate context range around the MATCH LINE (not entire chunk)
        context_start = max(1, match_line - context)
        context_end = min(len(file_lines), match_line + context)

        # Always use plain rendering with symbol-only highlighting
        # Syntax highlighting is intentionally disabled for find command
        self._render_plain_context(
            file_lines, context_start, context_end, match_line, result.rank, result.chunk.symbol
        )

    def _render_plain_context(
        self,
        file_lines: list[str],
        context_start: int,
        context_end: int,
        match_line: int,
        rank: int,
        symbol: str | None,
    ) -> None:
        """Render context without syntax highlighting.

        Uses compact ripgrep-style format with dimmed context lines.

        Args:
            file_lines: All lines from the file.
            context_start: First line to display (1-based).
            context_end: Last line to display (1-based).
            match_line: The primary match line (1-based).
            rank: Result rank for display.
            symbol: Symbol to highlight (if any).
        """
        rank_str = EmberColors.click_rank(f"[{rank}]")

        for line_num in range(context_start, context_end + 1):
            line_content = file_lines[line_num - 1]  # Convert to 0-based

            if line_num == match_line:
                # Match line: show rank and line number with colon
                line_num_str = EmberColors.click_line_number(str(line_num))
                # Apply symbol highlighting if present
                highlighted_content = highlight_symbol(line_content, symbol)
                click.echo(f"{rank_str} {line_num_str}:{highlighted_content}")
            else:
                # Context line: dimmed, with line number and colon, indented
                line_num_str = EmberColors.click_line_number(str(line_num))
                dimmed_content = EmberColors.click_dimmed(line_content)
                click.echo(f"    {line_num_str}:{dimmed_content}")
