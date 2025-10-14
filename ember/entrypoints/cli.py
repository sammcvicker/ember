"""Ember CLI entrypoint.

Command-line interface for Ember code search tool.
"""

import sys
from pathlib import Path

import blake3
import click

from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
from ember.adapters.fs.local import LocalFileSystem
from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.git_cmd.git_adapter import GitAdapter
from ember.adapters.parsers.line_chunker import LineChunker
from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.file_repository import SQLiteFileRepository
from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.adapters.vss.simple_vector_search import SimpleVectorSearch
from ember.core.chunking.chunk_usecase import ChunkFileUseCase
from ember.core.config.init_usecase import InitRequest, InitUseCase
from ember.core.indexing.index_usecase import IndexingUseCase, IndexRequest
from ember.core.retrieval.search_usecase import SearchUseCase
from ember.domain.entities import Query


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
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Reinitialize even if .ember/ already exists.",
)
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """Initialize Ember in the current directory.

    Creates .ember/ directory with configuration and database.
    """
    repo_root = Path.cwd().resolve()

    # Create use case and execute
    use_case = InitUseCase(version="0.1.0")
    request = InitRequest(repo_root=repo_root, force=force)

    try:
        response = use_case.execute(request)

        # Report success
        if response.was_reinitialized:
            click.echo(f"Reinitialized existing ember index at {response.ember_dir}")
        else:
            click.echo(f"Initialized ember index at {response.ember_dir}")

        if not ctx.obj.get("quiet", False):
            click.echo(f"  ✓ Created {response.config_path.name}")
            click.echo(f"  ✓ Created {response.db_path.name}")
            click.echo(f"  ✓ Created {response.state_path.name}")
            click.echo("\nNext: Run 'ember sync' to index your codebase")

    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Use 'ember init --force' to reinitialize", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error initializing ember: {e}", err=True)
        sys.exit(1)


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
    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    db_path = ember_dir / "index.db"

    # Check if ember is initialized
    if not ember_dir.exists() or not db_path.exists():
        click.echo("Error: Ember not initialized in this directory", err=True)
        click.echo("Run 'ember init' first", err=True)
        sys.exit(1)

    # Determine sync mode
    if rev:
        sync_mode = rev
    elif staged:
        sync_mode = "staged"
    else:
        sync_mode = "worktree"

    if not ctx.obj.get("quiet", False):
        click.echo(f"Indexing {sync_mode}...")

    try:
        # Initialize dependencies
        vcs = GitAdapter(repo_root)
        fs = LocalFileSystem()
        embedder = JinaCodeEmbedder()

        # Initialize repositories
        chunk_repo = SQLiteChunkRepository(db_path)
        vector_repo = SQLiteVectorRepository(db_path)
        file_repo = SQLiteFileRepository(db_path)
        meta_repo = SQLiteMetaRepository(db_path)

        # Initialize chunking use case
        tree_sitter = TreeSitterChunker()
        line_chunker = LineChunker()
        chunk_usecase = ChunkFileUseCase(tree_sitter, line_chunker)

        # Compute project ID (hash of repo root path)
        project_id = blake3.blake3(str(repo_root).encode("utf-8")).hexdigest()

        # Create indexing use case
        indexing_usecase = IndexingUseCase(
            vcs=vcs,
            fs=fs,
            chunk_usecase=chunk_usecase,
            embedder=embedder,
            chunk_repo=chunk_repo,
            vector_repo=vector_repo,
            file_repo=file_repo,
            meta_repo=meta_repo,
            project_id=project_id,
        )

        # Execute indexing
        request = IndexRequest(
            repo_root=repo_root,
            sync_mode=sync_mode,
            path_filters=[],
            force_reindex=reindex,
        )

        response = indexing_usecase.execute(request)

        if not response.success:
            click.echo(f"Error during indexing: {response.error}", err=True)
            sys.exit(1)

        # Report results
        click.echo(f"✓ Indexed {response.files_indexed} files")
        click.echo(f"  • {response.chunks_created} chunks created")
        click.echo(f"  • {response.chunks_updated} chunks updated")
        click.echo(f"  • {response.vectors_stored} vectors stored")
        click.echo(f"  • Tree SHA: {response.tree_sha[:12]}...")

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error during sync: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


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
    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    db_path = ember_dir / "index.db"

    # Check if ember is initialized
    if not ember_dir.exists() or not db_path.exists():
        click.echo("Error: Ember not initialized in this directory", err=True)
        click.echo("Run 'ember init' first", err=True)
        sys.exit(1)

    try:
        # Initialize dependencies
        text_search = SQLiteFTS(db_path)
        vector_search = SimpleVectorSearch(db_path)
        chunk_repo = SQLiteChunkRepository(db_path)
        embedder = JinaCodeEmbedder()

        # Create search use case
        search_usecase = SearchUseCase(
            text_search=text_search,
            vector_search=vector_search,
            chunk_repo=chunk_repo,
            embedder=embedder,
        )

        # Create query object
        query_obj = Query(
            text=query,
            topk=topk,
            path_filter=path_filter,
            lang_filter=lang_filter,
            json_output=json_output,
        )

        # Execute search
        results = search_usecase.search(query_obj)

        # Display results
        if json_output:
            import json

            output = []
            for result in results:
                output.append(
                    {
                        "rank": result.rank,
                        "score": result.score,
                        "path": str(result.chunk.path),
                        "lang": result.chunk.lang,
                        "symbol": result.chunk.symbol,
                        "start_line": result.chunk.start_line,
                        "end_line": result.chunk.end_line,
                        "content": result.chunk.content,
                        "explanation": result.explanation,
                    }
                )
            click.echo(json.dumps(output, indent=2))
        else:
            # Human-readable output
            if not results:
                click.echo("No results found.")
                return

            click.echo(f"\nFound {len(results)} results:\n")

            for result in results:
                # Header with rank, path, symbol
                symbol_info = (
                    f" ({result.chunk.symbol})" if result.chunk.symbol else ""
                )
                click.echo(
                    f"{result.rank}. {result.chunk.path}:{result.chunk.start_line}{symbol_info}"
                )

                # Score info
                click.echo(
                    f"   Score: {result.score:.4f} "
                    f"(BM25: {result.explanation.get('bm25_score', 0):.4f}, "
                    f"Vector: {result.explanation.get('vector_score', 0):.4f})"
                )

                # Preview
                preview = result.preview or result.format_preview(max_lines=3)
                for line in preview.split("\n"):
                    click.echo(f"   {line}")

                click.echo()  # Blank line between results

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error during search: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


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
