"""Search commands for Ember CLI.

Handles find, search (interactive), cat, and open commands.
"""

from __future__ import annotations

from pathlib import Path

import click

from ember.adapters.fs.local import LocalFileSystem
from ember.core.cli_utils import (
    display_content_with_context,
    display_content_with_highlighting,
    format_result_header,
    get_editor,
    load_cached_results,
    lookup_result_by_hash,
    lookup_result_from_cache,
    normalize_path_filter,
    open_file_in_editor,
    validate_result_index,
)
from ember.core.presentation import ResultPresenter


def register_commands(cli_group: click.Group, handle_errors) -> None:
    """Register search-related commands with the CLI group.

    Args:
        cli_group: The main CLI click group.
        handle_errors: The handle_cli_errors decorator.
    """
    # Late imports from cli are done inside command bodies to support
    # test patching at ember.entrypoints.cli.*
    from ember.entrypoints.cli import (
        _make_in_filter_exclusive_callback,
        _make_path_in_exclusive_callback,
    )

    @cli_group.command()
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
    @handle_errors("find")
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
        from ember.entrypoints.cli import _echo, _secho, _setup_search_command, get_ember_repo_root

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

    @cli_group.command()
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
    @handle_errors("search")
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
        from ember.entrypoints.cli import _setup_search_command, get_ember_repo_root

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

    @cli_group.command()
    @click.argument("identifier", type=str)
    @click.option(
        "--context",
        "-C",
        type=int,
        default=0,
        help="Number of surrounding lines to show.",
    )
    @click.pass_context
    @handle_errors("cat")
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
        from ember.entrypoints.cli import _load_config, get_ember_repo_root

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

    @click.command()
    @click.argument("index", type=int)
    @click.pass_context
    @handle_errors("open")
    def open_result(ctx: click.Context, index: int) -> None:
        """Open search result in editor.

        Opens file at the correct line in $EDITOR.
        Can be run from any subdirectory within the repository.
        """
        from ember.entrypoints.cli import get_ember_repo_root

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
    cli_group.add_command(open_result, name="open")

    return find, search, cat, open_result
