"""Centralized color definitions for all Ember output.

Provides consistent color scheme across CLI commands, interactive search,
and all output modes. Supports both click-style colors and prompt_toolkit styles.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pygments.lexer import Lexer
    from pygments.token import _TokenType

# Type aliases for color values
ClickColor = Literal["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
HexColor = str  # Hex color code like "#00aaaa"


class AnsiCodes:
    """ANSI escape codes for terminal coloring.

    Provides named constants for ANSI escape sequences instead of magic strings.
    Uses standard 16-color palette that adapts to terminal themes.
    """

    RESET = "\x1b[0m"
    DIM = "\x1b[2m"

    # Foreground colors (90-97 are bright variants)
    DARK_GRAY = "\x1b[90m"
    GREEN = "\x1b[92m"
    BLUE = "\x1b[94m"
    MAGENTA = "\x1b[95m"
    CYAN = "\x1b[96m"
    WHITE = "\x1b[97m"


# File extension to Pygments lexer name mapping
EXTENSION_TO_LEXER: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".sql": "sql",
}


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

        Uses ANSI color names instead of hex codes so colors adapt to the
        user's terminal theme (Solarized, Dracula, etc.).

        Returns:
            Dictionary mapping style class names to style definitions.

        Example:
            from prompt_toolkit.styles import Style
            style = Style.from_dict(EmberColors.get_prompt_toolkit_style())
        """
        return {
            "separator": "fg:ansibrightblack",
            "dimmed": "fg:ansibrightblack",
            "path": "fg:ansimagenta bold",
            "symbol": "fg:ansired bold",
            "status": "bold",
            "rank": "fg:ansigreen bold",
            "error": "fg:ansired",
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


def _get_lexer(language: str | None, file_path: Path | None) -> "Lexer":
    """Get the appropriate Pygments lexer for the given language or file.

    Args:
        language: Language identifier (e.g., "python", "typescript").
        file_path: File path for extension-based language detection.

    Returns:
        A Pygments lexer instance. Falls back to text lexer if language unknown.
    """
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound

    lexer_name = language
    if not lexer_name and file_path:
        lexer_name = EXTENSION_TO_LEXER.get(file_path.suffix, "text")

    try:
        return get_lexer_by_name(lexer_name or "text")
    except ClassNotFound:
        return get_lexer_by_name("text")


def _get_token_color_map() -> dict["_TokenType", str]:
    """Get the mapping from Pygments token types to ANSI color codes.

    Returns:
        Dictionary mapping token types to ANSI escape codes.
    """
    from pygments.token import Token

    return {
        Token.Keyword: AnsiCodes.MAGENTA,
        Token.Name.Function: AnsiCodes.BLUE,
        Token.Name.Class: AnsiCodes.BLUE,
        Token.String: AnsiCodes.GREEN,
        Token.Comment: AnsiCodes.DARK_GRAY,
        Token.Number: AnsiCodes.CYAN,
        Token.Operator: AnsiCodes.WHITE,
    }


def _find_token_color(
    token_type: "_TokenType", color_map: dict["_TokenType", str]
) -> str | None:
    """Find the color for a token, checking parent token types.

    Pygments tokens form a hierarchy (e.g., Token.Keyword.Namespace).
    This function checks the token and its parent types to find a matching color.

    Args:
        token_type: The Pygments token type to look up.
        color_map: Mapping from token types to ANSI color codes.

    Returns:
        The ANSI color code for the token, or None if no match found.
    """
    for ttype in [token_type] + list(token_type.split()):
        if ttype in color_map:
            return color_map[ttype]
    return None


def _colorize_text(text: str, color: str | None) -> str:
    """Apply ANSI color to text if a color is provided.

    Args:
        text: The text to colorize.
        color: ANSI color code, or None for no coloring.

    Returns:
        Colorized text with reset code, or original text if no color.
    """
    if color and text:
        return f"{color}{text}{AnsiCodes.RESET}"
    return text


def _format_line_number(line_num: int) -> str:
    """Format a line number with dimming for display.

    Args:
        line_num: The line number to format.

    Returns:
        Formatted line number string (right-aligned, 4 chars, dimmed).
    """
    return f"{AnsiCodes.DIM}{line_num:>4} {AnsiCodes.RESET}"


def render_syntax_highlighted(
    code: str,
    language: str | None = None,
    file_path: Path | None = None,
    start_line: int = 1,
    theme: str = "ansi",
) -> str:
    """Render code with syntax highlighting using terminal colors.

    Uses Pygments with ANSI 16-color terminal style by default, which respects
    the user's terminal color scheme. This provides seamless integration with
    any terminal theme (Solarized, Dracula, base16, etc.).

    Args:
        code: Code content to highlight.
        language: Language identifier (e.g., "python", "typescript").
            If None, will try to infer from file_path.
        file_path: Optional file path for language detection.
        start_line: Starting line number for display.
        theme: Pygments style name (default: "ansi" for terminal colors).
            Alternative: specific theme names like "monokai", "github-dark", etc.

    Returns:
        Syntax-highlighted code as a string ready for terminal output.
    """
    from pygments import lex

    lexer = _get_lexer(language, file_path)
    color_map = _get_token_color_map()
    tokens = lex(code, lexer)

    result_lines: list[str] = []
    current_line: list[str] = []
    line_num = start_line

    for token_type, value in tokens:
        color = _find_token_color(token_type, color_map)

        # Handle tokens that span multiple lines by splitting on newlines
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                # Complete the current line and start a new one
                line_text = "".join(current_line)
                result_lines.append(f"{_format_line_number(line_num)}{line_text}")
                current_line = []
                line_num += 1

            if part:
                current_line.append(_colorize_text(part, color))

    # Output the final line (always output at least one line)
    if current_line or not result_lines:
        line_text = "".join(current_line)
        result_lines.append(f"{_format_line_number(line_num)}{line_text}")

    return "\n".join(result_lines)
