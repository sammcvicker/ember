"""Result lookup utilities for CLI commands.

Handles loading cached search results and looking up chunks by index or hash.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ember.core.errors import (
    EmberCliError,
    index_out_of_range_error,
    no_search_results_error,
)

if TYPE_CHECKING:
    from ember.domain.entities import Chunk
    from ember.ports.chunk_repository import ChunkRepository


def load_cached_results(cache_path: Path) -> dict[str, Any]:
    """Load cached search results from JSON file.

    Args:
        cache_path: Path to .last_search.json cache file.

    Returns:
        Dictionary with 'query' and 'results' keys.

    Raises:
        EmberCliError: If cache doesn't exist, is corrupted, or empty.
    """
    # Check if cache exists
    if not cache_path.exists():
        no_search_results_error()

    try:
        cache_data = json.loads(cache_path.read_text())
        results = cache_data.get("results", [])

        if not results:
            raise EmberCliError(
                "No results in cache",
                hint="Run 'ember find <query>' to search your codebase",
            )

        return cache_data

    except json.JSONDecodeError as e:
        raise EmberCliError(
            "Corrupted search cache",
            hint="Run 'ember find <query>' to refresh the cache",
        ) from e


def validate_result_index(index: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate result index and return the corresponding result.

    Args:
        index: 1-based index from user.
        results: List of result dictionaries.

    Returns:
        The result dictionary at the given index.

    Raises:
        EmberCliError: If index is out of range.
    """
    # Validate index (1-based)
    if index < 1 or index > len(results):
        index_out_of_range_error(index, len(results))

    # Get the result (convert to 0-based)
    return results[index - 1]


def lookup_result_from_cache(
    identifier: str, cache_path: Path
) -> dict[str, Any]:
    """Look up a result from the search cache by numeric index.

    Args:
        identifier: Numeric string index (1-based).
        cache_path: Path to .last_search.json cache file.

    Returns:
        Result dictionary with path, start_line, end_line, content, lang, symbol.

    Raises:
        SystemExit: If cache doesn't exist, is corrupted, or index is out of range.
    """
    cache_data = load_cached_results(cache_path)
    results = cache_data.get("results", [])
    return validate_result_index(int(identifier), results)


def lookup_result_by_hash(
    identifier: str, chunk_repo: "ChunkRepository"
) -> dict[str, Any]:
    """Look up a result by chunk ID hash prefix.

    Args:
        identifier: Hash prefix (or full hash) to search for.
        chunk_repo: Repository for chunk lookups.

    Returns:
        Result dictionary with path, start_line, end_line, content, lang, symbol.

    Raises:
        EmberCliError: If no chunk found or multiple chunks match the prefix.
    """
    matches: list[Chunk] = chunk_repo.find_by_id_prefix(identifier)

    if len(matches) == 0:
        raise EmberCliError(
            f"No chunk found with ID prefix '{identifier}'",
            hint="Use 'ember find <query>' to search and get valid chunk IDs",
        )
    elif len(matches) > 1:
        # Build list of matching IDs for context
        match_list = "\n".join(f"  {chunk.id}" for chunk in matches[:5])
        if len(matches) > 5:
            match_list += f"\n  ... and {len(matches) - 5} more"
        raise EmberCliError(
            f"Ambiguous chunk ID prefix '{identifier}' matches {len(matches)} chunks:\n{match_list}",
            hint="Use a longer prefix to uniquely identify the chunk",
        )

    # Found exactly one match - convert to result format
    chunk = matches[0]
    return {
        "path": str(chunk.path),
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "content": chunk.content,
        "lang": chunk.lang,
        "symbol": chunk.symbol,
    }
