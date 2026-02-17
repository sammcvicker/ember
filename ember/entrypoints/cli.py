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


def _echo(ctx: click.Context, message: str, **kwargs) -> None:
    """Print a message only if quiet mode is not active.

    Use this for all informational output that should be suppressed with --quiet.
    Do NOT use this for error messages or primary command output (search results,
    cat content, etc.) -- those should always be displayed.

    Args:
        ctx: Click context containing the quiet flag in ctx.obj.
        message: Message to print.
        **kwargs: Additional keyword arguments passed to click.echo
            (e.g., err=True, nl=True).
    """
    if not ctx.obj.get("quiet", False):
        click.echo(message, **kwargs)


def _secho(ctx: click.Context, message: str, **kwargs) -> None:
    """Print a styled message only if quiet mode is not active.

    Use this for styled informational output that should be suppressed with --quiet.
    Do NOT use this for error messages or primary command output.

    Args:
        ctx: Click context containing the quiet flag in ctx.obj.
        message: Message to print.
        **kwargs: Additional keyword arguments passed to click.secho
            (e.g., fg="green", err=True).
    """
    if not ctx.obj.get("quiet", False):
        click.secho(message, **kwargs)


def _make_path_in_exclusive_callback(command_name: str, in_param_name: str = "path_filter"):
    """Create a callback that validates PATH and --in are mutually exclusive.

    This validates the constraint early during argument parsing, providing a
    Click UsageError with helpful examples instead of a domain error at runtime.

    Args:
        command_name: Name of the command (e.g., "find", "search") for error message.
        in_param_name: The parameter name for the --in option in ctx.params.

    Returns:
        A Click callback function for the path argument.
    """
    def callback(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
        # Check if --in filter was already provided
        in_filter = ctx.params.get(in_param_name)
        if value is not None and in_filter is not None:
            raise click.UsageError(
                f"Cannot use both PATH and --in. Choose one:\n"
                f"  ember {command_name} 'query' {value}\n"
                f"  ember {command_name} 'query' --in '{in_filter}'"
            )
        return value
    return callback


def _make_in_filter_exclusive_callback(command_name: str, path_param_name: str = "path"):
    """Create a callback that validates --in and PATH are mutually exclusive.

    This validates the constraint early during argument parsing, providing a
    Click UsageError with helpful examples instead of a domain error at runtime.

    Args:
        command_name: Name of the command (e.g., "find", "search") for error message.
        path_param_name: The parameter name for the PATH argument in ctx.params.

    Returns:
        A Click callback function for the --in option.
    """
    def callback(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
        # Check if PATH argument was already provided
        path_value = ctx.params.get(path_param_name)
        if value is not None and path_value is not None:
            raise click.UsageError(
                f"Cannot use both PATH and --in. Choose one:\n"
                f"  ember {command_name} 'query' {path_value}\n"
                f"  ember {command_name} 'query' --in '{value}'"
            )
        return value
    return callback


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
    import sqlite3
    from urllib.error import URLError

    import requests.exceptions

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
            except sqlite3.Error as e:
                # Database error - suggest reindex to rebuild
                raise EmberCliError(
                    f"Database error: {e}",
                    hint="Run 'ember sync --reindex' to rebuild the index.",
                ) from e
            except requests.exceptions.Timeout as e:
                # Network timeout - suggest retry
                raise EmberCliError(
                    f"Network timeout: {e}",
                    hint="Request timed out. Check your network connection and retry.",
                ) from e
            except (requests.exceptions.ConnectionError, URLError) as e:
                # Network connection error - suggest checking connection
                raise EmberCliError(
                    f"Network error: {e}",
                    hint="Check your internet connection and retry.",
                ) from e
            except TimeoutError as e:
                # Built-in timeout (e.g., from subprocess or socket operations)
                raise EmberCliError(
                    f"Operation timed out: {e}",
                    hint="The operation timed out. Try again or check system resources.",
                ) from e
            except PermissionError as e:
                # Permission denied - provide targeted hint with filename if available
                filename = getattr(e, "filename", None)
                if filename:
                    raise EmberCliError(
                        f"Permission denied: {filename}",
                        hint=f"Check file permissions: ls -la {filename}",
                    ) from e
                else:
                    raise EmberCliError(
                        "Permission denied",
                        hint="Check file and directory permissions in .ember/",
                    ) from e
            except OSError as e:
                # Check for disk full condition
                error_msg = str(e)
                if "No space left" in error_msg or "ENOSPC" in error_msg:
                    raise EmberCliError(
                        "Disk full: No space left on device",
                        hint="Free up disk space and retry",
                    ) from e
                else:
                    # Generic OS error - suggest checking logs
                    raise EmberCliError(
                        f"OS error: {e}",
                        hint="Run with --verbose for more details",
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
    quiet = ctx.obj.get("quiet", False)

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
            quiet=quiet,
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

    with progress_context(show_progress=show_progress) as progress:
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


def _show_interactive_sync_message(
    interactive_mode: bool,
    show_progress: bool,
    quiet: bool = False,
) -> None:
    """Show 'Syncing...' message for interactive mode without progress bar.

    Args:
        interactive_mode: Whether command is in interactive mode.
        show_progress: Whether progress bar is being shown.
        quiet: If True, suppress the message entirely.
    """
    if interactive_mode and not show_progress and not quiet:
        click.echo("Syncing index...", err=True)


def ensure_synced(
    repo_root: Path,
    db_path: Path,
    config,
    show_progress: bool = True,
    interactive_mode: bool = False,
    verbose: bool = False,
    quiet: bool = False,
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
        quiet: If True, suppress all status messages (errors still shown via verbose).

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

        # In quiet mode (suppress all status messages):
        result = ensure_synced(repo_root, db_path, config, quiet=True)
    """
    try:
        is_stale = _check_index_staleness(repo_root, db_path)
        if not is_stale:
            return SyncResult(synced=False, files_indexed=0)

        _show_interactive_sync_message(interactive_mode, show_progress, quiet)
        success, files_indexed = _execute_sync(repo_root, db_path, config, show_progress)

        if show_progress and not quiet:
            _show_sync_completion_message(success, files_indexed)

        return SyncResult(synced=True, files_indexed=files_indexed)

    except Exception as e:
        error_type = classify_sync_error(e)
        if verbose:
            _show_sync_error_message(e, error_type)
        return SyncResult(synced=False, files_indexed=0, error=str(e), error_type=error_type)


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
        if not response.global_config_created:
            click.echo(f"  ✓ Using model: {selected_model} (from global config)")
        click.echo("\nNext: Run 'ember sync' to index your codebase")


def _ensure_model_downloaded(model_name: str, quiet: bool) -> bool:
    """Ensure the embedding model is downloaded before daemon starts.

    This prevents daemon startup timeouts on fresh install by downloading
    the model during init when the user expects setup time.

    Args:
        model_name: The model preset or HuggingFace ID to download.
        quiet: If True, suppress progress output (but still show critical errors).

    Returns:
        True if model was downloaded or already cached, False on error.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from ember.adapters.local_models import create_embedder, is_model_cached

    if is_model_cached(model_name):
        return True

    try:
        # Create embedder and call ensure_loaded() to trigger download
        embedder = create_embedder(model_name)

        if quiet:
            # In quiet mode, just download without progress
            embedder.ensure_loaded()
        else:
            # Show Rich progress spinner during download
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                progress.add_task(
                    f"Downloading model: {model_name} (this may take a minute)...",
                    total=None,
                )
                embedder.ensure_loaded()
            click.echo(f"  Downloaded model: {model_name}")

        return True
    except Exception as e:
        # Handle all errors with categorized messages
        _handle_download_error(e, model_name, quiet)
        return False


def _handle_download_error(error: Exception, model_name: str, quiet: bool) -> None:
    """Handle download errors with categorized messages and actionable hints.

    Args:
        error: The exception that occurred during download.
        model_name: The model that was being downloaded.
        quiet: If True, show minimal output (but still show error).
    """
    from urllib.error import URLError

    import requests

    error_str = str(error)

    # Check for network-related errors first (before OSError check)
    # requests.exceptions.ConnectionError is a subclass of OSError
    is_network_error = isinstance(
        error,
        (requests.exceptions.ConnectionError, URLError),
    )
    is_timeout = isinstance(error, requests.exceptions.Timeout)

    if is_network_error:
        click.echo("  ✗ Network error. Check internet connection and retry.")
        if not quiet:
            click.echo("    Hint: ember init --model bge-small uses a smaller model (~130MB)")
    elif is_timeout:
        click.echo("  ✗ Connection timed out. Try again or use a smaller model.")
        if not quiet:
            click.echo("    Hint: ember init --model bge-small uses a smaller model (~130MB)")
    elif isinstance(error, OSError):
        # Handle file system errors with specific guidance
        if "No space left" in error_str:
            click.echo("  ✗ Disk full. Free up ~2GB and retry.")
            if not quiet:
                click.echo("    Hint: ember init --model bge-small uses a smaller model (~130MB)")
        elif "Permission denied" in error_str:
            click.echo("  ✗ Permission denied. Check ~/.cache/huggingface/ permissions.")
            if not quiet:
                click.echo("    Hint: Run 'chmod -R u+rw ~/.cache/huggingface' to fix")
        else:
            click.echo(f"  ✗ File system error: {error}")
            if not quiet:
                click.echo("    (model will be downloaded when sync runs)")
    else:
        # Generic fallback for unexpected errors
        click.echo(f"  ✗ Model download failed: {error}")
        if not quiet:
            click.echo("    For help: ember init --verbose")
            click.echo("    (model will be downloaded when sync runs)")


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
    use_case = InitUseCase(db_initializer=db_initializer)
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
    repo_root: Path, db_path: Path, sync_mode: str, reindex: bool, quiet: bool = False
) -> bool:
    """Check if index is up-to-date without expensive setup.

    Delegates to SyncService.quick_check_unchanged() to avoid duplicating
    business logic in the CLI layer.

    Args:
        repo_root: Repository root path.
        db_path: Path to SQLite database.
        sync_mode: Sync mode (worktree, staged, or revision).
        reindex: Whether force reindex is requested.
        quiet: If True, suppress warning messages.

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
        if not quiet:
            click.echo(f"Warning: Quick check failed, performing full sync: {e}", err=True)
        return False


def _get_targeted_sync_hint(error_message: str) -> str:
    """Get a targeted hint based on the sync error message.

    Analyzes the error message to provide specific, actionable guidance
    rather than generic hints.

    Args:
        error_message: The error message from the failed sync operation.

    Returns:
        An actionable hint string specific to the error type.
    """
    error_lower = error_message.lower()

    # Database corruption - suggest reindex
    if any(
        term in error_lower
        for term in ["malformed", "corrupt", "database disk image", "not a database"]
    ):
        return "Run 'ember sync --reindex' to rebuild the index"

    # Model mismatch or dimension mismatch - suggest init --force
    if "model" in error_lower and ("changed" in error_lower or "mismatch" in error_lower):
        return "Run 'ember init --force' to reinitialize with the new model"

    # Vector dimension mismatch (model changed but message doesn't say "model")
    if "dimension" in error_lower and "mismatch" in error_lower:
        return "Run 'ember init --force' to reinitialize with the new model"

    # Permission issues
    if "permission" in error_lower or "access denied" in error_lower:
        return "Check file permissions in .ember/ directory"

    # Disk space issues
    if "no space left" in error_lower or "disk full" in error_lower:
        return "Free up disk space and retry"

    # Lock/busy database
    if "locked" in error_lower or "busy" in error_lower:
        return "Another process may be using the database. Wait and retry."

    # Generic fallback - suggest verbose mode
    return "Run 'ember sync --verbose' for more details"


def _format_sync_results(response, verbose: bool = False, quiet: bool = False) -> None:
    """Print formatted sync results.

    Args:
        response: IndexResponse from indexing use case.
        verbose: If True, show detailed information including individual parse failures.
        quiet: If True, suppress all informational output.
    """
    if quiet:
        return

    sync_type = "incremental" if response.is_incremental else "full"

    if response.files_indexed == 0 and response.chunks_deleted == 0:
        click.echo(f"✓ No changes detected ({sync_type} scan completed)")
    else:
        click.echo(f"✓ Synced {response.files_indexed} files ({sync_type} sync)")

    if response.chunks_created > 0:
        click.echo(f"  • {response.chunks_created} chunks created")
    if response.chunks_updated > 0:
        click.echo(f"  • {response.chunks_updated} chunks updated")
    if response.chunks_deleted > 0:
        click.echo(f"  • {response.chunks_deleted} chunks deleted")
    if response.vectors_stored > 0:
        click.echo(f"  • {response.vectors_stored} vectors stored")

    # Show parse failure summary
    parse_warnings = getattr(response, "parse_warnings", [])
    if parse_warnings:
        click.echo(
            f"  • {len(parse_warnings)} file(s) failed to parse "
            f"(fell back to line-based chunking)"
        )
        if verbose:
            for warning in parse_warnings:
                click.echo(f"    - {warning.path}: {warning.reason}")
        else:
            click.echo("    Run with --verbose to see which files failed")
    if response.files_failed > 0:
        click.echo(f"  • {response.files_failed} file(s) failed to index")

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

    quiet = ctx.obj.get("quiet", False)

    # Quick check optimization
    if _quick_check_unchanged(repo_root, db_path, sync_mode, reindex, quiet=quiet):
        _echo(ctx, "✓ No changes detected (quick check)")
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

    with progress_context(show_progress=not ctx.obj.get("quiet", False)) as progress:
        if progress:
            response = indexing_usecase.execute(request, progress=progress)
        else:
            response = indexing_usecase.execute(request)

    if not response.success:
        hint = _get_targeted_sync_hint(response.error or "")
        raise EmberCliError(
            f"Indexing failed: {response.error}",
            hint=hint,
        )

    _format_sync_results(response, verbose=ctx.obj.get("verbose", False), quiet=quiet)


@cli.command()
@click.argument("query", type=str)
@click.argument(
    "path",
    type=str,
    required=False,
    default=None,
    callback=_make_path_in_exclusive_callback("find"),
)
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
    callback=_make_in_filter_exclusive_callback("find"),
    is_eager=True,
    help="Filter results by path glob (e.g., '*.py'). Mutually exclusive with PATH.",
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
    query_obj = Query.from_strings(
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
        _secho(ctx, result_set.warning, fg="yellow", err=True)

    # Cache results for cat/open commands
    cache_path = deps.ember_dir / ".last_search.json"
    try:
        import json

        cache_data = ResultPresenter.serialize_for_cache(query, result_set.results)
        cache_path.write_text(json.dumps(cache_data, indent=2))
    except Exception as e:
        # Show cache errors to stderr unless quiet mode (non-critical warning)
        _echo(ctx, f"Warning: Could not cache results: {e}", err=True)

    # Display results
    presenter = ResultPresenter(LocalFileSystem())
    if json_output:
        click.echo(presenter.format_json_output(result_set.results, context=context, repo_root=deps.repo_root))
    else:
        presenter.format_human_output(result_set.results, context=context, repo_root=deps.repo_root, config=deps.config)


@cli.command()
@click.argument(
    "path",
    type=str,
    required=False,
    default=None,
    callback=_make_path_in_exclusive_callback("search", in_param_name="file_pattern"),
)
@click.option(
    "--in",
    "file_pattern",
    type=str,
    callback=_make_in_filter_exclusive_callback("search"),
    is_eager=True,
    help="Filter by glob pattern (e.g., '*.py'). Mutually exclusive with PATH.",
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


# Register the open command with proper name
cli.add_command(open_result, name="open")


@cli.command()
@click.option(
    "--detailed",
    is_flag=True,
    help="Show full technical details including configuration parameters.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output status as JSON for programmatic use.",
)
@click.pass_context
@handle_cli_errors("status")
def status(ctx: click.Context, detailed: bool, json_output: bool) -> None:
    """Show ember index status.

    By default, shows essential information:
    - Whether index is up to date
    - Number of indexed files and chunks
    - When last synced

    Use --detailed for full technical output including configuration parameters.
    Use --json for machine-readable JSON output.
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

    # JSON output mode
    if json_output:
        import json

        # Format last_sync as ISO 8601 string or None
        last_sync_iso = None
        if response.last_sync_time is not None:
            from datetime import UTC, datetime

            last_sync_iso = datetime.fromtimestamp(
                response.last_sync_time, tz=UTC
            ).isoformat()

        data = {
            "files": response.indexed_files,
            "chunks": response.total_chunks,
            "model": response.model_name,
            "stale": response.is_stale,
            "last_sync": last_sync_iso,
        }
        click.echo(json.dumps(data, indent=2))
        return

    # In quiet mode, suppress all informational status output
    quiet = ctx.obj.get("quiet", False)
    if quiet:
        return

    # Build sync time display
    sync_time_display = ""
    if response.last_sync_time_ago:
        sync_time_display = f" (synced {response.last_sync_time_ago})"

    # Display simplified status (default)
    if response.last_tree_sha:
        if response.is_stale:
            click.echo(
                click.style("Index is out of date", fg="yellow") + sync_time_display
            )
            click.echo(f"  {response.indexed_files} files indexed ({response.total_chunks:,} chunks)")
            if response.model_name:
                click.echo(f"  Using model: {response.model_name}")
            click.echo("")
            click.echo(click.style("Run 'ember sync' to update", fg="yellow"))
        else:
            click.echo(
                click.style("Index is up to date", fg="green") + sync_time_display
            )
            click.echo(f"  {response.indexed_files} files indexed ({response.total_chunks:,} chunks)")
            if response.model_name:
                click.echo(f"  Using model: {response.model_name}")
    else:
        click.echo(click.style("Index has never been synced", fg="yellow"))
        click.echo(f"  {response.indexed_files} files indexed ({response.total_chunks:,} chunks)")
        click.echo("")
        click.echo(click.style("Run 'ember sync' to index your repository", fg="yellow"))

    # Show detailed configuration if requested
    if detailed and response.config:
        click.echo("\nConfiguration:")
        click.echo(f"  Search results (topk): {response.config.search.topk}")
        click.echo(f"  Chunking strategy: {response.config.index.chunk}")
        if response.config.index.chunk == "lines":
            click.echo(f"  Line window: {response.config.index.line_window} lines")
            click.echo(f"  Overlap: {response.config.index.overlap_lines} lines")
        if response.model_fingerprint:
            click.echo(f"  Model fingerprint: {response.model_fingerprint}")
        if response.last_tree_sha:
            click.echo(f"  Tree SHA: {response.last_tree_sha}")
        click.echo("\nView full config: ember config show")


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
) -> bool:
    """Load config using the provided loader and display it with a title.

    Returns:
        True if config was loaded and displayed successfully, False on error.
    """
    click.echo(f"\n{title}:")
    try:
        config = loader()
        _display_config_summary(config)
        return True
    except Exception as e:
        click.echo(f"  Error loading config: {e}", err=True)
        return False


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
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output configuration as JSON for programmatic use.",
)
@click.pass_context
@handle_cli_errors("config show")
def config_show(
    ctx: click.Context, show_global: bool, show_local: bool, json_output: bool
) -> None:
    """Show configuration file locations and current settings.

    By default shows both locations. Use --global or --local to show specific one.
    Use --json for machine-readable JSON output of the effective configuration.
    """
    import dataclasses

    from ember.shared.config_io import get_global_config_path

    global_path = get_global_config_path()
    local_path = _get_local_config_path()

    # JSON output mode - output effective config as JSON
    if json_output:
        import json

        if local_path and local_path.parent.exists():
            effective_config = _load_config(local_path.parent)
        elif global_path.exists():
            from ember.shared.config_io import load_config

            effective_config = load_config(global_path)
        else:
            from ember.domain.config import EmberConfig as EmberConfigClass

            effective_config = EmberConfigClass.default()

        data = dataclasses.asdict(effective_config)
        click.echo(json.dumps(data, indent=2))
        return

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
        _echo(ctx, f"Creating {config_type} config at {config_path}...")
        if edit_global:
            create_global_config_file(config_path)
        else:
            create_minimal_project_config(config_path)

    # Open in editor
    editor = get_editor()
    _echo(ctx, f"Opening {config_path} in {editor}...")
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
            _echo(ctx, "✓ Daemon is already running")
            return

        _echo(ctx, "Starting daemon in foreground...")
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
@click.pass_context
@handle_cli_errors("daemon stop")
def stop(ctx: click.Context) -> None:
    """Stop the daemon server."""
    from ember.adapters.factory import DaemonFactory

    daemon_factory = DaemonFactory()
    lifecycle = daemon_factory.create_daemon_lifecycle()

    if not lifecycle.is_running():
        _echo(ctx, "Daemon is not running")
        return

    _echo(ctx, "Stopping daemon...")
    if lifecycle.stop():
        _echo(ctx, "✓ Daemon stopped successfully")
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
    _echo(ctx, "Restarting daemon...")

    if lifecycle.restart():
        _echo(ctx, "✓ Daemon restarted successfully")
    else:
        raise EmberCliError(
            "Failed to restart daemon",
            hint="Try 'ember daemon stop' then 'ember daemon start'",
        )


@daemon.command(name="status")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output daemon status as JSON for programmatic use.",
)
@click.pass_context
@handle_cli_errors("daemon status")
def daemon_status(ctx: click.Context, json_output: bool) -> None:
    """Show daemon status.

    Use --json for machine-readable JSON output.
    """
    from ember.adapters.factory import DaemonFactory

    daemon_factory = DaemonFactory()
    lifecycle = daemon_factory.create_daemon_lifecycle()
    status = lifecycle.status()

    # JSON output mode
    if json_output:
        import json

        click.echo(json.dumps(status, indent=2))
        return

    quiet = ctx.obj.get("quiet", False)

    if quiet:
        return

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
