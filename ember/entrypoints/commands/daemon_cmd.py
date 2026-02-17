"""Daemon commands for Ember CLI.

Handles daemon lifecycle: start, stop, restart, and status.
"""

from __future__ import annotations

from pathlib import Path

import click

from ember.core.cli_utils import EmberCliError


def register_commands(cli_group: click.Group, handle_errors) -> None:
    """Register daemon commands with the CLI group.

    Args:
        cli_group: The main CLI click group.
        handle_errors: The handle_cli_errors decorator.
    """

    @cli_group.group()
    def daemon() -> None:
        """Manage the embedding daemon server.

        The daemon keeps the embedding model loaded in memory for instant searches.
        It starts automatically when needed and shuts down after idle timeout.
        """
        pass

    @daemon.command()
    @click.option("--foreground", "-f", is_flag=True, help="Run in foreground (blocks)")
    @click.pass_context
    @handle_errors("daemon start")
    def start(ctx: click.Context, foreground: bool) -> None:
        """Start the daemon server."""
        from ember.adapters.factory import DaemonFactory
        from ember.core.cli_utils import ensure_daemon_with_progress
        from ember.entrypoints.cli import _echo, _load_config

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
    @handle_errors("daemon stop")
    def stop(ctx: click.Context) -> None:
        """Stop the daemon server."""
        from ember.adapters.factory import DaemonFactory
        from ember.entrypoints.cli import _echo

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
    @handle_errors("daemon restart")
    def restart(ctx: click.Context) -> None:
        """Restart the daemon server."""
        from ember.adapters.factory import DaemonFactory
        from ember.entrypoints.cli import _echo, _load_config, get_ember_repo_root

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
    @handle_errors("daemon status")
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

    return daemon, start, stop, restart, daemon_status
