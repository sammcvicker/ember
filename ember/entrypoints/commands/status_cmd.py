"""Status command for Ember CLI.

Displays ember index status including staleness, file counts, and configuration.
"""

from __future__ import annotations

import click

from ember.core.cli_utils import EmberCliError


def register_commands(cli_group: click.Group, handle_errors) -> None:
    """Register status command with the CLI group.

    Args:
        cli_group: The main CLI click group.
        handle_errors: The handle_cli_errors decorator.
    """

    @cli_group.command()
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
    @handle_errors("status")
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
        from ember.entrypoints.cli import _load_config, get_ember_repo_root

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

    return status
