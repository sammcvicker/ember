"""Ember CLI entrypoint.

Command-line interface for Ember code search tool.
"""

import sys

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="ember")
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
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize Ember in the current directory.

    Creates .ember/ directory with configuration and database.
    """
    click.echo("init command - not yet implemented")
    click.echo("This will create .ember/ directory with:")
    click.echo("  - config.toml (configuration)")
    click.echo("  - index.db (SQLite database)")
    click.echo("  - state.json (indexing state)")


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
    click.echo("sync command - not yet implemented")
    mode = "worktree" if worktree else "staged" if staged else rev or "worktree"
    click.echo(f"Will index: {mode}")
    if reindex:
        click.echo("Full reindex requested")


@cli.command()
@click.argument("query", type=str)
@click.option(
    "--topk",
    "-k",
    type=int,
    default=20,
    help="Number of results to return.",
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
@click.pass_context
def find(
    ctx: click.Context,
    query: str,
    topk: int,
    json_output: bool,
    path_filter: str | None,
    lang_filter: str | None,
) -> None:
    """Search for code matching the query.

    Performs hybrid search (BM25 + semantic embeddings).
    """
    click.echo("find command - not yet implemented")
    click.echo(f"Query: {query}")
    click.echo(f"Top-k: {topk}")


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
    click.echo("cat command - not yet implemented")
    click.echo(f"Would show result #{index} with {context} lines of context")


@cli.command()
@click.argument("index", type=int)
@click.pass_context
def open_result(ctx: click.Context, index: int) -> None:
    """Open search result in editor.

    Opens file at the correct line in $EDITOR.
    """
    click.echo("open command - not yet implemented")
    click.echo(f"Would open result #{index} in $EDITOR")


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
