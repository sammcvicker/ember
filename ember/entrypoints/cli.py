"""Ember CLI entrypoint.

Command-line interface for Ember code search tool.
This module defines the main CLI group, shared utilities, and registers
all command modules. Individual commands live in ember.entrypoints.commands/.
"""

from __future__ import annotations

import functools
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from ember.core.retrieval.search_usecase import SearchUseCase
    from ember.domain.config import EmberConfig
    from ember.ports.embedder import Embedder

from ember.adapters.vss.sqlite_vec_adapter import DimensionMismatchError
from ember.core.cli_utils import (
    EmberCliError,
    repo_not_found_error,
)
from ember.core.indexing.index_usecase import ModelMismatchError
from ember.domain.exceptions import EmberDomainError
from ember.version import __version__

# ---------------------------------------------------------------------------
# Shared utilities used by command modules
# ---------------------------------------------------------------------------


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

    Args:
        command_name: Name of the command (e.g., "find", "search") for error message.
        in_param_name: The parameter name for the --in option in ctx.params.

    Returns:
        A Click callback function for the path argument.
    """
    def callback(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
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

    Args:
        command_name: Name of the command (e.g., "find", "search") for error message.
        path_param_name: The parameter name for the PATH argument in ctx.params.

    Returns:
        A Click callback function for the --in option.
    """
    def callback(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
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
                raise
            except EmberDomainError as e:
                raise EmberCliError(e.message, hint=e.hint) from e
            except ModelMismatchError as e:
                raise EmberCliError(
                    str(e),
                    hint="The embedding model in your config differs from the one used to build the index.",
                ) from e
            except DimensionMismatchError as e:
                raise EmberCliError(
                    str(e),
                    hint="The embedding model in your config differs from the one used to build the index.",
                ) from e
            except sqlite3.Error as e:
                raise EmberCliError(
                    f"Database error: {e}",
                    hint="Run 'ember sync --reindex' to rebuild the index.",
                ) from e
            except requests.exceptions.Timeout as e:
                raise EmberCliError(
                    f"Network timeout: {e}",
                    hint="Request timed out. Check your network connection and retry.",
                ) from e
            except (requests.exceptions.ConnectionError, URLError) as e:
                raise EmberCliError(
                    f"Network error: {e}",
                    hint="Check your internet connection and retry.",
                ) from e
            except TimeoutError as e:
                raise EmberCliError(
                    f"Operation timed out: {e}",
                    hint="The operation timed out. Try again or check system resources.",
                ) from e
            except PermissionError as e:
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
                error_msg = str(e)
                if "No space left" in error_msg or "ENOSPC" in error_msg:
                    raise EmberCliError(
                        "Disk full: No space left on device",
                        hint="Free up disk space and retry",
                    ) from e
                else:
                    raise EmberCliError(
                        f"OS error: {e}",
                        hint="Run with --verbose for more details",
                    ) from e
            except RuntimeError as e:
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
    """
    from ember.adapters.factory import EmbedderFactory

    factory = EmbedderFactory(config)
    return factory.create_embedder(show_progress=show_progress)


def _create_search_usecase(db_path: Path, embedder) -> SearchUseCase:
    """Create search use case with all required dependencies.

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
    """Shared dependencies for find/search commands."""

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
    from ember.entrypoints.commands.sync_cmd import ensure_synced  # noqa: F811

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

    Returns:
        Tuple of (repo_root, ember_dir).

    Raises:
        EmberCliError: If not in an ember repository.
    """
    from ember.core.repo_utils import find_repo_root

    try:
        return find_repo_root()
    except RuntimeError:
        repo_not_found_error()


# ---------------------------------------------------------------------------
# Main CLI group
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Register all command modules
# ---------------------------------------------------------------------------

from ember.entrypoints.commands import (  # noqa: E402
    config_cmd,
    daemon_cmd,
    init_cmd,
    search_cmd,
    status_cmd,
    sync_cmd,
)

# Register init command
init_cmd.register_commands(cli, handle_cli_errors)

# Register sync command
sync_cmd.register_commands(cli, handle_cli_errors)

# Register search commands (find, search, cat, open)
search_cmd.register_commands(cli, handle_cli_errors)

# Register status command
status_cmd.register_commands(cli, handle_cli_errors)

# Register config commands
config_cmd.register_commands(cli, handle_cli_errors)

# Register daemon commands
daemon_cmd.register_commands(cli, handle_cli_errors)

# ---------------------------------------------------------------------------
# Backward-compatible re-exports for existing test imports
# ---------------------------------------------------------------------------

# Re-export command functions so `from ember.entrypoints.cli import sync` works
# These are looked up from the cli group's command map
init = cli.commands["init"]
sync = cli.commands["sync"]
find = cli.commands["find"]
search = cli.commands["search"]
cat = cli.commands["cat"]
open_result = cli.commands["open"]
status = cli.commands["status"]
config = cli.commands["config"]
daemon = cli.commands["daemon"]

# Backward-compatible re-exports for existing test imports.
# Tests import these from `ember.entrypoints.cli` so we re-export them here.
# Uses importlib inside a function to avoid ruff import-sorting conflicts.


def _re_export() -> None:
    """Populate module globals with re-exports from command sub-modules."""
    import importlib

    _mod = importlib.import_module
    _g = globals()

    _sync = _mod("ember.entrypoints.commands.sync_cmd")
    for _name in [
        "_check_index_staleness", "_create_indexing_usecase", "_execute_sync",
        "_format_sync_results", "_get_targeted_sync_hint", "_parse_sync_mode",
        "_quick_check_unchanged", "_show_interactive_sync_message",
        "_show_sync_completion_message", "_show_sync_error_message", "ensure_synced",
    ]:
        _g[_name] = getattr(_sync, _name)

    _init = _mod("ember.entrypoints.commands.init_cmd")
    for _name in [
        "_display_system_resources", "_ensure_model_downloaded", "_handle_download_error",
        "_prompt_for_model_choice", "_report_init_results", "_select_embedding_model",
    ]:
        _g[_name] = getattr(_init, _name)

    _cfg = _mod("ember.entrypoints.commands.config_cmd")
    for _name in [
        "_display_config_summary", "_display_local_config_info", "_display_path_status",
        "_load_and_display_config", "_show_effective_config",
    ]:
        _g[_name] = getattr(_cfg, _name)

    _entities = _mod("ember.domain.entities")
    _g["SyncErrorType"] = _entities.SyncErrorType


_re_export()
del _re_export

# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


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
