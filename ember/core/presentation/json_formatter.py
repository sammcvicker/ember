"""JSON serialization and formatting for search results.

Handles all JSON-related output including cache serialization
and formatted JSON for CLI output.
"""

import json
from pathlib import Path
from typing import Any

from ember.core.presentation.context_utils import get_context_for_result
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
                    "explanation": result.explanation.to_dict(),
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
                "explanation": result.explanation.to_dict(),
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
        context_data = get_context_for_result(
            result=result,
            context_lines=context,
            repo_root=repo_root,
            fs=self._fs,
        )

        if context_data is None:
            return None

        return context_data.to_dict()
