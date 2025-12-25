"""Ember CLI entrypoint.

Command-line interface for Ember code search tool.
"""

from __future__ import annotations

import functools
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from ember.core.config.init_usecase import InitResponse
    from ember.core.hardware import SystemResources
    from ember.core.retrieval.search_usecase import SearchUseCase
    from ember.domain.config import EmberConfig
    from ember.ports.embedder import Embedder

from ember.adapters.fs.local import LocalFileSystem
from ember.adapters.vss.sqlite_vec_adapter import DimensionMismatchError
from ember.core.cli_utils import (
    EmberCliError,
    display_content_with_context,
    display_content_with_highlighting,
    format_result_header,
    get_editor,
    load_cached_results,
    lookup_result_by_hash,
    lookup_result_from_cache,
    normalize_path_filter,
    open_file_in_editor,
    progress_context,
    repo_not_found_error,
    validate_result_index,
)
from ember.core.indexing.index_usecase import ModelMismatchError
from ember.core.presentation import ResultPresenter
from ember.core.sync import classify_sync_error
from ember.domain.entities import SyncErrorType, SyncResult
from ember.domain.exceptions import EmberDomainError
from ember.version import __version__


def handle_cli_errors(command_name: str):
    """Decorator to handle common CLI errors.

    Catches RuntimeError and Exception, displaying appropriate messages
    and showing tracebacks in verbose mode. EmberCliError exceptions
    are re-raised to use their built-in formatting.

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
            except EmberCliError:
                # Let EmberCliError propagate to use its format_message()
                raise
            except EmberDomainError as e:
                # Convert domain exceptions to CLI exceptions
                raise EmberCliError(e.message, hint=e.hint) from e
            except ModelMismatchError as e:
                # Embedding model changed - clear action required
                raise EmberCliError(
                    str(e),
                    hint="The embedding model in your config differs from the one used to build the index.",
                ) from e
            except DimensionMismatchError as e:
                # Vector dimension mismatch - clear action required
                raise EmberCliError(
                    str(e),
                    hint="The embedding model in your config differs from the one used to build the index.",
                ) from e
            except RuntimeError as e:
                # Convert RuntimeError to EmberCliError with generic hint
                raise EmberCliError(
                    str(e),
                    hint="Run with --verbose for more details",
                ) from e
            except Exception as e:
                ctx = click.get_current_context()
                if ctx.obj.get("verbose", False):
                    import traceback

                    traceback.print_exc()
                raise EmberCliError(
                    f"Unexpected error in {command_name}: {e}",
                    hint="Run with --verbose for more details",
                ) from e

        return wrapper

    return decorator


def _load_config(ember_dir: Path):
    """Load configuration for the given ember directory.

    Centralizes config loading to avoid code duplication across CLI commands.
    Uses ConfigFactory to create the config provider and load merged config.

    Args:
        ember_dir: Path to the .ember directory (or parent containing config).

    Returns:
        EmberConfig with merged global and local settings.
    """
    from ember.adapters.factory import ConfigFactory

    config_factory = ConfigFactory()
    return config_factory.create_config_provider().load(ember_dir)


def _create_embedder(config, show_progress: bool = True):
    """Create embedder based on configuration.

    Args:
        config: EmberConfig with model settings
        show_progress: Show progress bar during daemon startup

    Returns:
        Embedder instance (daemon client or direct)

    Raises:
        RuntimeError: If daemon fails to start
        ValueError: If model name is not recognized
    """
    from ember.adapters.factory import EmbedderFactory

    factory = EmbedderFactory(config)
    return factory.create_embedder(show_progress=show_progress)


def _create_search_usecase(db_path: Path, embedder) -> SearchUseCase:
    """Create search use case with all required dependencies.

    Centralizes the dependency setup for find/search commands to avoid
    duplication and ensure consistent initialization.

    Args:
        db_path: Path to the SQLite database
        embedder: Embedder instance for query vectorization

    Returns:
        Configured SearchUseCase ready for search operations
    """
    from ember.adapters.factory import UseCaseFactory

    factory = UseCaseFactory()
    return factory.create_search_usecase(db_path, embedder)


@dataclass
class SearchCommandDependencies:
    """Shared dependencies for find/search commands.

    Encapsulates all initialization state needed by both the find
    and search commands, eliminating duplicated setup code.
    """

    repo_root: Path
    ember_dir: Path
    db_path: Path
    config: EmberConfig
    topk: int
    embedder: Embedder
    search_usecase: SearchUseCase


def _setup_search_command(
    ctx: click.Context,
    repo_root: Path,
    ember_dir: Path,
    topk: int | None,
    no_sync: bool,
    show_progress: bool = True,
    interactive_mode: bool = False,
) -> SearchCommandDependencies:
    """Common setup for find/search commands.

    Handles all shared initialization:
    - Loading configuration
    - Applying topk default from config
    - Auto-sync check (unless disabled)
    - Creating embedder and search use case

    Args:
        ctx: Click context for accessing verbose flag
        repo_root: Repository root path
        ember_dir: Path to .ember directory
        topk: Number of results (None to use config default)
        no_sync: Skip auto-sync check
        show_progress: Show progress bar during sync/embedder init
        interactive_mode: Use interactive sync mode (brief status message)

    Returns:
        SearchCommandDependencies with all initialized components
    """
    db_path = ember_dir / "index.db"

    config = _load_config(ember_dir)

    if topk is None:
        topk = config.search.topk

    if not no_sync:
        ensure_synced(
            repo_root=repo_root,
            db_path=db_path,
            config=config,
            show_progress=show_progress,
            interactive_mode=interactive_mode,
            verbose=ctx.obj.get("verbose", False),
        )

    embedder = _create_embedder(config, show_progress=show_progress)
    search_usecase = _create_search_usecase(db_path, embedder)

    return SearchCommandDependencies(
        repo_root=repo_root,
        ember_dir=ember_dir,
        db_path=db_path,
        config=config,
        topk=topk,
        embedder=embedder,
        search_usecase=search_usecase,
    )


def get_ember_repo_root() -> tuple[Path, Path]:
    """Get ember repository root or exit with error.

    Finds the ember repository root and .ember directory from the current
    working directory. If not in an ember repository, raises EmberCliError.

    Returns:
        Tuple of (repo_root, ember_dir) where:
        - repo_root: Absolute path to repository root
        - ember_dir: Absolute path to .ember/ directory

    Raises:
        EmberCliError: If not in an ember repository.
    """
    from ember.core.repo_utils import find_repo_root

    try:
        return find_repo_root()
    except RuntimeError:
        repo_not_found_error()


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
    from ember.adapters.factory import EmbedderFactory, UseCaseFactory

    embedder_factory = EmbedderFactory(config)
    embedder = embedder_factory.create_embedder()

    usecase_factory = UseCaseFactory()
    return usecase_factory.create_indexing_usecase(repo_root, db_path, config, embedder)


def _check_index_staleness(repo_root: Path, db_path: Path) -> bool | None:
    """Check if the index is stale and needs syncing.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.

    Returns:
        True if sync is needed, False if up to date, None on error.

    Raises:
        Exception: If staleness check fails (git or database error).
    """
    from ember.adapters.factory import RepositoryFactory

    repo_factory = RepositoryFactory()
    vcs = repo_factory.create_git_adapter(repo_root)
    meta_repo = repo_factory.create_meta_repository(db_path)

    current_tree_sha = vcs.get_worktree_tree_sha()
    last_tree_sha = meta_repo.get("last_tree_sha")

    return last_tree_sha != current_tree_sha


def _execute_sync(
    repo_root: Path,
    db_path: Path,
    config,
    show_progress: bool,
) -> tuple[bool, int]:
    """Execute the sync operation.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        config: Configuration object.
        show_progress: Whether to show progress bar.

    Returns:
        Tuple of (success, files_indexed).
    """
    from ember.core.indexing.index_usecase import IndexRequest

    indexing_usecase = _create_indexing_usecase(repo_root, db_path, config)

    request = IndexRequest(
        repo_root=repo_root,
        sync_mode="worktree",
        path_filters=[],
        force_reindex=False,
    )

    quiet_mode = not show_progress
    with progress_context(quiet_mode=quiet_mode) as progress:
        if progress:
            response = indexing_usecase.execute(request, progress=progress)
        else:
            response = indexing_usecase.execute(request)

    return response.success, response.files_indexed


def _show_sync_completion_message(success: bool, files_indexed: int) -> None:
    """Show completion message after sync.

    Args:
        success: Whether sync was successful.
        files_indexed: Number of files that were indexed.
    """
    if not success:
        return

    if files_indexed > 0:
        click.echo(f"✓ Synced {files_indexed} file(s)", err=True)
    else:
        click.echo("✓ Index up to date", err=True)


def _show_sync_error_message(error: Exception, error_type: SyncErrorType) -> None:
    """Show error message for sync failure.

    Args:
        error: The exception that occurred.
        error_type: Classification of the error.
    """
    if error_type == SyncErrorType.PERMISSION_ERROR:
        click.echo(f"Warning: Permission denied during sync: {error}", err=True)
    else:
        click.echo(f"Warning: Could not check index staleness: {error}", err=True)


def _show_interactive_sync_message(interactive_mode: bool, show_progress: bool) -> None:
    """Show 'Syncing...' message for interactive mode without progress bar.

    Args:
        interactive_mode: Whether command is in interactive mode.
        show_progress: Whether progress bar is being shown.
    """
    if interactive_mode and not show_progress:
        click.echo("Syncing index...", err=True)


def ensure_synced(
    repo_root: Path,
    db_path: Path,
    config,
    show_progress: bool = True,
    interactive_mode: bool = False,
    verbose: bool = False,
) -> SyncResult:
    """Ensure the index is synced before running a command.

    This is the unified sync helper for all Ember commands that need fresh data.
    Use this instead of implementing sync logic directly in each command.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        config: Configuration object.
        show_progress: If True, show progress bar during sync. Default True.
        interactive_mode: If True, show brief status message even without progress bar.
            Use this for TUI commands where progress bar would corrupt display.
        verbose: If True, show warnings on errors.

    Returns:
        SyncResult with information about whether sync was performed.

    Example:
        # In a command that needs fresh data with progress bar:
        result = ensure_synced(repo_root, db_path, config, show_progress=True)

        # In a TUI command (no progress bar but show status):
        result = ensure_synced(repo_root, db_path, config,
                              show_progress=False, interactive_mode=True)

        # In JSON output mode (completely silent):
        result = ensure_synced(repo_root, db_path, config, show_progress=False)
    """
    try:
        is_stale = _check_index_staleness(repo_root, db_path)
        if not is_stale:
            return SyncResult(synced=False, files_indexed=0)

        _show_interactive_sync_message(interactive_mode, show_progress)
        success, files_indexed = _execute_sync(repo_root, db_path, config, show_progress)

        if show_progress:
            _show_sync_completion_message(success, files_indexed)

        return SyncResult(synced=True, files_indexed=files_indexed)

    except Exception as e:
        error_type = classify_sync_error(e)
        if verbose:
            _show_sync_error_message(e, error_type)
        return SyncResult(synced=False, files_indexed=0, error=str(e), error_type=error_type)


def check_and_auto_sync(
    repo_root: Path,
    db_path: Path,
    config,
    quiet_mode: bool = False,
    verbose: bool = False,
) -> None:
    """Check if index is stale and auto-sync if needed.

    .. deprecated::
        Use :func:`ensure_synced` instead. This function is kept for backward
        compatibility and will be removed in a future version.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        config: Configuration object.
        quiet_mode: If True, suppress progress and messages.
        verbose: If True, show warnings on errors.

    Note:
        If staleness check fails, continues silently to allow search to proceed.
    """
    # Delegate to ensure_synced with appropriate parameters
    ensure_synced(
        repo_root=repo_root,
        db_path=db_path,
        config=config,
        show_progress=not quiet_mode,
        verbose=verbose,
    )


@click.group()
@click.version_option(version=__version__, prog_name="ember")
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


def _select_embedding_model(
    model: str | None,
    quiet: bool,
    yes: bool,
) -> str:
    """Select embedding model based on user input or system auto-detection.

    Args:
        model: User-specified model name, or None for auto-detection.
        quiet: If True, suppress informational output.
        yes: If True, accept recommended model without prompting.

    Returns:
        The selected model name.
    """
    from ember.core.hardware import (
        detect_system_resources,
        get_model_recommendation_reason,
        recommend_model,
    )

    if model is not None:
        return model

    resources = detect_system_resources()
    recommended = recommend_model(resources)
    reason = get_model_recommendation_reason(recommended, resources)

    if not quiet:
        _display_system_resources(resources, recommended, reason)

    if recommended != "jina-code-v2" and not yes:
        return _prompt_for_model_choice(resources, recommended)

    return recommended


def _display_system_resources(
    resources: SystemResources,
    recommended: str,
    reason: str,
) -> None:
    """Display detected system resources to user.

    Args:
        resources: Detected system resources.
        recommended: Recommended model name.
        reason: Human-readable reason for recommendation.
    """
    click.echo("\nDetecting system resources...")
    click.echo(f"  Available RAM: {resources.available_ram_gb:.1f}GB")
    if resources.gpu is not None:
        gpu = resources.gpu
        click.echo(
            f"  GPU: {gpu.device_name} "
            f"({gpu.total_vram_gb:.1f}GB VRAM, {gpu.free_vram_gb:.1f}GB free)"
        )
    click.echo(f"  Recommended model: {recommended}")
    click.echo(f"  ({reason})")
    click.echo()


def _prompt_for_model_choice(resources: SystemResources, recommended: str) -> str:
    """Prompt user to choose between recommended model and default.

    Args:
        resources: Detected system resources.
        recommended: Recommended model name.

    Returns:
        The user's chosen model name.
    """
    if resources.gpu is not None and resources.gpu.free_vram_gb < resources.available_ram_gb:
        click.echo(
            "The default model (jina-code-v2) requires ~1.6GB VRAM and may cause GPU memory issues."
        )
    else:
        click.echo(
            "The default model (jina-code-v2) requires ~1.6GB RAM and may cause slowdowns."
        )

    use_recommended = click.confirm(
        f"Use recommended model ({recommended}) instead?", default=True
    )
    return recommended if use_recommended else "jina-code-v2"


def _report_init_results(
    response: InitResponse,
    selected_model: str,
    quiet: bool,
) -> None:
    """Report init command results to user.

    Note: This function should only be called when response.success is True.

    Args:
        response: The InitResponse from the use case (must have success=True).
        selected_model: The model that was selected.
        quiet: If True, suppress detailed output.
    """
    # These are guaranteed to be non-None when success=True
    assert response.ember_dir is not None
    assert response.config_path is not None
    assert response.db_path is not None
    assert response.state_path is not None

    if response.global_config_created and not quiet:
        click.echo(f"Created global config at {response.global_config_path}")
        click.echo(f"  ✓ Using model: {selected_model}")
        click.echo("")

    if response.was_reinitialized:
        click.echo(f"Reinitialized existing ember index at {response.ember_dir}")
    else:
        click.echo(f"Initialized ember index at {response.ember_dir}")

    if not quiet:
        click.echo(f"  ✓ Created {response.config_path.name}")
        click.echo(f"  ✓ Created {response.db_path.name}")
        click.echo(f"  ✓ Created {response.state_path.name}")
        if not response.global_config_created:
            click.echo(f"  ✓ Using model: {selected_model} (from global config)")
        click.echo("\nNext: Run 'ember sync' to index your codebase")


def _ensure_model_downloaded(model_name: str, quiet: bool) -> bool:
    """Ensure the embedding model is downloaded before daemon starts.

    This prevents daemon startup timeouts on fresh install by downloading
    the model during init when the user expects setup time.

    Args:
        model_name: The model preset or HuggingFace ID to download.
        quiet: If True, suppress progress output.

    Returns:
        True if model was downloaded or already cached, False on error.
    """
    from ember.adapters.local_models import create_embedder, is_model_cached

    if is_model_cached(model_name):
        return True

    if not quiet:
        click.echo(f"Downloading embedding model: {model_name}")
        click.echo("  (this may take a minute on first run)")

    try:
        # Create embedder and call ensure_loaded() to trigger download
        embedder = create_embedder(model_name)
        embedder.ensure_loaded()

        if not quiet:
            click.echo("  ✓ Model downloaded successfully")
        return True
    except Exception as e:
        # Model download failed, but don't block init - daemon will retry
        if not quiet:
            click.echo(f"  ⚠ Model download failed: {e}")
            click.echo("    (model will be downloaded when sync runs)")
        return False


@cli.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Reinitialize even if .ember/ already exists.",
)
@click.option(
    "--model",
    "-m",
    type=str,
    default=None,
    help="Embedding model to use (jina-code-v2, bge-small, minilm, auto).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Accept recommended model without prompting.",
)
@click.pass_context
@handle_cli_errors("init")
def init(ctx: click.Context, force: bool, model: str | None, yes: bool) -> None:
    """Initialize Ember in the current directory.

    Creates .ember/ directory with configuration and database.
    If in a git repository, initializes at the git root.

    Detects available system RAM and GPU VRAM and suggests an appropriate
    embedding model. Use --model to override or --yes to accept the recommendation.
    """
    from ember.adapters.factory import ConfigFactory
    from ember.core.config.init_usecase import InitRequest, InitUseCase
    from ember.core.repo_utils import find_repo_root_for_init

    repo_root = find_repo_root_for_init()
    quiet = ctx.obj.get("quiet", False)

    selected_model = _select_embedding_model(model, quiet, yes)

    config_factory = ConfigFactory()
    db_initializer = config_factory.create_db_initializer()
    use_case = InitUseCase(db_initializer=db_initializer, version=__version__)
    request = InitRequest(repo_root=repo_root, force=force, model=selected_model)

    response = use_case.execute(request)
    if not response.success:
        hint = (
            "Use 'ember init --force' to reinitialize"
            if response.already_exists
            else "Check permissions and try again, or use --force to reinitialize"
        )
        raise EmberCliError(response.error or "Unknown error", hint=hint)

    # Pre-download the embedding model to prevent daemon startup timeouts (#378)
    # This happens after init succeeds but before reporting results
    _ensure_model_downloaded(selected_model, quiet)

    _report_init_results(response, selected_model, quiet)


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

    Delegates to SyncService.quick_check_unchanged() to avoid duplicating
    business logic in the CLI layer.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        sync_mode: Sync mode (worktree, staged, or revision).
        reindex: Whether force reindex is requested.

    Returns:
        True if index is unchanged and sync can be skipped, False otherwise.
    """
    from ember.adapters.factory import RepositoryFactory
    from ember.core.sync.sync_service import SyncService

    try:
        repo_factory = RepositoryFactory()
        vcs = repo_factory.create_git_adapter(repo_root)
        meta_repo = repo_factory.create_meta_repository(db_path)
        sync_service = SyncService(vcs, meta_repo)
        return sync_service.quick_check_unchanged(sync_mode, reindex)
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
    from ember.core.indexing.index_usecase import IndexRequest

    repo_root, ember_dir = get_ember_repo_root()
    db_path = ember_dir / "index.db"
    sync_mode = _parse_sync_mode(rev, staged, worktree)

    # Quick check optimization
    if _quick_check_unchanged(repo_root, db_path, sync_mode, reindex):
        click.echo("✓ No changes detected (quick check)")
        return

    # Load config and create indexing use case
    config = _load_config(ember_dir)
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
        raise EmberCliError(
            f"Indexing failed: {response.error}",
            hint="Run 'ember sync --reindex' to force a fresh index",
        )

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

    # Normalize path argument to path filter glob pattern
    path_filter = normalize_path_filter(
        path=path,
        existing_filter=path_filter,
        repo_root=repo_root,
        cwd=Path.cwd().resolve(),
    )

    # Setup shared search dependencies
    deps = _setup_search_command(
        ctx=ctx,
        repo_root=repo_root,
        ember_dir=ember_dir,
        topk=topk,
        no_sync=no_sync,
        show_progress=not json_output,
    )

    # Lazy import for Query entity
    from ember.domain.entities import Query

    # Create query object
    query_obj = Query(
        text=query,
        topk=deps.topk,
        path_filter=path_filter,
        lang_filter=lang_filter,
        json_output=json_output,
    )

    # Execute search
    result_set = deps.search_usecase.search(query_obj)

    # Display warning if results are degraded (missing chunks)
    if result_set.warning:
        click.secho(result_set.warning, fg="yellow", err=True)

    # Cache results for cat/open commands
    cache_path = deps.ember_dir / ".last_search.json"
    try:
        import json

        cache_data = ResultPresenter.serialize_for_cache(query, result_set.results)
        cache_path.write_text(json.dumps(cache_data, indent=2))
    except Exception as e:
        # Log cache errors but don't fail the command
        if ctx.obj.get("verbose", False):
            click.echo(f"Warning: Could not cache results: {e}", err=True)

    # Display results
    presenter = ResultPresenter(LocalFileSystem())
    if json_output:
        click.echo(presenter.format_json_output(result_set.results, context=context, repo_root=deps.repo_root))
    else:
        presenter.format_human_output(result_set.results, context=context, repo_root=deps.repo_root, config=deps.config)


@cli.command()
@click.argument("path", type=str, required=False, default=None)
@click.option(
    "--in",
    "file_pattern",
    type=str,
    help="Filter by glob pattern (e.g., '*.py'). Cannot be used with PATH argument.",
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
    path: str | None,
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

    If PATH is provided, searches only within that path (relative to current directory).
    Examples:
        ember search              # Search entire repo
        ember search .            # Search current directory subtree
        ember search src/         # Search src/ subtree
        ember search tests        # Search tests/ subtree
    """
    repo_root, ember_dir = get_ember_repo_root()

    # Convert file_pattern to path_filter format (e.g., "*.py" -> "**/*.py")
    existing_filter = f"**/{file_pattern}" if file_pattern else None

    # Normalize path argument to path filter glob pattern
    path_filter = normalize_path_filter(
        path=path,
        existing_filter=existing_filter,
        repo_root=repo_root,
        cwd=Path.cwd().resolve(),
    )

    # Setup shared search dependencies (no progress bar for TUI, use interactive mode)
    deps = _setup_search_command(
        ctx=ctx,
        repo_root=repo_root,
        ember_dir=ember_dir,
        topk=topk,
        no_sync=no_sync,
        show_progress=False,
        interactive_mode=True,
    )

    # Lazy imports
    from ember.adapters.tui.search_ui import InteractiveSearchUI
    from ember.domain.entities import Query

    # Create search function wrapper (returns list for TUI compatibility)
    def search_fn(query: Query) -> list:
        result_set = deps.search_usecase.search(query)
        return result_set.results

    # Create and run interactive UI
    ui = InteractiveSearchUI(
        search_fn=search_fn,
        config=deps.config,
        initial_query="",  # Always start with empty query, user types interactively
        topk=deps.topk,
        path_filter=path_filter,
        lang_filter=lang_filter,
        show_scores=not no_scores,
        show_preview=not no_preview,
    )

    selected_file, selected_line = ui.run()

    # If user selected a file, open it in editor
    if selected_file and selected_line:
        file_path = deps.repo_root / selected_file
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
    from ember.adapters.factory import RepositoryFactory

    repo_root, ember_dir = get_ember_repo_root()
    config = _load_config(ember_dir)

    # Look up result by numeric index or hash ID
    is_numeric = identifier.isdigit()
    if is_numeric:
        cache_path = ember_dir / ".last_search.json"
        result = lookup_result_from_cache(identifier, cache_path)
    else:
        repo_factory = RepositoryFactory()
        db_path = ember_dir / "index.db"
        chunk_repo = repo_factory.create_chunk_repository(db_path)
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
        click.echo(f"Opening in {get_editor()}:")
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
@handle_cli_errors("export")
def export(ctx: click.Context, output_path: str, no_preview: bool) -> None:
    """Export index to a bundle.

    Creates a portable bundle for sharing or backup.
    """
    click.echo("export command - not yet implemented")
    click.echo(f"Would export to: {output_path}")


@cli.command()
@click.argument("bundle_path", type=click.Path(exists=True))
@click.pass_context
@handle_cli_errors("import")
def import_bundle(ctx: click.Context, bundle_path: str) -> None:
    """Import index from a bundle.

    Loads a previously exported index bundle.
    """
    click.echo("import command - not yet implemented")
    click.echo(f"Would import from: {bundle_path}")


@cli.command()
@click.pass_context
@handle_cli_errors("audit")
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
@handle_cli_errors("status")
def status(ctx: click.Context) -> None:
    """Show ember index status and configuration.

    Displays information about the current index state, including:
    - Number of indexed files and chunks
    - Last sync time
    - Whether index is up to date
    - Current configuration
    """
    from ember.adapters.factory import RepositoryFactory
    from ember.core.status.status_usecase import StatusRequest, StatusUseCase

    repo_root, ember_dir = get_ember_repo_root()

    # Load configuration
    config = _load_config(ember_dir)

    # Set up repositories using factory
    db_path = ember_dir / "index.db"
    repo_factory = RepositoryFactory()
    vcs = repo_factory.create_git_adapter(repo_root)
    chunk_repo = repo_factory.create_chunk_repository(db_path)
    meta_repo = repo_factory.create_meta_repository(db_path)

    # Execute status use case
    use_case = StatusUseCase(
        vcs=vcs,
        chunk_repo=chunk_repo,
        meta_repo=meta_repo,
        config=config,
    )

    response = use_case.execute(StatusRequest(repo_root=repo_root))

    if not response.success:
        raise EmberCliError(
            f"Failed to get status: {response.error}",
            hint="Try 'ember sync' to refresh the index",
        )

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
        if response.model_name:
            click.echo(f"  Model: {response.model_name}")


# Configuration management commands
@cli.group()
def config() -> None:
    """Manage Ember configuration files.

    Ember uses a two-tier configuration system:
    - Local: .ember/config.toml (repo-specific settings)
    - Global: ~/.config/ember/config.toml (user defaults)

    Local settings override global settings. Missing values use built-in defaults.
    """
    pass


def _display_path_status(path: Path, label: str) -> None:
    """Display a config path with its existence status."""
    status = "exists" if path.exists() else "not created"
    color = "green" if path.exists() else "yellow"
    click.echo(f"{label}{path}")
    click.echo(f"  Status: {click.style(status, fg=color)}")


def _load_and_display_config(
    title: str, loader: Callable[[], EmberConfig]  # noqa: F821
) -> None:
    """Load config using the provided loader and display it with a title."""
    click.echo(f"\n{title}:")
    try:
        config = loader()
        _display_config_summary(config)
    except Exception as e:
        click.echo(f"  Error loading config: {e}")


def _get_local_config_path() -> Path | None:
    """Get the local config path if in a repository, or None otherwise."""
    try:
        _, ember_dir = get_ember_repo_root()
        return ember_dir / "config.toml"
    except EmberCliError:
        # Not in an ember repository
        return None


def _display_local_config_info(local_path: Path | None, show_local: bool) -> None:
    """Display local config path and status."""
    if local_path:
        _display_path_status(local_path, "Local config:  ")
    elif show_local:
        click.echo("Local config: Not in an Ember repository")


def _show_effective_config(
    local_path: Path | None,
    global_path: Path,
    include_local: bool,
    include_global: bool,
) -> None:
    """Show effective configuration content based on display mode."""
    from ember.shared.config_io import load_config

    if local_path and include_local:
        _load_and_display_config(
            "Effective configuration (merged global + local)",
            lambda: _load_config(local_path.parent),
        )
    elif include_global and not include_local and global_path.exists():
        _load_and_display_config(
            "Global configuration",
            lambda: load_config(global_path),
        )


@config.command(name="show")
@click.option(
    "--global", "-g", "show_global", is_flag=True, help="Show global config location"
)
@click.option(
    "--local", "-l", "show_local", is_flag=True, help="Show local config location"
)
@click.pass_context
@handle_cli_errors("config show")
def config_show(
    ctx: click.Context, show_global: bool, show_local: bool
) -> None:
    """Show configuration file locations and current settings.

    By default shows both locations. Use --global or --local to show specific one.
    """
    from ember.shared.config_io import get_global_config_path

    global_path = get_global_config_path()
    local_path = _get_local_config_path()

    # Determine what to display - default is both
    include_global = show_global or not show_local
    include_local = show_local or not show_global

    # Display path info
    if include_global:
        _display_path_status(global_path, "Global config: ")
    if include_local:
        _display_local_config_info(local_path, show_local)

    # Show effective configuration content
    _show_effective_config(local_path, global_path, include_local, include_global)


def _display_config_summary(config: EmberConfig) -> None:  # noqa: F821
    """Display a summary of config settings."""
    click.echo("  [index]")
    click.echo(f"    model = {config.index.model}")
    click.echo(f"    chunk = {config.index.chunk}")
    click.echo("  [model]")
    click.echo(f"    mode = {config.model.mode}")
    click.echo(f"    daemon_timeout = {config.model.daemon_timeout}")
    click.echo("  [search]")
    click.echo(f"    topk = {config.search.topk}")
    click.echo("  [display]")
    click.echo(f"    theme = {config.display.theme}")
    click.echo(f"    syntax_highlighting = {config.display.syntax_highlighting}")


@config.command(name="edit")
@click.option(
    "--global", "-g", "edit_global", is_flag=True, help="Edit global config file"
)
@click.pass_context
@handle_cli_errors("config edit")
def config_edit(ctx: click.Context, edit_global: bool) -> None:
    """Open configuration file in your default editor.

    Opens the local config by default. Use --global to edit global config.
    Creates the config file if it doesn't exist.
    """
    import subprocess

    from ember.shared.config_io import (
        create_global_config_file,
        create_minimal_project_config,
        get_global_config_path,
    )

    if edit_global:
        config_path = get_global_config_path()
        config_type = "global"
    else:
        # Find local config
        try:
            _, ember_dir = get_ember_repo_root()
            config_path = ember_dir / "config.toml"
            config_type = "local"
        except Exception as e:
            raise EmberCliError(
                "Not in an Ember repository",
                hint="Use 'ember config edit --global' to edit global config",
            ) from e

    # Create config file if it doesn't exist
    if not config_path.exists():
        click.echo(f"Creating {config_type} config at {config_path}...")
        if edit_global:
            create_global_config_file(config_path)
        else:
            create_minimal_project_config(config_path)

    # Open in editor
    editor = get_editor()
    click.echo(f"Opening {config_path} in {editor}...")
    try:
        subprocess.run([editor, str(config_path)], check=True)
    except subprocess.CalledProcessError as e:
        raise EmberCliError(
            f"Editor exited with error: {e.returncode}",
            hint="Set EDITOR environment variable to change your editor",
        ) from e
    except FileNotFoundError as e:
        raise EmberCliError(
            f"Editor '{editor}' not found",
            hint="Set EDITOR environment variable to your preferred editor",
        ) from e


@config.command(name="path")
@click.option(
    "--global", "-g", "show_global", is_flag=True, help="Show only global config path"
)
@click.option(
    "--local", "-l", "show_local", is_flag=True, help="Show only local config path"
)
@handle_cli_errors("config path")
def config_path(show_global: bool, show_local: bool) -> None:
    """Print config file path(s) for use in scripts.

    Outputs bare paths without any decoration, suitable for piping.
    """
    from ember.shared.config_io import get_global_config_path

    global_path = get_global_config_path()

    if show_global:
        click.echo(global_path)
        return

    if show_local:
        try:
            _, ember_dir = get_ember_repo_root()
            click.echo(ember_dir / "config.toml")
        except EmberCliError:
            # Not in an ember repository, exit silently with no output
            pass
        return

    # Default: show both
    click.echo(f"global:{global_path}")
    try:
        _, ember_dir = get_ember_repo_root()
        click.echo(f"local:{ember_dir / 'config.toml'}")
    except EmberCliError:
        # Not in an ember repository, only show global config
        pass


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
@handle_cli_errors("daemon start")
def start(ctx: click.Context, foreground: bool) -> None:
    """Start the daemon server."""
    from ember.adapters.factory import DaemonFactory
    from ember.core.cli_utils import ensure_daemon_with_progress

    # Load config for daemon timeout
    ember_dir = Path.home() / ".ember"
    ember_dir.mkdir(parents=True, exist_ok=True)
    config = _load_config(ember_dir)

    daemon_factory = DaemonFactory()

    if foreground:
        # Foreground mode uses direct lifecycle management
        lifecycle = daemon_factory.create_daemon_lifecycle(
            idle_timeout=config.model.daemon_timeout,
            model_name=config.index.model,
        )

        if lifecycle.is_running():
            click.echo("✓ Daemon is already running")
            return

        click.echo("Starting daemon in foreground...")
        try:
            lifecycle.start(foreground=True)
        except RuntimeError as e:
            raise EmberCliError(
                f"Failed to start daemon: {e}",
                hint="Check 'ember daemon status' for details, or try 'ember daemon restart'",
            ) from e
    else:
        # Background mode with progress
        quiet = ctx.obj.get("quiet", False)
        daemon_manager = daemon_factory.create_daemon_lifecycle(
            idle_timeout=config.model.daemon_timeout,
            model_name=config.index.model,
        )
        if ensure_daemon_with_progress(daemon_manager, quiet=quiet):
            if not quiet:
                click.echo("✓ Daemon started successfully")
        else:
            raise EmberCliError(
                "Failed to start daemon",
                hint="Check 'ember daemon status' for details, or try 'ember daemon restart'",
            )


@daemon.command()
@handle_cli_errors("daemon stop")
def stop() -> None:
    """Stop the daemon server."""
    from ember.adapters.factory import DaemonFactory

    daemon_factory = DaemonFactory()
    lifecycle = daemon_factory.create_daemon_lifecycle()

    if not lifecycle.is_running():
        click.echo("Daemon is not running")
        return

    click.echo("Stopping daemon...")
    if lifecycle.stop():
        click.echo("✓ Daemon stopped successfully")
    else:
        raise EmberCliError(
            "Failed to stop daemon",
            hint="The process may have already exited. Check 'ember daemon status'",
        )


@daemon.command()
@click.pass_context
@handle_cli_errors("daemon restart")
def restart(ctx: click.Context) -> None:
    """Restart the daemon server."""
    from ember.adapters.factory import DaemonFactory

    # Load config to get model name
    repo_root, ember_dir = get_ember_repo_root()
    config = _load_config(ember_dir)

    daemon_factory = DaemonFactory()
    lifecycle = daemon_factory.create_daemon_lifecycle(
        idle_timeout=config.model.daemon_timeout,
        model_name=config.index.model,
    )
    click.echo("Restarting daemon...")

    if lifecycle.restart():
        click.echo("✓ Daemon restarted successfully")
    else:
        raise EmberCliError(
            "Failed to restart daemon",
            hint="Try 'ember daemon stop' then 'ember daemon start'",
        )


@daemon.command(name="status")
@handle_cli_errors("daemon status")
def daemon_status() -> None:
    """Show daemon status."""
    from ember.adapters.factory import DaemonFactory

    daemon_factory = DaemonFactory()
    lifecycle = daemon_factory.create_daemon_lifecycle()
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
