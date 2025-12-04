"""Ember CLI entrypoint.

Command-line interface for Ember code search tool.
"""

import functools
import sys
from pathlib import Path

import blake3
import click

from ember.adapters.fs.local import LocalFileSystem
from ember.core.cli_utils import (
    display_content_with_context,
    display_content_with_highlighting,
    format_result_header,
    load_cached_results,
    lookup_result_by_hash,
    lookup_result_from_cache,
    open_file_in_editor,
    progress_context,
    validate_result_index,
)
from ember.core.presentation import ResultPresenter


def handle_cli_errors(command_name: str):
    """Decorator to handle common CLI errors.

    Catches RuntimeError and Exception, displaying appropriate messages
    and showing tracebacks in verbose mode.

    Args:
        command_name: Name of the command for error messages.

    Returns:
        Decorated function with error handling.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except RuntimeError as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)
            except Exception as e:
                ctx = click.get_current_context()
                click.echo(f"Unexpected error in {command_name}: {e}", err=True)
                if ctx.obj.get("verbose", False):
                    import traceback

                    traceback.print_exc()
                sys.exit(1)

        return wrapper

    return decorator


def _create_embedder(config, show_progress: bool = True):
    """Create embedder based on configuration.

    Args:
        config: EmberConfig with model settings
        show_progress: Show progress bar during daemon startup

    Returns:
        Embedder instance (daemon client or direct)

    Raises:
        RuntimeError: If daemon fails to start
    """
    if config.model.mode == "daemon":
        # Use daemon mode (default)
        from ember.adapters.daemon.client import DaemonEmbedderClient
        from ember.adapters.daemon.lifecycle import DaemonLifecycle
        from ember.core.cli_utils import ensure_daemon_with_progress

        # ALWAYS pre-start daemon before returning client
        # This ensures errors are caught before TUI initialization (#126)
        daemon_manager = DaemonLifecycle(idle_timeout=config.model.daemon_timeout)

        # If daemon is already running, nothing to do
        if not daemon_manager.is_running():
            # Use progress UI if requested, otherwise start silently
            if show_progress:
                ensure_daemon_with_progress(daemon_manager, quiet=False)
            else:
                # Start daemon without progress UI
                # Let RuntimeError propagate to show clean error before TUI starts
                daemon_manager.start(foreground=False)

        return DaemonEmbedderClient(
            fallback=True,
            auto_start=False,  # Daemon already started above
            daemon_timeout=config.model.daemon_timeout,
        )
    else:
        # Use direct mode (fallback or explicit config)
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        return JinaCodeEmbedder()


def get_ember_repo_root() -> tuple[Path, Path]:
    """Get ember repository root or exit with error.

    Finds the ember repository root and .ember directory from the current
    working directory. If not in an ember repository, prints an error
    message and exits with code 1.

    Returns:
        Tuple of (repo_root, ember_dir) where:
        - repo_root: Absolute path to repository root
        - ember_dir: Absolute path to .ember/ directory
    """
    from ember.core.repo_utils import find_repo_root

    try:
        return find_repo_root()
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _create_indexing_usecase(repo_root: Path, db_path: Path, config):
    """Create IndexingUseCase with all dependencies.

    Helper function to avoid code duplication between sync command and auto-sync.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        config: Configuration object with index settings.

    Returns:
        Initialized IndexingUseCase instance.
    """
    # Lazy imports - only load heavy dependencies when needed
    from ember.adapters.fs.local import LocalFileSystem
    from ember.adapters.git_cmd.git_adapter import GitAdapter
    from ember.adapters.parsers.line_chunker import LineChunker
    from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
    from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
    from ember.adapters.sqlite.file_repository import SQLiteFileRepository
    from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
    from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
    from ember.core.chunking.chunk_usecase import ChunkFileUseCase
    from ember.core.indexing.index_usecase import IndexingUseCase

    # Initialize dependencies
    vcs = GitAdapter(repo_root)
    fs = LocalFileSystem()
    embedder = _create_embedder(config)

    # Initialize repositories
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path, expected_dim=embedder.dim)
    file_repo = SQLiteFileRepository(db_path)
    meta_repo = SQLiteMetaRepository(db_path)

    # Initialize chunking use case with config settings
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker(
        window_size=config.index.line_window,
        stride=config.index.line_stride,
    )
    chunk_usecase = ChunkFileUseCase(tree_sitter, line_chunker)

    # Compute project ID (hash of repo root path)
    project_id = blake3.blake3(str(repo_root).encode("utf-8")).hexdigest()

    # Create and return indexing use case
    return IndexingUseCase(
        vcs=vcs,
        fs=fs,
        chunk_usecase=chunk_usecase,
        embedder=embedder,
        chunk_repo=chunk_repo,
        vector_repo=vector_repo,
        file_repo=file_repo,
        meta_repo=meta_repo,
        project_id=project_id,
    )


def check_and_auto_sync(
    repo_root: Path,
    db_path: Path,
    config,
    quiet_mode: bool = False,
    verbose: bool = False,
) -> None:
    """Check if index is stale and auto-sync if needed.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        config: Configuration object.
        quiet_mode: If True, suppress progress and messages.
        verbose: If True, show warnings on errors.

    Note:
        If staleness check fails, continues silently to allow search to proceed.
    """
    try:
        # Import dependencies
        from ember.adapters.git_cmd.git_adapter import GitAdapter
        from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
        from ember.core.indexing.index_usecase import IndexRequest

        vcs = GitAdapter(repo_root)
        meta_repo = SQLiteMetaRepository(db_path)

        # Get current worktree tree SHA
        current_tree_sha = vcs.get_worktree_tree_sha()

        # Get last indexed tree SHA
        last_tree_sha = meta_repo.get("last_tree_sha")

        # If tree SHAs differ, index is stale - auto-sync
        if last_tree_sha != current_tree_sha:
            # Create indexing use case with all dependencies
            indexing_usecase = _create_indexing_usecase(repo_root, db_path, config)

            # Execute incremental sync
            request = IndexRequest(
                repo_root=repo_root,
                sync_mode="worktree",
                path_filters=[],
                force_reindex=False,
            )

            # Use progress bars unless in quiet mode
            from ember.core.cli_utils import progress_context

            with progress_context(quiet_mode=quiet_mode) as progress:
                if progress:
                    response = indexing_usecase.execute(request, progress=progress)
                else:
                    # Silent mode
                    response = indexing_usecase.execute(request)

            # Show completion message AFTER progress context exits (ensures progress bar is cleared)
            if not quiet_mode and response.success:
                if response.files_indexed > 0:
                    click.echo(
                        f"✓ Synced {response.files_indexed} file(s)",
                        err=True,
                    )
                else:
                    click.echo("✓ Index up to date", err=True)

    except Exception as e:
        # If staleness check fails, continue with search anyway
        if verbose:
            click.echo(f"Warning: Could not check index staleness: {e}", err=True)


@click.group()
@click.version_option(version="1.1.0", prog_name="ember")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress non-essential output.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool) -> None:
    """Ember - Local codebase embedding and search.

    Fast, deterministic semantic code search powered by embeddings.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet


@cli.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Reinitialize even if .ember/ already exists.",
)
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """Initialize Ember in the current directory.

    Creates .ember/ directory with configuration and database.
    If in a git repository, initializes at the git root.
    """
    # Lazy import - only load when init is actually called
    from ember.adapters.sqlite.initializer import SqliteDatabaseInitializer
    from ember.core.config.init_usecase import InitRequest, InitUseCase
    from ember.core.repo_utils import find_repo_root_for_init

    repo_root = find_repo_root_for_init()

    # Create use case with injected dependencies
    db_initializer = SqliteDatabaseInitializer()
    use_case = InitUseCase(db_initializer=db_initializer, version="1.1.0")
    request = InitRequest(repo_root=repo_root, force=force)

    try:
        response = use_case.execute(request)

        # Report success
        if response.was_reinitialized:
            click.echo(f"Reinitialized existing ember index at {response.ember_dir}")
        else:
            click.echo(f"Initialized ember index at {response.ember_dir}")

        if not ctx.obj.get("quiet", False):
            click.echo(f"  ✓ Created {response.config_path.name}")
            click.echo(f"  ✓ Created {response.db_path.name}")
            click.echo(f"  ✓ Created {response.state_path.name}")
            click.echo("\nNext: Run 'ember sync' to index your codebase")

    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Use 'ember init --force' to reinitialize", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error initializing ember: {e}", err=True)
        sys.exit(1)


def _parse_sync_mode(rev: str | None, staged: bool, worktree: bool) -> str:
    """Determine sync mode from CLI options.

    Args:
        rev: Git revision to index (commit SHA, branch, tag).
        staged: Whether to index staged changes only.
        worktree: Whether to index worktree explicitly.

    Returns:
        Sync mode string ("worktree", "staged", or revision identifier).

    Raises:
        click.UsageError: If multiple mutually exclusive options are provided.
    """
    exclusive_options = sum([bool(rev), staged, worktree])
    if exclusive_options > 1:
        raise click.UsageError("--rev, --staged, and --worktree are mutually exclusive")

    if rev:
        return rev
    elif staged:
        return "staged"
    else:
        return "worktree"


def _quick_check_unchanged(
    repo_root: Path, db_path: Path, sync_mode: str, reindex: bool
) -> bool:
    """Check if index is up-to-date without expensive setup.

    Performs a quick check to see if the worktree tree SHA matches
    the last indexed SHA, allowing us to skip expensive model initialization.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        sync_mode: Sync mode (worktree, staged, or revision).
        reindex: Whether force reindex is requested.

    Returns:
        True if index is unchanged and sync can be skipped, False otherwise.
    """
    if reindex or sync_mode != "worktree":
        return False

    from ember.adapters.git_cmd.git_adapter import GitAdapter
    from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository

    vcs = GitAdapter(repo_root)
    meta_repo = SQLiteMetaRepository(db_path)
    try:
        current_tree_sha = vcs.get_worktree_tree_sha()
        last_indexed_sha = meta_repo.get("last_tree_sha")
        return current_tree_sha == last_indexed_sha
    except Exception as e:
        # If quick check fails, fall through to full sync
        click.echo(f"Warning: Quick check failed, performing full sync: {e}", err=True)
        return False


def _format_sync_results(response) -> None:
    """Print formatted sync results.

    Args:
        response: IndexResponse from indexing use case.
    """
    sync_type = "incremental" if response.is_incremental else "full"

    if response.files_indexed == 0 and response.chunks_deleted == 0:
        click.echo(f"✓ No changes detected ({sync_type} scan completed)")
    else:
        click.echo(f"✓ Indexed {response.files_indexed} files ({sync_type} sync)")

    if response.chunks_created > 0:
        click.echo(f"  • {response.chunks_created} chunks created")
    if response.chunks_updated > 0:
        click.echo(f"  • {response.chunks_updated} chunks updated")
    if response.chunks_deleted > 0:
        click.echo(f"  • {response.chunks_deleted} chunks deleted")
    if response.vectors_stored > 0:
        click.echo(f"  • {response.vectors_stored} vectors stored")
    if response.files_indexed > 0 or response.chunks_deleted > 0:
        click.echo(f"  • Tree SHA: {response.tree_sha[:12]}...")


@cli.command()
@click.option(
    "--worktree",
    is_flag=True,
    help="Index current worktree (including uncommitted changes).",
)
@click.option(
    "--staged",
    is_flag=True,
    help="Index staged changes only.",
)
@click.option(
    "--rev",
    type=str,
    help="Index specific git revision (commit SHA, branch, tag).",
)
@click.option(
    "--reindex",
    is_flag=True,
    help="Force full reindex (ignore incremental state).",
)
@click.pass_context
@handle_cli_errors("sync")
def sync(
    ctx: click.Context,
    worktree: bool,
    staged: bool,
    rev: str | None,
    reindex: bool,
) -> None:
    """Sync (index) the codebase.

    By default, indexes the current worktree.
    Can be run from any subdirectory within the repository.
    """
    from ember.adapters.config.toml_config_provider import TomlConfigProvider
    from ember.core.indexing.index_usecase import IndexRequest

    repo_root, ember_dir = get_ember_repo_root()
    db_path = ember_dir / "index.db"
    sync_mode = _parse_sync_mode(rev, staged, worktree)

    # Quick check optimization
    if _quick_check_unchanged(repo_root, db_path, sync_mode, reindex):
        click.echo("✓ No changes detected (quick check)")
        return

    # Load config and create indexing use case
    config = TomlConfigProvider().load(ember_dir)
    indexing_usecase = _create_indexing_usecase(repo_root, db_path, config)

    # Execute indexing with progress reporting
    request = IndexRequest(
        repo_root=repo_root,
        sync_mode=sync_mode,
        path_filters=[],
        force_reindex=reindex,
    )

    with progress_context(quiet_mode=ctx.obj.get("quiet", False)) as progress:
        if progress:
            response = indexing_usecase.execute(request, progress=progress)
        else:
            response = indexing_usecase.execute(request)

    if not response.success:
        click.echo(f"Error during indexing: {response.error}", err=True)
        sys.exit(1)

    _format_sync_results(response)


@cli.command()
@click.argument("query", type=str)
@click.argument("path", type=str, required=False, default=None)
@click.option(
    "--topk",
    "-k",
    type=int,
    default=None,
    help="Number of results to return (default: from config).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output results as JSON.",
)
@click.option(
    "--in",
    "path_filter",
    type=str,
    help="Filter results by path glob (e.g., '*.py'). Cannot be used with PATH argument.",
)
@click.option(
    "--lang",
    "lang_filter",
    type=str,
    help="Filter results by language (e.g., 'py', 'ts').",
)
@click.option(
    "--no-sync",
    "no_sync",
    is_flag=True,
    help="Skip auto-sync check before searching (faster but may return stale results).",
)
@click.option(
    "--context",
    "-C",
    type=int,
    default=0,
    help="Number of surrounding lines to show for each result.",
)
@click.pass_context
@handle_cli_errors("find")
def find(
    ctx: click.Context,
    query: str,
    path: str | None,
    topk: int | None,
    json_output: bool,
    path_filter: str | None,
    lang_filter: str | None,
    no_sync: bool,
    context: int,
) -> None:
    """Search for code matching the query.

    Performs hybrid search (BM25 + semantic embeddings).
    Can be run from any subdirectory within the repository.

    If PATH is provided, searches only within that path (relative to current directory).
    Examples:
        ember find "query"           # Search entire repo
        ember find "query" .          # Search current directory subtree
        ember find "query" src/       # Search src/ subtree
    """
    repo_root, ember_dir = get_ember_repo_root()
    db_path = ember_dir / "index.db"

    # Handle path argument: convert from CWD-relative to repo-relative glob
    if path is not None:
        # Convert path argument to absolute, then to relative from repo root
        cwd = Path.cwd().resolve()
        path_abs = (cwd / path).resolve()

        # Check if path is within repo
        try:
            path_rel_to_repo = path_abs.relative_to(repo_root)
        except ValueError:
            click.echo(f"Error: Path '{path}' is not within repository", err=True)
            sys.exit(1)

        # Check for mutually exclusive filter options
        if path_filter:
            click.echo(
                f"Error: Cannot use both PATH argument ('{path}') and --in filter ('{path_filter}').\n"
                f"Use PATH to search a directory subtree, OR --in for glob patterns, but not both.",
                err=True,
            )
            sys.exit(1)

        # Create glob pattern for this path subtree
        path_filter = f"{path_rel_to_repo}/**" if path_rel_to_repo != Path(".") else "*/**"

    # Load config
    from ember.adapters.config.toml_config_provider import TomlConfigProvider

    config_provider = TomlConfigProvider()
    config = config_provider.load(ember_dir)

    # Use config default for topk if not specified
    if topk is None:
        topk = config.search.topk

    # Auto-sync: Check if index is stale and sync if needed (unless --no-sync)
    if not no_sync:
        check_and_auto_sync(
            repo_root=repo_root,
            db_path=db_path,
            config=config,
            quiet_mode=json_output,
            verbose=ctx.obj.get("verbose", False),
        )

    # Lazy imports - only load heavy dependencies when find is actually called
    from ember.adapters.fts.sqlite_fts import SQLiteFTS
    from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
    from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
    from ember.core.retrieval.search_usecase import SearchUseCase
    from ember.domain.entities import Query

    # Initialize dependencies
    text_search = SQLiteFTS(db_path)
    vector_search = SqliteVecAdapter(db_path)
    chunk_repo = SQLiteChunkRepository(db_path)
    embedder = _create_embedder(config)

    # Create search use case
    search_usecase = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )

    # Create query object
    query_obj = Query(
        text=query,
        topk=topk,
        path_filter=path_filter,
        lang_filter=lang_filter,
        json_output=json_output,
    )

    # Execute search
    results = search_usecase.search(query_obj)

    # Cache results for cat/open commands
    cache_path = ember_dir / ".last_search.json"
    try:
        import json

        cache_data = ResultPresenter.serialize_for_cache(query, results)
        cache_path.write_text(json.dumps(cache_data, indent=2))
    except Exception as e:
        # Log cache errors but don't fail the command
        if ctx.obj.get("verbose", False):
            click.echo(f"Warning: Could not cache results: {e}", err=True)

    # Display results
    presenter = ResultPresenter(LocalFileSystem())
    if json_output:
        click.echo(presenter.format_json_output(results, context=context, repo_root=repo_root))
    else:
        presenter.format_human_output(results, context=context, repo_root=repo_root, config=config)


@cli.command()
@click.argument("initial_query", type=str, required=False, default="")
@click.option(
    "--path",
    "path_filter",
    type=str,
    help="Limit search to directory path. Cannot be used with --in.",
)
@click.option(
    "--in",
    "file_pattern",
    type=str,
    help="Filter by glob pattern (e.g., '*.py'). Cannot be used with --path.",
)
@click.option(
    "--lang",
    "lang_filter",
    type=str,
    help="Filter by language (e.g., python, typescript).",
)
@click.option(
    "--topk",
    "-k",
    type=int,
    default=None,
    help="Max results to show (default: from config).",
)
@click.option(
    "--no-preview",
    is_flag=True,
    help="Start with preview pane disabled.",
)
@click.option(
    "--no-scores",
    is_flag=True,
    help="Hide relevance scores.",
)
@click.option(
    "--no-sync",
    "no_sync",
    is_flag=True,
    help="Skip auto-sync check before searching.",
)
@click.pass_context
@handle_cli_errors("search")
def search(
    ctx: click.Context,
    initial_query: str,
    path_filter: str | None,
    file_pattern: str | None,
    lang_filter: str | None,
    topk: int | None,
    no_preview: bool,
    no_scores: bool,
    no_sync: bool,
) -> None:
    """Interactive semantic search interface.

    Opens an fzf-style interactive search UI with real-time results,
    keyboard navigation, preview pane, and direct file opening.

    Can be run from any subdirectory within the repository.
    """
    repo_root, ember_dir = get_ember_repo_root()
    db_path = ember_dir / "index.db"

    # Load config
    from ember.adapters.config.toml_config_provider import TomlConfigProvider

    config_provider = TomlConfigProvider()
    config = config_provider.load(ember_dir)

    # Use config default for topk if not specified
    if topk is None:
        topk = config.search.topk

    # Check for mutually exclusive filter options
    if path_filter and file_pattern:
        click.echo(
            f"Error: Cannot use both --path ('{path_filter}') and --in ('{file_pattern}').\n"
            f"Use --path to search a directory, OR --in for glob patterns, but not both.",
            err=True,
        )
        sys.exit(1)

    # Convert file_pattern to path_filter format
    if file_pattern:
        path_filter = f"**/{file_pattern}"

    # Auto-sync unless disabled
    if not no_sync:
        check_and_auto_sync(
            repo_root=repo_root,
            db_path=db_path,
            config=config,
            quiet_mode=True,  # Always quiet for interactive mode
            verbose=ctx.obj.get("verbose", False),
        )

    # Lazy imports
    from ember.adapters.fts.sqlite_fts import SQLiteFTS
    from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
    from ember.adapters.tui.search_ui import InteractiveSearchUI
    from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
    from ember.core.retrieval.search_usecase import SearchUseCase
    from ember.domain.entities import Query

    # Initialize search dependencies
    text_search = SQLiteFTS(db_path)
    vector_search = SqliteVecAdapter(db_path)
    chunk_repo = SQLiteChunkRepository(db_path)
    embedder = _create_embedder(config, show_progress=False)  # No progress for interactive

    # Create search use case
    search_usecase = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )

    # Create search function wrapper
    def search_fn(query: Query) -> list:
        return search_usecase.search(query)

    # Create and run interactive UI
    ui = InteractiveSearchUI(
        search_fn=search_fn,
        config=config,
        initial_query=initial_query,
        topk=topk,
        path_filter=path_filter,
        lang_filter=lang_filter,
        show_scores=not no_scores,
        show_preview=not no_preview,
    )

    selected_file, selected_line = ui.run()

    # If user selected a file, open it in editor
    if selected_file and selected_line:
        file_path = repo_root / selected_file
        open_file_in_editor(file_path, selected_line)


@cli.command()
@click.argument("identifier", type=str)
@click.option(
    "--context",
    "-C",
    type=int,
    default=0,
    help="Number of surrounding lines to show.",
)
@click.pass_context
@handle_cli_errors("cat")
def cat(ctx: click.Context, identifier: str, context: int) -> None:
    """Display content of a search result by index or chunk ID.

    Use after 'find' to view full chunk content.
    Can be run from any subdirectory within the repository.

    IDENTIFIER can be:
      - Numeric index (e.g., '1', '2') from recent search results
      - Full chunk ID (e.g., 'blake3:a1b2c3d4...')
      - Short hash prefix (e.g., 'a1b2c3d4') - minimum 8 characters
    """
    from ember.adapters.config.toml_config_provider import TomlConfigProvider

    repo_root, ember_dir = get_ember_repo_root()
    config_provider = TomlConfigProvider()
    config = config_provider.load(ember_dir)

    # Look up result by numeric index or hash ID
    is_numeric = identifier.isdigit()
    if is_numeric:
        cache_path = ember_dir / ".last_search.json"
        result = lookup_result_from_cache(identifier, cache_path)
    else:
        from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository

        db_path = ember_dir / "index.db"
        chunk_repo = SQLiteChunkRepository(db_path)
        result = lookup_result_by_hash(identifier, chunk_repo)

    # Display header
    display_index = int(identifier) if is_numeric else None
    format_result_header(result, display_index, show_symbol=True)
    click.echo(
        click.style(
            f"Lines {result['start_line']}-{result['end_line']} ({result['lang'] or 'text'})",
            dim=True,
        )
    )
    click.echo()

    # Display content (with context or with highlighting)
    if context > 0:
        if not display_content_with_context(result, context, repo_root):
            click.echo(result["content"])
    else:
        display_content_with_highlighting(
            result, config, verbose=ctx.obj.get("verbose", False)
        )

    click.echo()


@cli.command()
@click.argument("index", type=int)
@click.pass_context
@handle_cli_errors("open")
def open_result(ctx: click.Context, index: int) -> None:
    """Open search result in editor.

    Opens file at the correct line in $EDITOR.
    Can be run from any subdirectory within the repository.
    """
    import os

    repo_root, ember_dir = get_ember_repo_root()
    cache_path = ember_dir / ".last_search.json"

    # Load cached results
    cache_data = load_cached_results(cache_path)
    results = cache_data.get("results", [])

    # Validate and get the result
    result = validate_result_index(index, results)

    # Build absolute file path
    file_path = repo_root / result["path"]
    line_num = result["start_line"]

    # Show what we're doing (if not quiet)
    if not ctx.obj.get("quiet", False):
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"
        click.echo(f"Opening in {editor}:")
        format_result_header(result, index, show_symbol=True)

    # Open in editor
    open_file_in_editor(file_path, line_num)


@cli.command()
@click.argument("output_path", type=click.Path())
@click.option(
    "--no-preview",
    is_flag=True,
    help="Strip content from export (embeddings only).",
)
@click.pass_context
def export(ctx: click.Context, output_path: str, no_preview: bool) -> None:
    """Export index to a bundle.

    Creates a portable bundle for sharing or backup.
    """
    click.echo("export command - not yet implemented")
    click.echo(f"Would export to: {output_path}")


@cli.command()
@click.argument("bundle_path", type=click.Path(exists=True))
@click.pass_context
def import_bundle(ctx: click.Context, bundle_path: str) -> None:
    """Import index from a bundle.

    Loads a previously exported index bundle.
    """
    click.echo("import command - not yet implemented")
    click.echo(f"Would import from: {bundle_path}")


@cli.command()
@click.pass_context
def audit(ctx: click.Context) -> None:
    """Audit indexed content for potential secrets.

    Scans for API keys, tokens, and other sensitive data.
    """
    click.echo("audit command - not yet implemented")
    click.echo("Would scan for secrets in indexed content")


# Register import and open commands with proper names
cli.add_command(import_bundle, name="import")
cli.add_command(open_result, name="open")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show ember index status and configuration.

    Displays information about the current index state, including:
    - Number of indexed files and chunks
    - Last sync time
    - Whether index is up to date
    - Current configuration
    """
    from ember.adapters.config.toml_config_provider import TomlConfigProvider
    from ember.adapters.git_cmd.git_adapter import GitAdapter
    from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
    from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
    from ember.core.status.status_usecase import StatusRequest, StatusUseCase

    repo_root, ember_dir = get_ember_repo_root()

    # Load configuration
    config_provider = TomlConfigProvider()
    config = config_provider.load(ember_dir)

    # Set up repositories
    db_path = ember_dir / "index.db"
    vcs = GitAdapter(repo_root)
    chunk_repo = SQLiteChunkRepository(db_path)
    meta_repo = SQLiteMetaRepository(db_path)

    # Execute status use case
    use_case = StatusUseCase(
        vcs=vcs,
        chunk_repo=chunk_repo,
        meta_repo=meta_repo,
        config=config,
    )

    response = use_case.execute(StatusRequest(repo_root=repo_root))

    if not response.success:
        click.echo(f"✗ Failed to get status: {response.error}", err=True)
        sys.exit(1)

    # Display status
    click.echo(f"✓ Ember initialized at {repo_root}\n")

    click.echo("Index Status:")
    click.echo(f"  Indexed files: {response.indexed_files}")
    click.echo(f"  Total chunks: {response.total_chunks}")

    if response.last_tree_sha:
        if response.is_stale:
            click.echo(f"  Status: {click.style('⚠ Out of date', fg='yellow')}")
            click.echo("    Run 'ember sync' to update index")
        else:
            click.echo(f"  Status: {click.style('✓ Up to date', fg='green')}")
    else:
        click.echo(f"  Status: {click.style('⚠ Never synced', fg='yellow')}")
        click.echo("    Run 'ember sync' to index your repository")

    # Show configuration
    if response.config:
        click.echo("\nConfiguration:")
        click.echo(f"  Search results (topk): {response.config.search.topk}")
        click.echo(f"  Chunking strategy: {response.config.index.chunk}")
        if response.config.index.chunk == "lines":
            click.echo(f"  Line window: {response.config.index.line_window} lines")
            click.echo(f"  Overlap: {response.config.index.overlap_lines} lines")
        if response.model_fingerprint:
            # Extract model name from fingerprint (e.g., "jina-embeddings-v2-base-code")
            model_name = response.model_fingerprint.split(":")[0] if ":" in response.model_fingerprint else response.model_fingerprint
            click.echo(f"  Model: {model_name}")


# Daemon management commands
@cli.group()
def daemon() -> None:
    """Manage the embedding daemon server.

    The daemon keeps the embedding model loaded in memory for instant searches.
    It starts automatically when needed and shuts down after idle timeout.
    """
    pass


@daemon.command()
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (blocks)")
@click.pass_context
def start(ctx: click.Context, foreground: bool) -> None:
    """Start the daemon server."""
    from ember.adapters.config.toml_config_provider import TomlConfigProvider
    from ember.core.cli_utils import ensure_daemon_with_progress

    # Load config for daemon timeout
    ember_dir = Path.home() / ".ember"
    ember_dir.mkdir(parents=True, exist_ok=True)
    config_provider = TomlConfigProvider()
    config = config_provider.load(ember_dir)

    if foreground:
        # Foreground mode uses direct lifecycle management
        from ember.adapters.daemon.lifecycle import DaemonLifecycle

        lifecycle = DaemonLifecycle(idle_timeout=config.model.daemon_timeout)

        if lifecycle.is_running():
            click.echo("✓ Daemon is already running")
            return

        click.echo("Starting daemon in foreground...")
        try:
            lifecycle.start(foreground=True)
        except RuntimeError as e:
            click.echo(f"✗ Failed to start daemon: {e}", err=True)
            sys.exit(1)
    else:
        # Background mode with progress
        from ember.adapters.daemon.lifecycle import DaemonLifecycle

        quiet = ctx.obj.get("quiet", False)
        daemon_manager = DaemonLifecycle(idle_timeout=config.model.daemon_timeout)
        if ensure_daemon_with_progress(daemon_manager, quiet=quiet):
            if not quiet:
                click.echo("✓ Daemon started successfully")
        else:
            click.echo("✗ Failed to start daemon", err=True)
            sys.exit(1)


@daemon.command()
def stop() -> None:
    """Stop the daemon server."""
    from ember.adapters.daemon.lifecycle import DaemonLifecycle

    lifecycle = DaemonLifecycle()

    if not lifecycle.is_running():
        click.echo("Daemon is not running")
        return

    click.echo("Stopping daemon...")
    if lifecycle.stop():
        click.echo("✓ Daemon stopped successfully")
    else:
        click.echo("✗ Failed to stop daemon", err=True)
        sys.exit(1)


@daemon.command()
def restart() -> None:
    """Restart the daemon server."""
    from ember.adapters.daemon.lifecycle import DaemonLifecycle

    lifecycle = DaemonLifecycle()
    click.echo("Restarting daemon...")

    if lifecycle.restart():
        click.echo("✓ Daemon restarted successfully")
    else:
        click.echo("✗ Failed to restart daemon", err=True)
        sys.exit(1)


@daemon.command(name="status")
def daemon_status() -> None:
    """Show daemon status."""
    from ember.adapters.daemon.lifecycle import DaemonLifecycle

    lifecycle = DaemonLifecycle()
    status = lifecycle.status()

    # Display status
    if status["running"]:
        click.echo(f"✓ Daemon is running (PID {status['pid']})")
    else:
        click.echo("✗ Daemon is not running")

    # Show details
    click.echo("\nDetails:")
    click.echo(f"  Status: {status['status']}")
    click.echo(f"  Socket: {status['socket']}")
    click.echo(f"  PID file: {status['pid_file']}")
    click.echo(f"  Log file: {status['log_file']}")

    # Only show message for non-running states (errors/warnings)
    if status.get("message") and status["status"] != "running":
        click.echo(f"\n{status['message']}")


def main() -> int:
    """Main entrypoint for the CLI."""
    try:
        cli(obj={})
        return 0
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
