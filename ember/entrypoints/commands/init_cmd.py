"""Init command for Ember CLI.

Handles repository initialization including model selection,
system resource detection, and model download.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from ember.core.cli_utils import EmberCliError

if TYPE_CHECKING:
    from ember.core.config.init_usecase import InitResponse
    from ember.core.hardware import SystemResources


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


def _classify_download_error(error: Exception) -> tuple[str, str]:
    """Classify a download error into a user-facing message and hint.

    Args:
        error: The exception that occurred during download.

    Returns:
        Tuple of (error_message, hint_message).
    """
    from urllib.error import URLError

    import requests

    error_str = str(error)

    # Check network errors before OSError (ConnectionError is a subclass of OSError)
    if isinstance(error, (requests.exceptions.ConnectionError, URLError)):
        return (
            "Network error. Check internet connection and retry.",
            "ember init --model bge-small uses a smaller model (~130MB)",
        )
    if isinstance(error, requests.exceptions.Timeout):
        return (
            "Connection timed out. Try again or use a smaller model.",
            "ember init --model bge-small uses a smaller model (~130MB)",
        )
    if isinstance(error, OSError):
        if "No space left" in error_str:
            return (
                "Disk full. Free up ~2GB and retry.",
                "ember init --model bge-small uses a smaller model (~130MB)",
            )
        if "Permission denied" in error_str:
            return (
                "Permission denied. Check ~/.cache/huggingface/ permissions.",
                "Run 'chmod -R u+rw ~/.cache/huggingface' to fix",
            )
        return (f"File system error: {error}", "(model will be downloaded when sync runs)")

    return (f"Model download failed: {error}", "For help: ember init --verbose")


def _handle_download_error(error: Exception, model_name: str, quiet: bool) -> None:
    """Handle download errors with categorized messages and actionable hints.

    Args:
        error: The exception that occurred during download.
        model_name: The model that was being downloaded.
        quiet: If True, show minimal output (but still show error).
    """
    message, hint = _classify_download_error(error)
    click.echo(f"  ✗ {message}")
    if not quiet:
        click.echo(f"    Hint: {hint}")


def register_commands(cli_group: click.Group, handle_errors) -> None:
    """Register init command with the CLI group.

    Args:
        cli_group: The main CLI click group.
        handle_errors: The handle_cli_errors decorator.
    """

    @cli_group.command()
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
    @handle_errors("init")
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

    return init
