"""Result presentation logic for search results.

Handles serialization and formatting of search results for different output modes.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import click

from ember.core.cli_utils import highlight_symbol


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
    def format_human_output(results: list[Any], context: int = 0, repo_root: Path | None = None) -> None:
        """Format and print results in human-readable ripgrep-style format.

        Args:
            results: List of SearchResult objects.
            context: Number of lines of context to show around each result (default: 0).
            repo_root: Repository root path for reading files (required if context > 0).

        Note:
            This method prints directly to stdout using click.echo.
        """
        if not results:
            click.echo("No results found.")
            return

        # Group results by file path for cleaner output
        results_by_file = defaultdict(list)
        for result in results:
            results_by_file[result.chunk.path].append(result)

        # Display grouped results
        for file_path, file_results in results_by_file.items():
            # Print filename in magenta
            click.echo(click.style(str(file_path), fg="magenta", bold=True))

            for result in file_results:
                # If context requested, show context with line numbers
                if context > 0 and repo_root is not None:
                    ResultPresenter._display_result_with_context(result, context, repo_root)
                else:
                    # Original format: [rank] line_number: content
                    # Rank in green (what users reference for cat/open)
                    rank = click.style(f"[{result.rank}]", fg="green", bold=True)
                    # Line number in dim gray (informational)
                    line_num = click.style(f"{result.chunk.start_line}", dim=True)

                    # Get preview content (first line only for compact display)
                    preview = result.preview or result.format_preview(max_lines=1)
                    content_lines = preview.split("\n")

                    # First line with rank and line number
                    if content_lines:
                        first_line = highlight_symbol(content_lines[0], result.chunk.symbol)
                        click.echo(f"{rank} {line_num}:{first_line}")

                        # Additional preview lines (indented, no line number)
                        for line in content_lines[1:]:
                            if line.strip():  # Skip empty lines
                                highlighted_line = highlight_symbol(line, result.chunk.symbol)
                                click.echo(f"    {highlighted_line}")

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
        if not file_path.exists():
            return None

        try:
            file_lines = file_path.read_text(errors="replace").splitlines()
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
        except Exception:
            return None

    @staticmethod
    def _display_result_with_context(result: Any, context: int, repo_root: Path) -> None:
        """Display a search result with surrounding context.

        Args:
            result: SearchResult object.
            context: Number of lines of context.
            repo_root: Repository root path.
        """
        # Show rank
        rank = click.style(f"[{result.rank}]", fg="green", bold=True)
        click.echo(rank)

        file_path = repo_root / result.chunk.path
        if not file_path.exists():
            # Fall back to preview if file not found
            click.echo(
                click.style("Warning: File not found, showing preview only", fg="yellow"),
            )
            preview = result.preview or result.format_preview(max_lines=5)
            click.echo(preview)
            return

        try:
            file_lines = file_path.read_text(errors="replace").splitlines()
            start_line = result.chunk.start_line
            end_line = result.chunk.end_line

            # Calculate context range (1-based line numbers)
            context_start = max(1, start_line - context)
            context_end = min(len(file_lines), end_line + context)

            # Display with line numbers (similar to cat --context)
            for line_num in range(context_start, context_end + 1):
                line_content = file_lines[line_num - 1]  # Convert to 0-based
                # Highlight the chunk lines, dim the context
                if start_line <= line_num <= end_line:
                    click.echo(f"{line_num:5} | {line_content}")
                else:
                    click.echo(click.style(f"{line_num:5} | {line_content}", dim=True))
        except Exception as e:
            # Fall back to preview if file read fails
            click.echo(
                click.style(f"Warning: Could not read file: {e}", fg="yellow"),
            )
            preview = result.preview or result.format_preview(max_lines=5)
            click.echo(preview)
