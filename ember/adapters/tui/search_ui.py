"""Main interactive search UI controller.

Implements an fzf-style interactive search interface using prompt_toolkit.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import (
    ConditionalContainer,
    Dimension,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style

from ember.core.presentation.colors import EmberColors, render_syntax_highlighted
from ember.core.retrieval.interactive import InteractiveSearchSession
from ember.domain.config import EmberConfig
from ember.domain.entities import Query, SearchResult


class InteractiveSearchUI:
    """Interactive search UI using prompt_toolkit."""

    def __init__(
        self,
        search_fn: Callable[[Query], list[SearchResult]],
        config: EmberConfig,
        initial_query: str = "",
        topk: int = 20,
        path_filter: str | None = None,
        lang_filter: str | None = None,
        show_scores: bool = True,
        show_preview: bool = True,
        min_query_length: int = 2,
        debounce_ms: int = 150,
    ):
        """Initialize interactive search UI.

        Args:
            search_fn: Function to execute searches.
            config: Ember configuration (for display settings).
            initial_query: Initial search query.
            topk: Maximum number of results to show.
            path_filter: Optional path glob filter.
            lang_filter: Optional language filter.
            show_scores: Whether to show relevance scores.
            show_preview: Whether to show preview pane by default.
            min_query_length: Minimum query length before searching.
            debounce_ms: Debounce delay in milliseconds.
        """
        self.search_fn = search_fn
        self.config = config
        self.topk = topk
        self.path_filter = path_filter
        self.lang_filter = lang_filter
        self.show_scores = show_scores
        self.min_query_length = min_query_length
        self.debounce_ms = debounce_ms / 1000.0  # Convert to seconds

        # Session state
        self.session = InteractiveSearchSession(
            query_text=initial_query,
            preview_visible=show_preview,
        )

        # Search task management
        self.current_search_task: asyncio.Task | None = None
        self.debounce_task: asyncio.Task | None = None

        # UI state
        self.selected_file: Path | None = None
        self.selected_line: int | None = None
        self.should_exit = False

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the prompt_toolkit UI layout."""
        # Query input buffer
        self.query_buffer = Buffer(
            multiline=False,
            on_text_changed=self._on_query_changed,
        )
        self.query_buffer.text = self.session.query_text

        # Key bindings
        kb = self._create_key_bindings()

        # Layout components
        query_window = Window(
            content=BufferControl(buffer=self.query_buffer),
            height=Dimension.exact(1),
        )

        results_window = Window(
            content=FormattedTextControl(
                self._get_results_text,
                focusable=False,
            ),
            wrap_lines=False,
        )

        preview_window = Window(
            content=FormattedTextControl(
                self._get_preview_text,
                focusable=False,
            ),
            wrap_lines=True,
        )

        status_window = Window(
            content=FormattedTextControl(
                self._get_status_text,
                focusable=False,
            ),
            height=Dimension.exact(1),
        )

        # Main layout
        @Condition
        def preview_visible() -> bool:
            return self.session.preview_visible

        main_container = HSplit([
            Window(height=Dimension.exact(1), char="─", style="class:separator"),
            VSplit([
                Window(width=Dimension.exact(2), char=" "),
                query_window,
            ]),
            Window(height=Dimension.exact(1), char="─", style="class:separator"),
            results_window,
            ConditionalContainer(
                Window(
                    height=Dimension.exact(1),
                    char="─",
                    style="class:separator",
                ),
                filter=preview_visible,
            ),
            ConditionalContainer(
                Window(
                    content=preview_window.content,
                    wrap_lines=True,
                ),
                filter=preview_visible,
            ),
            Window(height=Dimension.exact(1), char="─", style="class:separator"),
            status_window,
        ])

        # Style - use centralized color palette
        style = Style.from_dict(EmberColors.get_prompt_toolkit_style())

        # Application
        self.app: Application[Any] = Application(
            layout=Layout(main_container),
            key_bindings=kb,
            style=style,
            full_screen=True,
            mouse_support=False,
        )

    def _create_key_bindings(self) -> KeyBindings:
        """Create key bindings for the UI.

        Returns:
            KeyBindings object.
        """
        kb = KeyBindings()

        # Navigation
        @kb.add("c-n")
        @kb.add("down")
        def next_result(event: KeyPressEvent) -> None:
            self.session.select_next()
            self.app.invalidate()

        @kb.add("c-p")
        @kb.add("up")
        def previous_result(event: KeyPressEvent) -> None:
            self.session.select_previous()
            self.app.invalidate()

        @kb.add("c-d")
        def page_down(event: KeyPressEvent) -> None:
            self.session.page_down()
            self.app.invalidate()

        @kb.add("c-u")
        def page_up(event: KeyPressEvent) -> None:
            self.session.page_up()
            self.app.invalidate()

        # Actions
        @kb.add("enter")
        def open_file(event: KeyPressEvent) -> None:
            result = self.session.get_selected_result()
            if result:
                self.selected_file = Path(result.chunk.path)
                self.selected_line = result.chunk.start_line
                self.should_exit = True
                event.app.exit()

        @kb.add("c-v")
        def toggle_preview(event: KeyPressEvent) -> None:
            self.session.toggle_preview()
            self.app.invalidate()

        @kb.add("c-r")
        def cycle_mode(event: KeyPressEvent) -> None:
            self.session.cycle_search_mode()
            # Trigger new search with new mode
            if event.app.loop:
                event.app.loop.create_task(self._execute_search())

        # Exit
        @kb.add("escape")
        @kb.add("c-c")
        def exit_app(event: KeyPressEvent) -> None:
            self.should_exit = False
            event.app.exit()

        return kb

    def _on_query_changed(self, buffer: Buffer) -> None:
        """Handle query text changes.

        Args:
            buffer: The query buffer.
        """
        self.session.update_query(buffer.text)

        # Cancel existing debounce task
        if self.debounce_task and not self.debounce_task.done():
            self.debounce_task.cancel()

        # Start new debounce task - schedule it in the app's event loop
        async def debounced_search() -> None:
            try:
                await asyncio.sleep(self.debounce_ms)
                await self._execute_search()
            except asyncio.CancelledError:
                pass

        # Get the event loop from the app
        if hasattr(self, 'app') and self.app:
            loop = self.app.loop
            if loop:
                self.debounce_task = loop.create_task(debounced_search())

    async def _execute_search(self) -> None:
        """Execute search with current query."""
        # Cancel existing search
        if self.current_search_task and not self.current_search_task.done():
            self.current_search_task.cancel()

        # Check minimum query length
        if len(self.session.query_text) < self.min_query_length:
            self.session.update_results([], 0.0)
            self.app.invalidate()
            return

        # Execute search
        async def search_task() -> None:
            try:
                start_time = time.time()

                # Create query object
                query = Query(
                    text=self.session.query_text,
                    topk=self.topk,
                    path_filter=self.path_filter,
                    lang_filter=self.lang_filter,
                    json_output=False,
                )

                # Run search (synchronous function in executor)
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(None, self.search_fn, query)

                # Update session
                elapsed_ms = (time.time() - start_time) * 1000
                self.session.update_results(results, elapsed_ms)
                self.app.invalidate()

            except asyncio.CancelledError:
                pass
            except Exception as e:
                # Extract meaningful error message
                error_msg = str(e) if str(e) else type(e).__name__
                self.session.set_error(f"Search error: {error_msg}")
                self.app.invalidate()

        self.current_search_task = asyncio.create_task(search_task())

    def _get_results_text(self) -> list[tuple[str, str]]:
        """Get formatted results text.

        Returns:
            List of (style, text) tuples for formatted text.
        """
        if not self.session.query_text:
            return [("", "Type to search...")]

        if len(self.session.query_text) < self.min_query_length:
            return [("", f"Type {self.min_query_length - len(self.session.query_text)} more character(s)...")]

        # Show error message if one exists
        if self.session.error_message:
            return [("class:error", self.session.error_message)]

        if not self.session.current_results:
            return [("", "No results found")]

        lines: list[tuple[str, str]] = []

        for idx, result in enumerate(self.session.current_results):
            style = "class:selected" if idx == self.session.selected_index else ""

            # Format: path:lines (symbol) | score
            chunk = result.chunk
            path = chunk.path
            line_range = f"{chunk.start_line}-{chunk.end_line}"
            symbol = f" ({chunk.symbol})" if chunk.symbol else ""

            result_text = f"  {path}:{line_range}{symbol}"

            if self.show_scores:
                score = f" │ {result.score:.3f}" if result.score else ""
                result_text += score

            lines.append((style, result_text + "\n"))

        return lines

    def _get_preview_text(self) -> list[tuple[str, str]]:
        """Get formatted preview text with optional syntax highlighting.

        Returns:
            List of (style, text) tuples for formatted text.
        """
        result = self.session.get_selected_result()
        if not result:
            return [("", "")]

        chunk = result.chunk

        # Apply syntax highlighting if enabled in config
        if self.config.display.syntax_highlighting:
            try:
                # Use render_syntax_highlighted to get ANSI-formatted code
                highlighted = render_syntax_highlighted(
                    code=chunk.content,
                    file_path=Path(chunk.path),
                    start_line=chunk.start_line,
                    theme=self.config.display.theme,
                )
                # Convert ANSI escape codes to prompt_toolkit formatted text
                # ANSI class wraps the ANSI string, then to_formatted_text converts it
                # to a list of (style, text) tuples that prompt_toolkit can render
                ansi_obj = ANSI(highlighted)
                return to_formatted_text(ansi_obj)
            except Exception:
                # Fall back to plain text if highlighting fails
                pass

        # Plain text fallback (no highlighting or on error)
        lines: list[tuple[str, str]] = []
        content_lines = chunk.content.splitlines()
        for i, line in enumerate(content_lines):
            line_num = chunk.start_line + i
            lines.append(("", f"{line_num:5} │ {line}\n"))

        return lines

    def _get_status_text(self) -> list[tuple[str, str]]:
        """Get formatted status bar text.

        Returns:
            List of (style, text) tuples for formatted text.
        """
        parts: list[tuple[str, str]] = []

        # Left side: result count and timing
        if self.session.current_results is not None:
            count = len(self.session.current_results)
            time_ms = int(self.session.last_search_time_ms)
            parts.append(("class:status", f" {count} results in {time_ms}ms"))
        else:
            parts.append(("class:status", " Ready"))

        # Search mode
        parts.append(("", f" │ mode: {self.session.search_mode}"))

        # Right side: keybinding hints
        parts.append(("class:dimmed", " │ "))
        parts.append(("class:dimmed", "↑↓:navigate enter:open esc:quit"))

        return parts

    async def run_async(self) -> tuple[Path | None, int | None]:
        """Run the interactive search UI asynchronously.

        Returns:
            Tuple of (selected_file, selected_line) or (None, None) if cancelled.
        """
        # Run initial search if query provided
        if self.session.query_text and len(self.session.query_text) >= self.min_query_length:
            # Schedule initial search
            asyncio.create_task(self._execute_search())

        # Run application
        await self.app.run_async()

        if self.should_exit and self.selected_file:
            return (self.selected_file, self.selected_line)
        return (None, None)

    def run(self) -> tuple[Path | None, int | None]:
        """Run the interactive search UI.

        Suppresses all logging output during TUI execution to prevent display
        corruption, then restores original logging state after exit.

        Returns:
            Tuple of (selected_file, selected_line) or (None, None) if cancelled.
        """
        # Disable all logging during TUI to prevent corrupting the display
        # prompt_toolkit runs in full-screen mode, so any stderr output
        # (including logging) will corrupt the UI
        logging.disable(logging.CRITICAL)
        try:
            return asyncio.run(self.run_async())
        finally:
            # Restore logging to original state
            logging.disable(logging.NOTSET)
