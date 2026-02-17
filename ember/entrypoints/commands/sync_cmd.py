"""Sync command for Ember CLI.

Handles index synchronization including auto-sync, staleness checks,
and result formatting.
"""

from __future__ import annotations

from pathlib import Path

import click

from ember.core.cli_utils import EmberCliError, progress_context
from ember.core.sync import classify_sync_error, get_targeted_sync_hint
from ember.domain.entities import SyncErrorType, SyncResult


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


# Backward-compatible alias for tests that import from this module
_get_targeted_sync_hint = get_targeted_sync_hint


def _build_sync_detail_lines(response) -> list[str]:
    """Build detail lines for sync results display.

    Args:
        response: IndexResponse from indexing use case.

    Returns:
        List of formatted detail strings to display.
    """
    details: list[str] = []
    stat_fields = [
        ("chunks_created", "chunks created"),
        ("chunks_updated", "chunks updated"),
        ("chunks_deleted", "chunks deleted"),
        ("vectors_stored", "vectors stored"),
    ]
    for attr, label in stat_fields:
        value = getattr(response, attr, 0)
        if value > 0:
            details.append(f"  • {value} {label}")

    if response.files_failed > 0:
        details.append(f"  • {response.files_failed} file(s) failed to index")

    if response.files_indexed > 0 or response.chunks_deleted > 0:
        details.append(f"  • Tree SHA: {response.tree_sha[:12]}...")

    return details


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

    for line in _build_sync_detail_lines(response):
        click.echo(line)

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


def register_commands(cli_group: click.Group, handle_errors) -> None:
    """Register sync commands with the CLI group.

    Args:
        cli_group: The main CLI click group.
        handle_errors: The handle_cli_errors decorator.
    """

    @cli_group.command()
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
    @handle_errors("sync")
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
        # Late imports from cli to support test patching at ember.entrypoints.cli.*
        from ember.core.indexing.index_usecase import IndexRequest
        from ember.entrypoints.cli import _echo, _load_config, get_ember_repo_root

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
            hint = get_targeted_sync_hint(response.error or "")
            raise EmberCliError(
                f"Indexing failed: {response.error}",
                hint=hint,
            )

        _format_sync_results(response, verbose=ctx.obj.get("verbose", False), quiet=quiet)

    return sync
