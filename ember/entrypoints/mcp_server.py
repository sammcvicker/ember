"""Ember MCP server entrypoint.

Exposes Ember's codebase search capabilities via the Model Context Protocol (MCP).
Designed for use with AI agents (Claude, Cursor, Gemini, etc.).

Usage (MCP client config):
    {
      "ember": {
        "command": "ember",
        "args": ["mcp", "start"]
      }
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP(
    "ember",
    instructions=(
        "Ember provides semantic code search over local codebases. "
        "Use ember_search to find code by natural language query. "
        "Use ember_status to check index health. "
        "Use ember_cat to read the full content of a search result."
    ),
)


def _get_repo_context() -> tuple[Path, Path, Path]:
    """Get repo root, ember dir, and db path.

    Returns:
        Tuple of (repo_root, ember_dir, db_path).

    Raises:
        RuntimeError: If not in an ember-initialized repository.
    """
    from ember.core.repo_utils import find_repo_root

    repo_root, ember_dir = find_repo_root()
    db_path = ember_dir / "index.db"
    return repo_root, ember_dir, db_path


def _load_config(ember_dir: Path):
    """Load ember configuration.

    Args:
        ember_dir: Path to .ember directory.

    Returns:
        EmberConfig instance.
    """
    from ember.adapters.config.toml_config_provider import TomlConfigProvider

    return TomlConfigProvider().load(ember_dir)


def _create_search_deps(repo_root: Path, db_path: Path, config):
    """Create search dependencies (embedder + search use case).

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        config: EmberConfig instance.

    Returns:
        Initialized SearchUseCase.
    """
    from ember.adapters.fts.sqlite_fts import SQLiteFTS
    from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
    from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
    from ember.core.retrieval.search_usecase import SearchUseCase
    from ember.entrypoints.cli import _create_embedder

    text_search = SQLiteFTS(db_path)
    vector_search = SqliteVecAdapter(db_path)
    chunk_repo = SQLiteChunkRepository(db_path)
    embedder = _create_embedder(config, show_progress=False)

    return SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )


def _result_to_dict(result) -> dict:
    """Convert a SearchResult to a JSON-serializable dict.

    Args:
        result: SearchResult instance.

    Returns:
        Dictionary with result fields.
    """
    return {
        "rank": result.rank,
        "score": round(result.score, 6),
        "path": str(result.chunk.path),
        "symbol": result.chunk.symbol,
        "lang": result.chunk.lang,
        "start_line": result.chunk.start_line,
        "end_line": result.chunk.end_line,
        "content": result.chunk.content,
        "chunk_id": result.chunk.id,
    }


@mcp.tool()
def ember_search(
    query: str,
    topk: int = 20,
    path_filter: str | None = None,
    lang_filter: str | None = None,
) -> str:
    """Search the codebase for code matching a natural language query.

    Uses hybrid BM25 + semantic vector search with Reciprocal Rank Fusion.
    Automatically syncs the index if the working tree has changed.

    Args:
        query: Natural language search query (e.g. "database connection pooling").
        topk: Maximum number of results to return. Defaults to 20.
        path_filter: Optional glob to filter by file path (e.g. "src/**", "*.py").
        lang_filter: Optional language filter (e.g. "py", "ts", "go").

    Returns:
        JSON array of search results with path, line numbers, symbol, and content.
    """
    repo_root, ember_dir, db_path = _get_repo_context()
    config = _load_config(ember_dir)

    # Auto-sync index if stale (silent, no progress output)
    from ember.entrypoints.cli import ensure_synced

    ensure_synced(
        repo_root=repo_root,
        db_path=db_path,
        config=config,
        show_progress=False,
        verbose=False,
    )

    # Execute search
    from ember.domain.entities import Query

    search_usecase = _create_search_deps(repo_root, db_path, config)
    query_obj = Query(
        text=query,
        topk=topk,
        path_filter=path_filter,
        lang_filter=lang_filter,
    )
    results = search_usecase.search(query_obj)

    return json.dumps([_result_to_dict(r) for r in results], indent=2)


@mcp.tool()
def ember_status() -> str:
    """Get the current Ember index status and configuration.

    Returns index health, file counts, sync state, and active configuration.
    Run this to check if the index is initialized and up to date.

    Returns:
        JSON object with index status fields.
    """
    from ember.adapters.git_cmd.git_adapter import GitAdapter
    from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
    from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
    from ember.core.status.status_usecase import StatusRequest, StatusUseCase

    repo_root, ember_dir, db_path = _get_repo_context()
    config = _load_config(ember_dir)

    vcs = GitAdapter(repo_root)
    chunk_repo = SQLiteChunkRepository(db_path)
    meta_repo = SQLiteMetaRepository(db_path)

    use_case = StatusUseCase(
        vcs=vcs,
        chunk_repo=chunk_repo,
        meta_repo=meta_repo,
        config=config,
    )
    response = use_case.execute(StatusRequest(repo_root=repo_root))

    status_dict: dict = {
        "initialized": response.initialized,
        "repo_root": str(response.repo_root) if response.repo_root else None,
        "indexed_files": response.indexed_files,
        "total_chunks": response.total_chunks,
        "is_stale": response.is_stale,
        "last_tree_sha": response.last_tree_sha,
        "success": response.success,
    }

    if response.error:
        status_dict["error"] = response.error

    if response.config:
        status_dict["config"] = {
            "model": response.config.index.model,
            "chunk_strategy": response.config.index.chunk,
            "topk": response.config.search.topk,
        }

    if response.model_fingerprint:
        status_dict["model_fingerprint"] = response.model_fingerprint

    return json.dumps(status_dict, indent=2)


@mcp.tool()
def ember_cat(identifier: str) -> str:
    """Get the full content of a search result by index number or chunk hash.

    Use after ember_search to retrieve the complete code for a specific result.

    Args:
        identifier: Either a numeric index from recent search results (e.g. "1"),
            a full chunk ID (e.g. "blake3:a1b2c3d4..."), or a short hash prefix
            (minimum 8 characters).

    Returns:
        JSON object with the chunk's path, line range, symbol, language, and content.
    """
    from ember.core.cli_utils import (
        lookup_result_by_hash,
        lookup_result_from_cache,
    )

    _repo_root, ember_dir, db_path = _get_repo_context()

    if identifier.isdigit():
        cache_path = ember_dir / ".last_search.json"
        result = lookup_result_from_cache(identifier, cache_path)
    else:
        from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository

        chunk_repo = SQLiteChunkRepository(db_path)
        result = lookup_result_by_hash(identifier, chunk_repo)

    return json.dumps(
        {
            "path": result["path"],
            "symbol": result.get("symbol"),
            "lang": result.get("lang"),
            "start_line": result["start_line"],
            "end_line": result["end_line"],
            "content": result["content"],
            "chunk_id": result.get("id", result.get("chunk_id")),
        },
        indent=2,
    )


def run_server() -> None:
    """Run the Ember MCP server on stdio transport."""
    mcp.run(transport="stdio")
