"""Result presentation logic for search results.

Handles serialization and formatting of search results for different output modes.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import click

from ember.core.presentation.colors import EmberColors, highlight_symbol, render_syntax_highlighted


class ResultPresenter:
    """Handles presentation of search results in various formats.

    Separates business logic from presentation concerns by providing
    reusable formatters for JSON and human-readable output.
    """

    @staticmethod
    def serialize_for_cache(query: str, results: list[Any]) -> dict[str, Any]:
        """Serialize search results for caching.

        Args:
            query: The search query.
            results: List of SearchResult objects.

        Returns:
            Dictionary suitable for JSON serialization and caching.
        """
        return {
            "query": query,
            "results": [
                {
                    "rank": result.rank,
                    "score": result.score,
                    "path": str(result.chunk.path),
                    "lang": result.chunk.lang,
                    "symbol": result.chunk.symbol,
                    "start_line": result.chunk.start_line,
                    "end_line": result.chunk.end_line,
                    "content": result.chunk.content,
                    "chunk_id": result.chunk.id,
                    "tree_sha": result.chunk.tree_sha,
                    "explanation": result.explanation,
                }
                for result in results
            ],
        }

    @staticmethod
    def format_json_output(results: list[Any], context: int = 0, repo_root: Path | None = None) -> str:
        """Format results as JSON string.

        Args:
            results: List of SearchResult objects.
            context: Number of lines of context to include (default: 0).
            repo_root: Repository root path for reading files (required if context > 0).

        Returns:
            JSON-formatted string.
        """
        output = []
        for result in results:
            item = {
                "id": result.chunk.id,  # Stable hash ID for direct lookup
                "rank": result.rank,
                "score": result.score,
                "path": str(result.chunk.path),
                "lang": result.chunk.lang,
                "symbol": result.chunk.symbol,
                "start_line": result.chunk.start_line,
                "end_line": result.chunk.end_line,
                "content": result.chunk.content,
                "explanation": result.explanation,
            }

            # Add context if requested
            if context > 0 and repo_root is not None:
                context_data = ResultPresenter._get_context(
                    result, context, repo_root
                )
                if context_data:
                    item["context"] = context_data

            output.append(item)
        return json.dumps(output, indent=2)

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
    def _read_file_lines(file_path: Path) -> list[str] | None:
        """Read file and return lines.

        Args:
            file_path: Path to file to read.

        Returns:
            List of lines, or None if file doesn't exist or can't be read.
        """
        if not file_path.exists():
            return None
        try:
            return file_path.read_text(errors="replace").splitlines()
        except Exception:
            return None

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

    @staticmethod
    def _render_compact_preview(
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
        max_preview_lines = 3
        rank = EmberColors.click_rank(f"[{result.rank}]")
        line_num = EmberColors.click_line_number(f"{result.chunk.start_line}")

        # Try syntax highlighting if enabled
        if settings["use_highlighting"] and repo_root is not None:
            file_path = repo_root / result.chunk.path
            file_lines = ResultPresenter._read_file_lines(file_path)

            if file_lines is not None:
                start_line = result.chunk.start_line
                end_line = result.chunk.end_line

                # Get preview lines (first N lines of chunk)
                preview_lines = []
                for line_num_iter in range(start_line, min(start_line + max_preview_lines, end_line + 1, len(file_lines) + 1)):
                    if line_num_iter - 1 < len(file_lines):
                        preview_lines.append(file_lines[line_num_iter - 1])

                if preview_lines:
                    code_block = "\n".join(preview_lines)

                    # Apply syntax highlighting to preview
                    highlighted = render_syntax_highlighted(
                        code=code_block,
                        file_path=file_path,
                        start_line=start_line,
                        theme=settings["theme"],
                    )

                    # Show rank and line number with first line
                    highlighted_lines = highlighted.splitlines() if highlighted else code_block.splitlines()
                    if highlighted_lines:
                        click.echo(f"{rank} {line_num}:{highlighted_lines[0]}")

                        # Show remaining preview lines (indented)
                        for line in highlighted_lines[1:]:
                            click.echo(f"    {line}")
                    return

        # Fallback: use preview without syntax highlighting
        content_lines = result.chunk.content.split("\n")
        preview_lines = content_lines[:max_preview_lines]

        # First line with rank and line number
        if preview_lines:
            first_line = highlight_symbol(preview_lines[0], result.chunk.symbol)
            click.echo(f"{rank} {line_num}:{first_line}")

            # Additional preview lines (indented, no ellipses)
            for line in preview_lines[1:]:
                highlighted_line = highlight_symbol(line, result.chunk.symbol)
                click.echo(f"    {highlighted_line}")

    @staticmethod
    def _render_with_context(
        result: Any,
        context: int,
        repo_root: Path,
        settings: dict[str, Any],
    ) -> None:
        """Render a search result with surrounding context lines.

        Args:
            result: SearchResult object.
            context: Number of lines of context around the match start line.
            repo_root: Repository root path.
            settings: Display settings dict with 'use_highlighting' and 'theme'.
        """
        file_path = repo_root / result.chunk.path
        file_lines = ResultPresenter._read_file_lines(file_path)

        if file_lines is None:
            # Fall back to preview if file not found
            click.echo(EmberColors.click_warning("Warning: File not found, showing preview only"))
            preview = result.preview or result.format_preview(max_lines=5)
            click.echo(preview)
            return

        match_line = result.chunk.start_line  # The primary match line

        # Calculate context range around the MATCH LINE (not entire chunk)
        context_start = max(1, match_line - context)
        context_end = min(len(file_lines), match_line + context)

        if settings["use_highlighting"]:
            # With syntax highlighting: show all context lines with highlighting
            all_lines = []
            for line_num in range(context_start, context_end + 1):
                all_lines.append(file_lines[line_num - 1])

            code_block = "\n".join(all_lines)

            # Apply syntax highlighting with line numbers starting at context_start
            highlighted = render_syntax_highlighted(
                code=code_block,
                file_path=file_path,
                start_line=context_start,
                theme=settings["theme"],
            )

            # Add rank indicator before the highlighted output
            rank = EmberColors.click_rank(f"[{result.rank}]")
            click.echo(rank)
            click.echo(highlighted)
        else:
            # Compact ripgrep-style format without syntax highlighting
            rank = EmberColors.click_rank(f"[{result.rank}]")

            for line_num in range(context_start, context_end + 1):
                line_content = file_lines[line_num - 1]  # Convert to 0-based

                if line_num == match_line:
                    # Match line: show rank and line number with colon
                    line_num_str = EmberColors.click_line_number(str(line_num))
                    # Apply symbol highlighting if present
                    highlighted_content = highlight_symbol(line_content, result.chunk.symbol)
                    click.echo(f"{rank} {line_num_str}:{highlighted_content}")
                else:
                    # Context line: dimmed, with line number and colon, indented
                    line_num_str = EmberColors.click_line_number(str(line_num))
                    dimmed_content = EmberColors.click_dimmed(line_content)
                    click.echo(f"    {line_num_str}:{dimmed_content}")

    @staticmethod
    def format_human_output(results: list[Any], context: int = 0, repo_root: Path | None = None, config: Any | None = None) -> None:
        """Format and print results in human-readable ripgrep-style format.

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

        results_by_file = ResultPresenter._group_results_by_file(results)
        settings = ResultPresenter._get_display_settings(config)

        for file_path, file_results in results_by_file.items():
            # Print filename using centralized color
            click.echo(EmberColors.click_path(str(file_path)))

            for i, result in enumerate(file_results):
                # Add blank line between results when using --context for readability
                if context > 0 and i > 0:
                    click.echo()

                if context > 0 and repo_root is not None:
                    ResultPresenter._render_with_context(result, context, repo_root, settings)
                else:
                    ResultPresenter._render_compact_preview(result, settings, repo_root)

            # Blank line between files
            click.echo()

    @staticmethod
    def _get_context(result: Any, context: int, repo_root: Path) -> dict[str, Any] | None:
        """Get context lines for a search result.

        Args:
            result: SearchResult object.
            context: Number of lines of context.
            repo_root: Repository root path.

        Returns:
            Dictionary with context information, or None if file not readable.
        """
        file_path = repo_root / result.chunk.path
        file_lines = ResultPresenter._read_file_lines(file_path)

        if file_lines is None:
            return None

        start_line = result.chunk.start_line
        end_line = result.chunk.end_line

        # Calculate context range (1-based line numbers)
        context_start = max(1, start_line - context)
        context_end = min(len(file_lines), end_line + context)

        # Collect context lines
        before_lines = []
        chunk_lines = []
        after_lines = []

        for line_num in range(context_start, context_end + 1):
            line_content = file_lines[line_num - 1]  # Convert to 0-based
            if line_num < start_line:
                before_lines.append({"line": line_num, "content": line_content})
            elif line_num > end_line:
                after_lines.append({"line": line_num, "content": line_content})
            else:
                chunk_lines.append({"line": line_num, "content": line_content})

        return {
            "before": before_lines,
            "chunk": chunk_lines,
            "after": after_lines,
            "start_line": context_start,
            "end_line": context_end,
        }
