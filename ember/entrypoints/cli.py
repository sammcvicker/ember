"""Ember CLI entrypoint.

Command-line interface for Ember code search tool.
"""

import sys
from pathlib import Path

import blake3
import click

from ember.core.cli_utils import (
    check_and_auto_sync,
    format_result_header,
    load_cached_results,
    progress_context,
    validate_result_index,
)
from ember.core.presentation import ResultPresenter


def _create_embedder(config):
    """Create embedder based on configuration.

    Args:
        config: EmberConfig with model settings

    Returns:
        Embedder instance (daemon client or direct)
    """
    if config.model.mode == "daemon":
        # Use daemon mode (default)
        # Client will auto-start daemon on first use
        from ember.adapters.daemon.client import DaemonEmbedderClient

        return DaemonEmbedderClient(
            fallback=True, auto_start=True, daemon_timeout=config.model.daemon_timeout
        )
    else:
        # Use direct mode (fallback or explicit config)
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        return JinaCodeEmbedder()


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
    vector_repo = SQLiteVectorRepository(db_path)
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


@click.group()
@click.version_option(version="0.2.0", prog_name="ember")
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
    """
    # Lazy import - only load when init is actually called
    from ember.core.config.init_usecase import InitRequest, InitUseCase

    repo_root = Path.cwd().resolve()

    # Create use case and execute
    use_case = InitUseCase(version="0.2.0")
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
def sync(
    ctx: click.Context,
    worktree: bool,
    staged: bool,
    rev: str | None,
    reindex: bool,
) -> None:
    """Sync (index) the codebase.

    By default, indexes the current worktree.
    """
    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    db_path = ember_dir / "index.db"

    # Check if ember is initialized
    if not ember_dir.exists() or not db_path.exists():
        click.echo("Error: Ember not initialized in this directory", err=True)
        click.echo("Run 'ember init' first", err=True)
        sys.exit(1)

    # Determine sync mode
    if rev:
        sync_mode = rev
    elif staged:
        sync_mode = "staged"
    else:
        sync_mode = "worktree"

    # Load config
    from ember.adapters.config.toml_config_provider import TomlConfigProvider

    config_provider = TomlConfigProvider()
    config = config_provider.load(ember_dir)

    try:
        # Import only what's needed for this command
        from ember.adapters.git_cmd.git_adapter import GitAdapter
        from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
        from ember.core.indexing.index_usecase import IndexRequest

        # Quick check: if not force reindex and tree SHA unchanged, skip expensive setup
        if not reindex and sync_mode == "worktree":
            vcs = GitAdapter(repo_root)
            meta_repo = SQLiteMetaRepository(db_path)
            try:
                current_tree_sha = vcs.get_worktree_tree_sha()
                last_indexed_sha = meta_repo.get_last_indexed_tree_sha()
                if current_tree_sha == last_indexed_sha:
                    if ctx.obj.get("verbose", False):
                        click.echo("DEBUG: Tree SHAs match, returning early", err=True)
                    click.echo("✓ No changes detected (index up to date)")
                    return
            except Exception as e:
                # If quick check fails, fall through to full sync
                if ctx.obj.get("verbose", False):
                    click.echo(f"Quick check failed: {e}", err=True)
                pass

        # Create indexing use case with all dependencies (starts daemon if needed)
        indexing_usecase = _create_indexing_usecase(repo_root, db_path, config)

        # Execute indexing with progress reporting (unless quiet mode)
        request = IndexRequest(
            repo_root=repo_root,
            sync_mode=sync_mode,
            path_filters=[],
            force_reindex=reindex,
        )

        # Use progress bar unless in quiet mode
        with progress_context(quiet_mode=ctx.obj.get("quiet", False)) as progress:
            if progress:
                response = indexing_usecase.execute(request, progress=progress)
            else:
                response = indexing_usecase.execute(request)

        if not response.success:
            click.echo(f"Error during indexing: {response.error}", err=True)
            sys.exit(1)

        # Report results
        sync_type = "incremental" if response.is_incremental else "full"

        if response.files_indexed == 0 and response.chunks_deleted == 0:
            click.echo("✓ No changes detected (index up to date)")
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

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error during sync: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument("query", type=str)
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
    help="Filter results by path glob (e.g., 'src/**/*.py').",
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
@click.pass_context
def find(
    ctx: click.Context,
    query: str,
    topk: int | None,
    json_output: bool,
    path_filter: str | None,
    lang_filter: str | None,
    no_sync: bool,
) -> None:
    """Search for code matching the query.

    Performs hybrid search (BM25 + semantic embeddings).
    """
    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    db_path = ember_dir / "index.db"

    # Check if ember is initialized
    if not ember_dir.exists() or not db_path.exists():
        click.echo("Error: Ember not initialized in this directory", err=True)
        click.echo("Run 'ember init' first", err=True)
        sys.exit(1)

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

    try:
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
        if json_output:
            click.echo(ResultPresenter.format_json_output(results))
        else:
            ResultPresenter.format_human_output(results)

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error during search: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument("index", type=int)
@click.option(
    "--context",
    "-C",
    type=int,
    default=0,
    help="Number of surrounding lines to show.",
)
@click.pass_context
def cat(ctx: click.Context, index: int, context: int) -> None:
    """Display content of a search result by index.

    Use after 'find' to view full chunk content.
    """
    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    cache_path = ember_dir / ".last_search.json"

    try:
        # Load cached results
        cache_data = load_cached_results(cache_path)
        results = cache_data.get("results", [])

        # Validate and get the result
        result = validate_result_index(index, results)

        # Display header
        format_result_header(result, index, show_symbol=True)
        click.echo(
            click.style(
                f"Lines {result['start_line']}-{result['end_line']} ({result['lang'] or 'text'})",
                dim=True,
            )
        )
        click.echo()

        # Get chunk content
        content = result["content"]

        # If context requested, read file and show surrounding lines
        if context > 0:
            file_path = repo_root / result["path"]
            if file_path.exists():
                try:
                    file_lines = file_path.read_text(errors="replace").splitlines()
                    start_line = result["start_line"]
                    end_line = result["end_line"]

                    # Calculate context range (1-based line numbers)
                    context_start = max(1, start_line - context)
                    context_end = min(len(file_lines), end_line + context)

                    # Display with line numbers
                    for line_num in range(context_start, context_end + 1):
                        line_content = file_lines[line_num - 1]  # Convert to 0-based
                        # Highlight the chunk lines
                        if start_line <= line_num <= end_line:
                            click.echo(f"{line_num:5} | {line_content}")
                        else:
                            click.echo(click.style(f"{line_num:5} | {line_content}", dim=True))
                except Exception as e:
                    # Fall back to just chunk content if file read fails
                    click.echo(
                        f"Warning: Could not read context from {result['path']}: {e}", err=True
                    )
                    click.echo(content)
            else:
                click.echo(
                    f"Warning: File {result['path']} not found, showing chunk only", err=True
                )
                click.echo(content)
        else:
            # Just display the chunk content
            click.echo(content)

        click.echo()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument("index", type=int)
@click.pass_context
def open_result(ctx: click.Context, index: int) -> None:
    """Open search result in editor.

    Opens file at the correct line in $EDITOR.
    """
    import os
    import subprocess

    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    cache_path = ember_dir / ".last_search.json"

    try:
        # Load cached results
        cache_data = load_cached_results(cache_path)
        results = cache_data.get("results", [])

        # Validate and get the result
        result = validate_result_index(index, results)

        # Build absolute file path
        file_path = repo_root / result["path"]

        # Check if file exists
        if not file_path.exists():
            click.echo(f"Error: File not found: {result['path']}", err=True)
            sys.exit(1)

        # Determine which editor to use
        # Priority: $VISUAL > $EDITOR > vim (fallback)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"

        # Build editor command with line number
        # Different editors have different syntax for opening at a line
        editor_name = Path(editor).name.lower()
        line_num = result["start_line"]

        if editor_name in ("vim", "vi", "nvim", "nano"):
            # vim/vi/nvim/nano: +line syntax
            cmd = [editor, f"+{line_num}", str(file_path)]
        elif editor_name in ("emacs", "emacsclient"):
            # emacs: +line syntax
            cmd = [editor, f"+{line_num}", str(file_path)]
        elif editor_name in ("code", "vscode"):
            # VS Code: --goto file:line syntax
            cmd = [editor, "--goto", f"{file_path}:{line_num}"]
        elif editor_name == "subl":
            # Sublime Text: file:line syntax
            cmd = [editor, f"{file_path}:{line_num}"]
        elif editor_name == "atom":
            # Atom: file:line syntax
            cmd = [editor, f"{file_path}:{line_num}"]
        else:
            # Unknown editor: try vim-style +line syntax
            cmd = [editor, f"+{line_num}", str(file_path)]

        # Show what we're doing (if not quiet)
        if not ctx.obj.get("quiet", False):
            click.echo(f"Opening in {editor}:")
            format_result_header(result, index, show_symbol=True)

        # Execute editor command
        subprocess.run(cmd, check=True)

    except subprocess.CalledProcessError as e:
        click.echo(f"Error: Failed to open editor: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo(f"Error: Editor '{editor}' not found", err=True)
        click.echo("Set $EDITOR or $VISUAL environment variable", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


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
def start(foreground: bool) -> None:
    """Start the daemon server."""
    from ember.adapters.daemon.lifecycle import DaemonLifecycle

    lifecycle = DaemonLifecycle()

    if lifecycle.is_running():
        click.echo("✓ Daemon is already running")
        return

    click.echo("Starting daemon...")
    try:
        lifecycle.start(foreground=foreground)
        if not foreground:
            click.echo("✓ Daemon started successfully")
    except RuntimeError as e:
        click.echo(f"✗ Failed to start daemon: {e}", err=True)
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


@daemon.command()
def status() -> None:
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

    if status.get("message"):
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
