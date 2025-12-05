"""JSON serialization and formatting for search results.

Handles all JSON-related output including cache serialization
and formatted JSON for CLI output.
"""

import json
from pathlib import Path
from typing import Any

from ember.ports.fs import FileSystem


class JsonResultFormatter:
    """Handles JSON serialization of search results.

    Separates JSON formatting concerns from other presentation logic.

    Args:
        fs: FileSystem port for reading file contents (needed for context).
    """

    def __init__(self, fs: FileSystem) -> None:
        """Initialize JsonResultFormatter with dependencies.

        Args:
            fs: FileSystem port for reading file contents.
        """
        self._fs = fs

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

    def format_output(
        self, results: list[Any], context: int = 0, repo_root: Path | None = None
    ) -> str:
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
                context_data = self._get_context(result, context, repo_root)
                if context_data:
                    item["context"] = context_data

            output.append(item)
        return json.dumps(output, indent=2)

    def _get_context(
        self, result: Any, context: int, repo_root: Path
    ) -> dict[str, Any] | None:
        """Get context lines for a search result.

        Args:
            result: SearchResult object.
            context: Number of lines of context.
            repo_root: Repository root path.

        Returns:
            Dictionary with context information, or None if file not readable.
        """
        file_path = repo_root / result.chunk.path
        file_lines = self._fs.read_text_lines(file_path)

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
