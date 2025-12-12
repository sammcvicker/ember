"""Unit tests for render_syntax_highlighted function.

Tests the syntax highlighting function to ensure behavior is preserved
during refactoring (issue #137).
"""

from pathlib import Path


class TestRenderSyntaxHighlighted:
    """Tests for the render_syntax_highlighted function."""

    def test_basic_python_highlighting(self) -> None:
        """Test basic Python code highlighting produces expected output."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "def foo():\n    pass"
        result = render_syntax_highlighted(code, language="python")

        # Should have line numbers
        assert "1 " in result
        assert "2 " in result
        # Should contain the code content
        assert "def" in result
        assert "foo" in result
        assert "pass" in result

    def test_line_numbers_start_from_given_value(self) -> None:
        """Test that line numbers start from the given start_line value."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "x = 1\ny = 2"
        result = render_syntax_highlighted(code, language="python", start_line=10)

        # Should have line numbers starting at 10
        assert "10 " in result
        assert "11 " in result
        # Should NOT have line numbers 1 or 2 at the start of lines
        # Line numbers are formatted as "{num:>4} " (right-aligned 4 chars)
        assert "   1 " not in result
        assert "   2 " not in result

    def test_language_detection_from_file_path(self) -> None:
        """Test that language is detected from file extension when not provided."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "function foo() { return 1; }"
        result = render_syntax_highlighted(code, file_path=Path("test.js"))

        # Should still have line numbers and content
        assert "1 " in result
        assert "function" in result

    def test_unknown_file_extension_falls_back_to_text(self) -> None:
        """Test that unknown file extensions fall back to plain text lexer."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "some random content"
        result = render_syntax_highlighted(code, file_path=Path("test.xyz"))

        # Should still produce output with line numbers
        assert "1 " in result
        assert "some random content" in result

    def test_unknown_language_falls_back_to_text(self) -> None:
        """Test that unknown language identifiers fall back to plain text."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "some content"
        result = render_syntax_highlighted(code, language="unknownlang")

        # Should still produce output
        assert "1 " in result
        assert "some content" in result

    def test_empty_code_produces_output(self) -> None:
        """Test that empty code produces a single empty line."""
        from ember.core.presentation.colors import render_syntax_highlighted

        result = render_syntax_highlighted("", language="python")

        # Should have at least a line number
        assert "1 " in result

    def test_multiline_code_preserves_lines(self) -> None:
        """Test that multiline code preserves all lines."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "line1\nline2\nline3"
        result = render_syntax_highlighted(code, language="text")

        lines = result.split('\n')
        assert len(lines) == 3
        assert "1 " in lines[0]
        assert "2 " in lines[1]
        assert "3 " in lines[2]

    def test_code_with_trailing_newline(self) -> None:
        """Test that code with trailing newline is handled correctly.

        Note: The current implementation strips trailing empty lines, which is
        reasonable behavior for code display.
        """
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "line1\nline2\n"
        result = render_syntax_highlighted(code, language="text")

        lines = result.split('\n')
        # Trailing newline results in an empty string after split, but the
        # implementation only outputs non-empty lines, so we get 2 lines
        assert len(lines) == 2
        assert "line1" in lines[0]
        assert "line2" in lines[1]

    def test_ansi_codes_present_for_keywords(self) -> None:
        """Test that ANSI escape codes are present for Python keywords."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "def foo(): pass"
        result = render_syntax_highlighted(code, language="python")

        # Should contain ANSI escape codes
        assert "\x1b[" in result

    def test_ansi_reset_codes_present(self) -> None:
        """Test that ANSI reset codes are present."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "def foo(): pass"
        result = render_syntax_highlighted(code, language="python")

        # Should contain reset code
        assert "\x1b[0m" in result

    def test_line_number_format(self) -> None:
        """Test that line numbers have consistent right-aligned format."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "a\n" * 10  # 10 lines
        result = render_syntax_highlighted(code, language="text")

        lines = result.split('\n')
        # Line numbers should be right-aligned with 4 characters + space
        # e.g., "   1 " or "  10 "
        for i, line in enumerate(lines[:10], start=1):
            # Extract the dimmed line number part (between dim start and reset)
            # Format: \x1b[2m{line_num:>4} \x1b[0m
            assert f"{i:>4} " in line

    def test_supported_file_extensions(self) -> None:
        """Test that common file extensions are mapped to lexers."""
        from ember.core.presentation.colors import render_syntax_highlighted

        extensions_and_content = [
            (".py", "def foo(): pass"),
            (".js", "function foo() {}"),
            (".ts", "const x: number = 1;"),
            (".go", "func main() {}"),
            (".rs", "fn main() {}"),
            (".java", "class Foo {}"),
            (".c", "int main() {}"),
            (".cpp", "int main() {}"),
            (".rb", "def foo; end"),
            (".sh", "echo hello"),
            (".yaml", "key: value"),
            (".json", '{"key": "value"}'),
            (".toml", 'key = "value"'),
            (".sql", "SELECT * FROM foo"),
        ]

        for ext, content in extensions_and_content:
            result = render_syntax_highlighted(content, file_path=Path(f"test{ext}"))
            assert result, f"No output for extension {ext}"
            assert "1 " in result, f"No line number for extension {ext}"

    def test_tokens_with_newlines_handled_correctly(self) -> None:
        """Test that tokens containing newlines are split correctly."""
        from ember.core.presentation.colors import render_syntax_highlighted

        # Multi-line string in Python
        code = '''"""
Multi-line
docstring
"""'''
        result = render_syntax_highlighted(code, language="python")

        lines = result.split('\n')
        assert len(lines) == 4
        # Each line should have a line number
        for i, line in enumerate(lines, start=1):
            assert f"{i:>4} " in line


class TestExtensionToLexerMapping:
    """Tests for the extension to lexer mapping."""

    def test_python_extensions(self) -> None:
        """Test that .py files use Python lexer."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "def foo(): pass"
        result = render_syntax_highlighted(code, file_path=Path("test.py"))
        # Python keywords should be colored (have ANSI codes)
        assert "\x1b[" in result

    def test_typescript_extensions(self) -> None:
        """Test that .ts and .tsx use TypeScript lexer."""
        from ember.core.presentation.colors import render_syntax_highlighted

        for ext in [".ts", ".tsx"]:
            result = render_syntax_highlighted("const x = 1;", file_path=Path(f"test{ext}"))
            assert result
            assert "1 " in result

    def test_javascript_extensions(self) -> None:
        """Test that .js and .jsx use JavaScript lexer."""
        from ember.core.presentation.colors import render_syntax_highlighted

        for ext in [".js", ".jsx"]:
            result = render_syntax_highlighted("const x = 1;", file_path=Path(f"test{ext}"))
            assert result
            assert "1 " in result

    def test_cpp_extensions(self) -> None:
        """Test that .cpp, .cc, .cxx all use C++ lexer."""
        from ember.core.presentation.colors import render_syntax_highlighted

        for ext in [".cpp", ".cc", ".cxx"]:
            result = render_syntax_highlighted("int main() {}", file_path=Path(f"test{ext}"))
            assert result
            assert "1 " in result


class TestAnsiColorCodes:
    """Tests for ANSI color code application."""

    def test_keyword_coloring(self) -> None:
        """Test that keywords receive color codes."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "def foo(): return None"
        result = render_syntax_highlighted(code, language="python")

        # Should have magenta code for keywords (\x1b[95m)
        assert "\x1b[95m" in result

    def test_string_coloring(self) -> None:
        """Test that strings receive color codes."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = 'x = "hello"'
        result = render_syntax_highlighted(code, language="python")

        # Should have green code for strings (\x1b[92m)
        assert "\x1b[92m" in result

    def test_comment_coloring(self) -> None:
        """Test that comments receive color codes."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "# this is a comment"
        result = render_syntax_highlighted(code, language="python")

        # Should have dark gray code for comments (\x1b[90m)
        assert "\x1b[90m" in result

    def test_number_coloring(self) -> None:
        """Test that numbers receive color codes."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "x = 42"
        result = render_syntax_highlighted(code, language="python")

        # Should have cyan code for numbers (\x1b[96m)
        assert "\x1b[96m" in result

    def test_function_name_coloring(self) -> None:
        """Test that function names receive color codes."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "def my_function():\n    pass"
        result = render_syntax_highlighted(code, language="python")

        # Should have blue code for function names (\x1b[94m)
        assert "\x1b[94m" in result

    def test_line_number_dimming(self) -> None:
        """Test that line numbers are dimmed."""
        from ember.core.presentation.colors import render_syntax_highlighted

        code = "x = 1"
        result = render_syntax_highlighted(code, language="python")

        # Should have dim code for line numbers (\x1b[2m)
        assert "\x1b[2m" in result
