"""Ember CLI entrypoint.

Command-line interface for Ember code search tool.
"""

import sys
from pathlib import Path

import blake3
import click
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn


class RichProgressCallback:
    """Rich-based progress callback for visual progress reporting.

    Uses Rich library to display a progress bar that updates as indexing progresses.
    """

    def __init__(self, progress: Progress) -> None:
        """Initialize with a Rich Progress instance.

        Args:
            progress: Rich Progress instance to use for display.
        """
        self.progress = progress
        self.task_id: int | None = None

    def on_start(self, total: int, description: str) -> None:
        """Create progress bar when operation starts."""
        # Use transient=True to auto-hide when complete
        self.task_id = self.progress.add_task(description, total=total)

    def on_progress(self, current: int, item_description: str | None = None) -> None:
        """Update progress bar with current item."""
        if self.task_id is not None:
            # Update the task description to show current file
            if item_description:
                self.progress.update(
                    self.task_id, completed=current, description=f"[cyan]{item_description}"
                )
            else:
                self.progress.update(self.task_id, completed=current)

    def on_complete(self) -> None:
        """Mark progress as complete and hide it."""
        if self.task_id is not None:
            # Remove the task to hide the progress bar
            self.progress.remove_task(self.task_id)


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
    # Lazy import - only load when init is actually called
    from ember.core.config.init_usecase import InitRequest, InitUseCase

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

    try:
        # Lazy imports - only load heavy dependencies when sync is actually called
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
        from ember.adapters.fs.local import LocalFileSystem
        from ember.adapters.git_cmd.git_adapter import GitAdapter
        from ember.adapters.parsers.line_chunker import LineChunker
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
        from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
        from ember.adapters.sqlite.file_repository import SQLiteFileRepository
        from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
        from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
        from ember.core.chunking.chunk_usecase import ChunkFileUseCase
        from ember.core.indexing.index_usecase import IndexingUseCase, IndexRequest

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

        # Execute indexing with progress reporting (unless quiet mode)
        request = IndexRequest(
            repo_root=repo_root,
            sync_mode=sync_mode,
            path_filters=[],
            force_reindex=reindex,
        )

        # Use progress bar unless in quiet mode
        if ctx.obj.get("quiet", False):
            # No progress reporting in quiet mode
            response = indexing_usecase.execute(request)
        else:
            # Create Rich progress bar (transient=True makes it disappear when done)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                transient=True,
            ) as progress:
                callback = RichProgressCallback(progress)
                response = indexing_usecase.execute(request, progress=callback)

        if not response.success:
            click.echo(f"Error during indexing: {response.error}", err=True)
            sys.exit(1)

        # Report results
        sync_type = "incremental" if response.is_incremental else "full"

        if response.files_indexed == 0 and response.chunks_deleted == 0:
            click.echo("✓ No changes detected (index up to date)")
        else:
            click.echo(f"✓ Indexed {response.files_indexed} files ({sync_type} sync)")

        if response.chunks_created > 0:
            click.echo(f"  • {response.chunks_created} chunks created")
        if response.chunks_updated > 0:
            click.echo(f"  • {response.chunks_updated} chunks updated")
        if response.chunks_deleted > 0:
            click.echo(f"  • {response.chunks_deleted} chunks deleted")
        if response.vectors_stored > 0:
            click.echo(f"  • {response.vectors_stored} vectors stored")
        if response.files_indexed > 0 or response.chunks_deleted > 0:
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
        # Lazy imports - only load heavy dependencies when find is actually called
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
        from ember.adapters.fts.sqlite_fts import SQLiteFTS
        from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
        from ember.adapters.vss.simple_vector_search import SimpleVectorSearch
        from ember.core.retrieval.search_usecase import SearchUseCase
        from ember.domain.entities import Query

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

        # Cache results for cat/open commands
        cache_path = ember_dir / ".last_search.json"
        try:
            import json

            cache_data = {
                "query": query,
                "results": [
                    {
                        "rank": result.rank,
                        "score": result.score,
                        "path": str(result.chunk.path),
                        "lang": result.chunk.lang,
                        "symbol": result.chunk.symbol,
                        "start_line": result.chunk.start_line,
                        "end_line": result.chunk.end_line,
                        "content": result.chunk.content,
                        "chunk_id": result.chunk.id,
                        "tree_sha": result.chunk.tree_sha,
                        "explanation": result.explanation,
                    }
                    for result in results
                ],
            }
            cache_path.write_text(json.dumps(cache_data, indent=2))
        except Exception as e:
            # Log cache errors but don't fail the command
            if ctx.obj.get("verbose", False):
                click.echo(f"Warning: Could not cache results: {e}", err=True)

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
            # Human-readable output (ripgrep-style)
            if not results:
                click.echo("No results found.")
                return

            # Group results by file path for cleaner output
            from collections import defaultdict

            results_by_file = defaultdict(list)
            for result in results:
                results_by_file[result.chunk.path].append(result)

            # Display grouped results
            for file_path, file_results in results_by_file.items():
                # Print filename in magenta
                click.echo(click.style(str(file_path), fg="magenta", bold=True))

                for result in file_results:
                    # Format: [rank] line_number: content
                    # Rank in green (what users reference for cat/open)
                    rank = click.style(f"[{result.rank}]", fg="green", bold=True)
                    # Line number in dim gray (informational)
                    line_num = click.style(
                        f"{result.chunk.start_line}", dim=True
                    )

                    # Get preview content (first line only for compact display)
                    preview = result.preview or result.format_preview(max_lines=1)
                    content_lines = preview.split("\n")

                    # Helper function to highlight symbol in text
                    def highlight_symbol(text: str, symbol: str | None) -> str:
                        if not symbol or symbol not in text:
                            return text

                        # Find and highlight all occurrences of the symbol
                        parts = []
                        remaining = text
                        while symbol in remaining:
                            idx = remaining.index(symbol)
                            # Add text before symbol
                            parts.append(remaining[:idx])
                            # Add highlighted symbol
                            parts.append(click.style(symbol, fg="red", bold=True))
                            # Continue with text after symbol
                            remaining = remaining[idx + len(symbol):]
                        # Add any remaining text
                        parts.append(remaining)
                        return "".join(parts)

                    # First line with rank and line number
                    if content_lines:
                        first_line = highlight_symbol(
                            content_lines[0], result.chunk.symbol
                        )
                        click.echo(f"{rank} {line_num}:{first_line}")

                        # Additional preview lines (indented, no line number)
                        for line in content_lines[1:]:
                            if line.strip():  # Skip empty lines
                                highlighted_line = highlight_symbol(
                                    line, result.chunk.symbol
                                )
                                click.echo(f"    {highlighted_line}")

                # Blank line between files
                click.echo()

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
    import json

    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    cache_path = ember_dir / ".last_search.json"

    # Check if cache exists
    if not cache_path.exists():
        click.echo("Error: No recent search results found", err=True)
        click.echo("Run 'ember find <query>' first", err=True)
        sys.exit(1)

    try:
        # Load cached results
        cache_data = json.loads(cache_path.read_text())
        results = cache_data.get("results", [])

        if not results:
            click.echo("Error: No results in cache", err=True)
            sys.exit(1)

        # Validate index (1-based)
        if index < 1 or index > len(results):
            click.echo(
                f"Error: Index {index} out of range (1-{len(results)})", err=True
            )
            sys.exit(1)

        # Get the result (convert to 0-based)
        result = results[index - 1]

        # Display header in ripgrep-style
        path = result["path"]

        # Filename in magenta bold
        click.echo(click.style(str(path), fg="magenta", bold=True))

        # Rank in green bold, line number dimmed
        rank = click.style(f"[{index}]", fg="green", bold=True)
        line_num = click.style(f"{result['start_line']}", dim=True)

        # Symbol in red bold (inline)
        symbol_display = ""
        if result.get("symbol"):
            symbol_display = " " + click.style(
                f"({result['symbol']})", fg="red", bold=True
            )

        click.echo(f"{rank} {line_num}:{symbol_display}")
        click.echo(
            click.style(
                f"Lines {result['start_line']}-{result['end_line']} "
                f"({result['lang'] or 'text'})",
                dim=True
            )
        )
        click.echo()

        # Get chunk content
        content = result["content"]

        # If context requested, read file and show surrounding lines
        if context > 0:
            file_path = repo_root / path
            if file_path.exists():
                try:
                    file_lines = file_path.read_text(errors="replace").splitlines()
                    start_line = result["start_line"]
                    end_line = result["end_line"]

                    # Calculate context range (1-based line numbers)
                    context_start = max(1, start_line - context)
                    context_end = min(len(file_lines), end_line + context)

                    # Display with line numbers
                    for line_num in range(context_start, context_end + 1):
                        line_content = file_lines[line_num - 1]  # Convert to 0-based
                        # Highlight the chunk lines
                        if start_line <= line_num <= end_line:
                            click.echo(f"{line_num:5} | {line_content}")
                        else:
                            click.echo(
                                click.style(f"{line_num:5} | {line_content}", dim=True)
                            )
                except Exception as e:
                    # Fall back to just chunk content if file read fails
                    click.echo(
                        f"Warning: Could not read context from {path}: {e}", err=True
                    )
                    click.echo(content)
            else:
                click.echo(
                    f"Warning: File {path} not found, showing chunk only", err=True
                )
                click.echo(content)
        else:
            # Just display the chunk content
            click.echo(content)

        click.echo()

    except json.JSONDecodeError:
        click.echo("Error: Corrupted search cache", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument("index", type=int)
@click.pass_context
def open_result(ctx: click.Context, index: int) -> None:
    """Open search result in editor.

    Opens file at the correct line in $EDITOR.
    """
    import json
    import os
    import subprocess

    repo_root = Path.cwd().resolve()
    ember_dir = repo_root / ".ember"
    cache_path = ember_dir / ".last_search.json"

    # Check if cache exists
    if not cache_path.exists():
        click.echo("Error: No recent search results found", err=True)
        click.echo("Run 'ember find <query>' first", err=True)
        sys.exit(1)

    try:
        # Load cached results
        cache_data = json.loads(cache_path.read_text())
        results = cache_data.get("results", [])

        if not results:
            click.echo("Error: No results in cache", err=True)
            sys.exit(1)

        # Validate index (1-based)
        if index < 1 or index > len(results):
            click.echo(
                f"Error: Index {index} out of range (1-{len(results)})", err=True
            )
            sys.exit(1)

        # Get the result (convert to 0-based)
        result = results[index - 1]

        # Build absolute file path
        file_path = repo_root / result["path"]

        # Check if file exists
        if not file_path.exists():
            click.echo(f"Error: File not found: {result['path']}", err=True)
            sys.exit(1)

        # Determine which editor to use
        # Priority: $VISUAL > $EDITOR > vim (fallback)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"

        # Build editor command with line number
        # Different editors have different syntax for opening at a line
        editor_name = Path(editor).name.lower()
        line_num = result["start_line"]

        if editor_name in ("vim", "vi", "nvim", "nano"):
            # vim/vi/nvim/nano: +line syntax
            cmd = [editor, f"+{line_num}", str(file_path)]
        elif editor_name in ("emacs", "emacsclient"):
            # emacs: +line syntax
            cmd = [editor, f"+{line_num}", str(file_path)]
        elif editor_name in ("code", "vscode"):
            # VS Code: --goto file:line syntax
            cmd = [editor, "--goto", f"{file_path}:{line_num}"]
        elif editor_name == "subl":
            # Sublime Text: file:line syntax
            cmd = [editor, f"{file_path}:{line_num}"]
        elif editor_name == "atom":
            # Atom: file:line syntax
            cmd = [editor, f"{file_path}:{line_num}"]
        else:
            # Unknown editor: try vim-style +line syntax
            cmd = [editor, f"+{line_num}", str(file_path)]

        # Show what we're doing (if not quiet)
        if not ctx.obj.get("quiet", False):
            # Use consistent ripgrep-style formatting
            path_display = click.style(str(result['path']), fg="magenta", bold=True)
            rank_display = click.style(f"[{index}]", fg="green", bold=True)
            line_display = click.style(f"{line_num}", dim=True)

            symbol_display = ""
            if result.get("symbol"):
                symbol_display = " " + click.style(
                    f"({result['symbol']})", fg="red", bold=True
                )

            click.echo(f"Opening {path_display} {rank_display} {line_display}:{symbol_display} in {editor}")

        # Execute editor command
        subprocess.run(cmd, check=True)

    except json.JSONDecodeError:
        click.echo("Error: Corrupted search cache", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error: Failed to open editor: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo(f"Error: Editor '{editor}' not found", err=True)
        click.echo("Set $EDITOR or $VISUAL environment variable", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.obj.get("verbose", False):
            import traceback

            traceback.print_exc()
        sys.exit(1)


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
