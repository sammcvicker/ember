"""Result display utilities for CLI commands.

Handles formatting headers and displaying content with context and
syntax highlighting.
"""

from pathlib import Path
from typing import Any

import click

from ember.core.presentation.colors import EmberColors


def format_result_header(
    result: dict[str, Any], index: int | None = None, show_symbol: bool = True
) -> None:
    """Print result header in consistent ripgrep-style format.

    Args:
        result: Result dictionary with path, start_line, symbol fields.
        index: Optional 1-based result index (rank). If None, rank is not shown.
        show_symbol: Whether to display symbol in header.
    """
    # Filename using centralized color
    click.echo(EmberColors.click_path(str(result["path"])))

    # Build second line: optional rank, line number, optional symbol
    line_num = EmberColors.click_line_number(f"{result['start_line']}")

    # Symbol using centralized color (inline)
    symbol_display = ""
    if show_symbol and result.get("symbol"):
        symbol_display = " " + EmberColors.click_symbol(f"({result['symbol']})")

    if index is not None:
        # Show rank when index is provided
        rank = EmberColors.click_rank(f"[{index}]")
        click.echo(f"{rank} {line_num}:{symbol_display}")
    else:
        # No rank for hash-based lookups
        click.echo(f"{line_num}:{symbol_display}")


def display_content_with_context(
    result: dict[str, Any],
    context: int,
    repo_root: Path,
) -> bool:
    """Display chunk content with surrounding context lines.

    Args:
        result: Result dictionary with path, start_line, end_line, content.
        context: Number of lines to show before and after the chunk.
        repo_root: Repository root for resolving file paths.

    Returns:
        True if content was displayed successfully, False if fallback needed.
    """
    file_path = repo_root / result["path"]
    if not file_path.exists():
        click.echo(
            f"Warning: File {result['path']} not found, showing chunk only", err=True
        )
        return False

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
                click.echo(click.style(f"{line_num:5} | {line_content}", dim=True))
        return True
    except Exception as e:
        click.echo(
            f"Warning: Could not read context from {result['path']}: {e}", err=True
        )
        return False


def display_content_with_highlighting(
    result: dict[str, Any],
    config: Any,
    verbose: bool = False,
) -> None:
    """Display chunk content with optional syntax highlighting.

    Args:
        result: Result dictionary with path, start_line, content.
        config: EmberConfig with display settings.
        verbose: Whether to show warning messages on highlighting failure.
    """
    from ember.core.presentation.colors import render_syntax_highlighted

    content = result["content"]

    if config.display.syntax_highlighting:
        try:
            highlighted = render_syntax_highlighted(
                code=content,
                file_path=Path(result["path"]),
                start_line=result["start_line"],
                theme=config.display.theme,
            )
            click.echo(highlighted)
        except Exception as e:
            # Fallback to plain text if highlighting fails
            if verbose:
                click.echo(f"Warning: Syntax highlighting failed: {e}", err=True)
            click.echo(content)
    else:
        # Just display plain content
        click.echo(content)
