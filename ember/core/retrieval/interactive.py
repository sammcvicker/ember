"""Interactive search use case.

Manages the state and flow of an interactive search session.
"""

from dataclasses import dataclass
from typing import Protocol

from ember.domain.entities import Query, SearchResult


class Searcher(Protocol):
    """Protocol for search operations."""

    def search(self, query: Query) -> list[SearchResult]:
        """Execute a search query.

        Args:
            query: Query object with search parameters.

        Returns:
            List of search results.
        """
        ...


@dataclass
class InteractiveSearchSession:
    """Manages state for an interactive search session."""

    query_text: str = ""
    current_results: list[SearchResult] | None = None
    selected_index: int = 0
    search_mode: str = "hybrid"  # hybrid, bm25, vector
    preview_visible: bool = True
    last_search_time_ms: float = 0.0
    error_message: str | None = None

    def update_query(self, text: str) -> None:
        """Update the query text.

        Args:
            text: New query text.
        """
        self.query_text = text
        self.selected_index = 0  # Reset selection when query changes

    def update_results(self, results: list[SearchResult], time_ms: float) -> None:
        """Update search results.

        Args:
            results: New search results.
            time_ms: Time taken for search in milliseconds.
        """
        self.current_results = results
        self.last_search_time_ms = time_ms
        self.selected_index = 0  # Reset selection when results change
        self.error_message = None  # Clear error on successful search

    def set_error(self, message: str) -> None:
        """Set an error message.

        Args:
            message: Error message to display.
        """
        self.error_message = message
        self.current_results = []  # Clear results on error
        self.last_search_time_ms = 0.0

    def select_next(self, wrap: bool = True) -> None:
        """Move to next result.

        Args:
            wrap: If True, wrap to first result after last.
        """
        if not self.current_results:
            return

        self.selected_index += 1
        if self.selected_index >= len(self.current_results):
            self.selected_index = 0 if wrap else len(self.current_results) - 1

    def select_previous(self, wrap: bool = True) -> None:
        """Move to previous result.

        Args:
            wrap: If True, wrap to last result after first.
        """
        if not self.current_results:
            return

        self.selected_index -= 1
        if self.selected_index < 0:
            self.selected_index = len(self.current_results) - 1 if wrap else 0

    def page_down(self, page_size: int = 10) -> None:
        """Jump down by page_size results.

        Args:
            page_size: Number of results to skip.
        """
        if not self.current_results:
            return

        self.selected_index = min(
            self.selected_index + page_size,
            len(self.current_results) - 1
        )

    def page_up(self, page_size: int = 10) -> None:
        """Jump up by page_size results.

        Args:
            page_size: Number of results to skip.
        """
        if not self.current_results:
            return

        self.selected_index = max(self.selected_index - page_size, 0)

    def cycle_search_mode(self) -> None:
        """Cycle through search modes: hybrid -> bm25 -> vector -> hybrid."""
        modes = ["hybrid", "bm25", "vector"]
        current_idx = modes.index(self.search_mode)
        self.search_mode = modes[(current_idx + 1) % len(modes)]

    def toggle_preview(self) -> None:
        """Toggle preview pane visibility."""
        self.preview_visible = not self.preview_visible

    def get_selected_result(self) -> SearchResult | None:
        """Get currently selected result.

        Returns:
            Selected result or None if no results.
        """
        if not self.current_results or self.selected_index >= len(self.current_results):
            return None
        return self.current_results[self.selected_index]
