"""CLI error handling with actionable hints.

Provides consistent error formatting and common error factory functions
for all ember CLI commands.
"""

from typing import NoReturn

import click


class EmberCliError(click.ClickException):
    """CLI error with actionable hint for users.

    Provides consistent error formatting across all ember commands with
    optional hints that guide users toward resolving the issue.

    Attributes:
        message: The primary error message.
        hint: Optional actionable suggestion for the user.

    Example:
        raise EmberCliError(
            "Not in an ember repository",
            hint="Run 'ember init' in your project root to initialize one"
        )
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        """Initialize the error with message and optional hint.

        Args:
            message: The primary error message.
            hint: Optional actionable suggestion for the user.
        """
        super().__init__(message)
        self.hint = hint

    def format_message(self) -> str:
        """Format the error message with hint if present.

        Returns:
            Formatted error message, with hint on a new line if provided.
        """
        msg = self.message
        if self.hint:
            msg += f"\nHint: {self.hint}"
        return msg


def repo_not_found_error() -> NoReturn:
    """Raise error when not in an ember repository.

    Raises:
        EmberCliError: Always raises with repo initialization hint.
    """
    raise EmberCliError(
        "Not in an ember repository",
        hint="Run 'ember init' in your project root to initialize one",
    )


def no_search_results_error() -> NoReturn:
    """Raise error when no cached search results exist.

    Raises:
        EmberCliError: Always raises with search hint.
    """
    raise EmberCliError(
        "No recent search results found",
        hint="Run 'ember find <query>' first, then use 'ember cat <index>'",
    )


def path_not_in_repo_error(path: str) -> NoReturn:
    """Raise error when path is outside repository.

    Args:
        path: The path that was outside the repository.

    Raises:
        EmberCliError: Always raises with path context.
    """
    raise EmberCliError(
        f"Path '{path}' is not within repository",
        hint="Specify a path relative to or within the repository root",
    )


def index_out_of_range_error(index: int, max_index: int) -> NoReturn:
    """Raise error when result index is out of range.

    Args:
        index: The invalid index provided.
        max_index: The maximum valid index.

    Raises:
        EmberCliError: Always raises with valid range hint.
    """
    raise EmberCliError(
        f"Index {index} out of range (valid: 1-{max_index})",
        hint="Run 'ember find <query>' to see available results",
    )
