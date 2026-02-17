"""Config commands for Ember CLI.

Handles configuration management: show, edit, and path commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from ember.core.cli_utils import EmberCliError

if TYPE_CHECKING:
    from ember.domain.config import EmberConfig


def _display_path_status(path: Path, label: str) -> None:
    """Display a config path with its existence status."""
    status = "exists" if path.exists() else "not created"
    color = "green" if path.exists() else "yellow"
    click.echo(f"{label}{path}")
    click.echo(f"  Status: {click.style(status, fg=color)}")


def _load_and_display_config(
    title: str, loader  # noqa: F821
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


def _get_local_config_path(get_repo_root_fn) -> Path | None:
    """Get the local config path if in a repository, or None otherwise."""
    try:
        _, ember_dir = get_repo_root_fn()
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
    load_config_fn,
) -> None:
    """Show effective configuration content based on display mode."""
    from ember.shared.config_io import load_config

    if local_path and include_local:
        _load_and_display_config(
            "Effective configuration (merged global + local)",
            lambda: load_config_fn(local_path.parent),
        )
    elif include_global and not include_local and global_path.exists():
        _load_and_display_config(
            "Global configuration",
            lambda: load_config(global_path),
        )


def register_commands(cli_group: click.Group, handle_errors) -> None:
    """Register config commands with the CLI group.

    Args:
        cli_group: The main CLI click group.
        handle_errors: The handle_cli_errors decorator.
    """

    @cli_group.group()
    def config() -> None:
        """Manage Ember configuration files.

        Ember uses a two-tier configuration system:
        - Local: .ember/config.toml (repo-specific settings)
        - Global: ~/.config/ember/config.toml (user defaults)

        Local settings override global settings. Missing values use built-in defaults.
        """
        pass

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
    @handle_errors("config show")
    def config_show(
        ctx: click.Context, show_global: bool, show_local: bool, json_output: bool
    ) -> None:
        """Show configuration file locations and current settings.

        By default shows both locations. Use --global or --local to show specific one.
        Use --json for machine-readable JSON output of the effective configuration.
        """
        import dataclasses

        from ember.entrypoints.cli import _load_config, get_ember_repo_root
        from ember.shared.config_io import get_global_config_path

        global_path = get_global_config_path()
        local_path = _get_local_config_path(get_ember_repo_root)

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
        _show_effective_config(local_path, global_path, include_local, include_global, _load_config)

    @config.command(name="edit")
    @click.option(
        "--global", "-g", "edit_global", is_flag=True, help="Edit global config file"
    )
    @click.pass_context
    @handle_errors("config edit")
    def config_edit(ctx: click.Context, edit_global: bool) -> None:
        """Open configuration file in your default editor.

        Opens the local config by default. Use --global to edit global config.
        Creates the config file if it doesn't exist.
        """
        import subprocess

        from ember.core.cli_utils import get_editor
        from ember.entrypoints.cli import _echo, get_ember_repo_root
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
    @handle_errors("config path")
    def config_path(show_global: bool, show_local: bool) -> None:
        """Print config file path(s) for use in scripts.

        Outputs bare paths without any decoration, suitable for piping.
        """
        from ember.entrypoints.cli import get_ember_repo_root
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

    return config, config_show, config_edit, config_path
