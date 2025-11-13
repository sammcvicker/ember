"""Centralized color definitions for all Ember output.

Provides consistent color scheme across CLI commands, interactive search,
and all output modes. Supports both click-style colors and prompt_toolkit styles.
"""

from typing import Literal

# Type aliases for color values
ClickColor = Literal["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
HexColor = str  # Hex color code like "#00aaaa"


class EmberColors:
    """Centralized color palette for consistent output across Ember.

    Defines colors for all UI elements using both click-compatible named colors
    and hex codes for prompt_toolkit styles.
    """

    # === File Metadata Colors ===
    PATH_FG = "magenta"  # File paths
    PATH_HEX = "#ff00ff"  # Magenta in hex

    SYMBOL_FG = "red"  # Symbol names (functions, classes)
    SYMBOL_HEX = "#ffaa00"  # Orange/yellow in hex for better visibility

    LINE_NUMBER_FG = "white"  # Line numbers
    LINE_NUMBER_DIM = True  # Use dim style

    RANK_FG = "green"  # Result rank numbers [1], [2], etc.
    RANK_HEX = "#00ff00"

    SCORE_FG = "white"  # Relevance scores
    SCORE_DIM = True
    SCORE_HEX = "#888888"

    # === Status Message Colors ===
    SUCCESS_FG = "green"
    SUCCESS_HEX = "#00ff00"

    WARNING_FG = "yellow"
    WARNING_HEX = "#ffff00"

    ERROR_FG = "red"
    ERROR_HEX = "#ff0000"

    INFO_FG = "cyan"
    INFO_HEX = "#00ffff"

    # === UI Element Colors ===
    SEPARATOR_HEX = "#888888"  # Horizontal separators in TUI
    SELECTED_BG_HEX = "#444444"  # Selected item background
    DIMMED_HEX = "#888888"  # Dimmed text

    # === Code Context Colors ===
    # (For future syntax highlighting)
    KEYWORD_FG = "magenta"
    KEYWORD_HEX = "#ff00ff"

    STRING_FG = "green"
    STRING_HEX = "#00ff00"

    COMMENT_FG = "white"
    COMMENT_DIM = True
    COMMENT_HEX = "#888888"

    FUNCTION_FG = "blue"
    FUNCTION_HEX = "#0000ff"

    # === Helper Methods ===

    @staticmethod
    def get_prompt_toolkit_style() -> dict[str, str]:
        """Get style dictionary for prompt_toolkit Style.from_dict().

        Returns:
            Dictionary mapping style class names to style definitions.

        Example:
            from prompt_toolkit.styles import Style
            style = Style.from_dict(EmberColors.get_prompt_toolkit_style())
        """
        return {
            "separator": f"fg:{EmberColors.SEPARATOR_HEX}",
            "selected": f"bg:{EmberColors.SELECTED_BG_HEX}",
            "dimmed": f"fg:{EmberColors.DIMMED_HEX}",
            "score": f"fg:{EmberColors.SCORE_HEX}",
            "path": f"fg:{EmberColors.PATH_HEX}",
            "symbol": f"fg:{EmberColors.SYMBOL_HEX}",
            "status": "bold",
            "rank": f"fg:{EmberColors.RANK_HEX}",
        }

    @staticmethod
    def click_path(text: str, bold: bool = True) -> str:
        """Style file path text for click output.

        Args:
            text: Text to style.
            bold: Whether to make text bold.

        Returns:
            Styled text using click.style().
        """
        import click
        return click.style(text, fg=EmberColors.PATH_FG, bold=bold)

    @staticmethod
    def click_symbol(text: str, bold: bool = True) -> str:
        """Style symbol text for click output.

        Args:
            text: Text to style.
            bold: Whether to make text bold.

        Returns:
            Styled text using click.style().
        """
        import click
        return click.style(text, fg=EmberColors.SYMBOL_FG, bold=bold)

    @staticmethod
    def click_rank(text: str, bold: bool = True) -> str:
        """Style rank text for click output.

        Args:
            text: Text to style.
            bold: Whether to make text bold.

        Returns:
            Styled text using click.style().
        """
        import click
        return click.style(text, fg=EmberColors.RANK_FG, bold=bold)

    @staticmethod
    def click_line_number(text: str) -> str:
        """Style line number text for click output.

        Args:
            text: Text to style.

        Returns:
            Styled text using click.style() with dim effect.
        """
        import click
        return click.style(text, fg=EmberColors.LINE_NUMBER_FG, dim=EmberColors.LINE_NUMBER_DIM)

    @staticmethod
    def click_warning(text: str) -> str:
        """Style warning text for click output.

        Args:
            text: Text to style.

        Returns:
            Styled text using click.style().
        """
        import click
        return click.style(text, fg=EmberColors.WARNING_FG)

    @staticmethod
    def click_error(text: str) -> str:
        """Style error text for click output.

        Args:
            text: Text to style.

        Returns:
            Styled text using click.style().
        """
        import click
        return click.style(text, fg=EmberColors.ERROR_FG)

    @staticmethod
    def click_success(text: str) -> str:
        """Style success text for click output.

        Args:
            text: Text to style.

        Returns:
            Styled text using click.style().
        """
        import click
        return click.style(text, fg=EmberColors.SUCCESS_FG)

    @staticmethod
    def click_dimmed(text: str) -> str:
        """Style dimmed text for click output.

        Args:
            text: Text to style.

        Returns:
            Styled text using click.style() with dim effect.
        """
        import click
        return click.style(text, dim=True)


def highlight_symbol(text: str, symbol: str | None) -> str:
    """Highlight all occurrences of symbol in text.

    Args:
        text: Text to search for symbol.
        symbol: Symbol to highlight (or None).

    Returns:
        Text with symbol highlighted using centralized color.
    """
    if not symbol or symbol not in text:
        return text

    # Find and highlight all occurrences of the symbol
    parts = []
    remaining = text
    while symbol in remaining:
        idx = remaining.index(symbol)
        # Add text before symbol
        parts.append(remaining[:idx])
        # Add highlighted symbol using centralized color
        parts.append(EmberColors.click_symbol(symbol))
        # Continue with text after symbol
        remaining = remaining[idx + len(symbol) :]
    # Add any remaining text
    parts.append(remaining)
    return "".join(parts)
