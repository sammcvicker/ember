"""Result presentation logic for search results.

Handles serialization and formatting of search results for different output modes.
"""

import json
from collections import defaultdict
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
    def format_json_output(results: list[Any]) -> str:
        """Format results as JSON string.

        Args:
            results: List of SearchResult objects.

        Returns:
            JSON-formatted string.
        """
        output = []
        for result in results:
            output.append(
                {
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
            )
        return json.dumps(output, indent=2)

    @staticmethod
    def format_human_output(results: list[Any]) -> None:
        """Format and print results in human-readable ripgrep-style format.

        Args:
            results: List of SearchResult objects.

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
                # Format: [rank] line_number: content
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
