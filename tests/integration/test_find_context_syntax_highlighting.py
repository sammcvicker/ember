"""Integration tests for find --context syntax highlighting.

Tests that the find command properly applies syntax highlighting when --context is used,
using the render_syntax_highlighted() infrastructure from ember.core.presentation.colors.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.entrypoints.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def python_repo(tmp_path: Path) -> Path:
    """Create a test repo with Python code for syntax highlighting tests."""
    import subprocess

    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Create Python test file with clear syntax elements
    test_file = repo_root / "example.py"
    test_file.write_text('''def calculate_sum(a, b):
    """Calculate the sum of two numbers."""
    result = a + b
    return result


class Calculator:
    """A simple calculator class."""

    def multiply(self, x, y):
        """Multiply two numbers."""
        return x * y
''')

    # Commit file
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        timeout=5,
    )

    return repo_root


class TestFindContextSyntaxHighlighting:
    """Tests for syntax highlighting in find --context command."""

    def test_find_context_applies_syntax_highlighting_by_default(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context applies syntax highlighting by default."""
        monkeypatch.chdir(python_repo)

        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Find with context - should have syntax highlighting by default
        result = runner.invoke(cli, ["find", "calculate", "--context", "3"], catch_exceptions=False)

        assert result.exit_code == 0
        # Check for line numbers in output (syntax highlighting includes line numbers)
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        # Syntax highlighted output has line numbers at the start (e.g., "  1 " or "  2 ")
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers, f"Expected line numbers in output. Lines: {lines[:5]}"

    def test_find_context_respects_syntax_highlighting_disabled(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context respects config.display.syntax_highlighting=false."""
        monkeypatch.chdir(python_repo)

        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Modify config to disable syntax highlighting
        config_path = python_repo / ".ember" / "config.toml"
        config_content = config_path.read_text()
        # Add display.syntax_highlighting = false to config
        if "[display]" not in config_content:
            config_content += "\n[display]\nsyntax_highlighting = false\n"
        else:
            # Replace the syntax_highlighting line or add it
            config_content = config_content.replace(
                "[display]",
                "[display]\nsyntax_highlighting = false"
            )
        config_path.write_text(config_content)

        # Sync and find with context
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "calculate", "--context", "3"], catch_exceptions=False)

        assert result.exit_code == 0
        # Without syntax highlighting, should use old format with | separator
        # and dimmed context lines
        assert "|" in result.output, f"Expected pipe separator in output. Output: {result.output}"

    def test_find_context_uses_configured_theme(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context uses the theme from config.display.theme."""
        monkeypatch.chdir(python_repo)

        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Modify config to use a different theme
        config_path = python_repo / ".ember" / "config.toml"
        config_content = config_path.read_text()
        if "[display]" not in config_content:
            config_content += "\n[display]\ntheme = \"github-dark\"\n"
        else:
            config_content = config_content.replace(
                "[display]",
                "[display]\ntheme = \"github-dark\""
            )
        config_path.write_text(config_content)

        # Sync and find with context
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "calculate", "--context", "3"], catch_exceptions=False)

        assert result.exit_code == 0
        # With syntax highlighting enabled, should have line numbers
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers

    def test_find_context_detects_language_from_file_extension(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context automatically detects language from file path."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and find with context
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "calculate", "--context", "3"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should apply Python syntax highlighting with line numbers
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers

    def test_find_context_shows_rank_before_code(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context shows rank [N] before highlighted code."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and find with context
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "calculate", "--context", "3"], catch_exceptions=False)

        assert result.exit_code == 0
        # Rank should be displayed as [1], [2], etc.
        assert "[1]" in result.output or "[2]" in result.output

    def test_find_without_context_unchanged(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find without --context uses the original format (unchanged)."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and find WITHOUT context
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "calculate"], catch_exceptions=False)

        assert result.exit_code == 0
        # Original format: [rank] line_number: content
        # Should have colon separator (not the | from context mode)
        assert ":" in result.output
        # Should NOT have the line numbers in column format from syntax highlighting
        # (because this tests the non-context mode which remains unchanged)

    @pytest.mark.skip(reason="Search doesn't always return results for non-code files")
    def test_find_context_graceful_fallback_for_unknown_language(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that find --context gracefully handles files with unknown extensions."""
        import subprocess

        # Create repo with unknown file type
        repo_root = tmp_path / "test_repo"
        repo_root.mkdir()

        subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, timeout=5)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            timeout=5,
        )

        # Create file with unknown extension
        test_file = repo_root / "data.xyz"
        test_file.write_text("some content here\nmore content\n")

        subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, timeout=5)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            timeout=5,
        )

        monkeypatch.chdir(repo_root)

        # Update config to index all files
        runner.invoke(cli, ["init"], catch_exceptions=False)
        config_path = repo_root / ".ember" / "config.toml"
        config_content = config_path.read_text()
        # Add .xyz to include patterns
        config_content = config_content.replace(
            'include = [',
            'include = [\n    "**/*.xyz",'
        )
        config_path.write_text(config_content)

        # Sync and find with context
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "content", "--context", "2"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should work even with unknown file type (fallback to plain text)
        assert "content" in result.output

    def test_find_context_json_output_unchanged(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context --json output is unchanged (no syntax highlighting in JSON)."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and find with context and JSON
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(
            cli, ["find", "calculate", "--context", "3", "--json"], catch_exceptions=False
        )

        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert isinstance(data, list)
        # JSON output should have context structure but no ANSI codes
        if len(data) > 0 and "context" in data[0]:
            # Context content should be plain text (no ANSI escape codes)
            context_content = str(data[0]["context"])
            assert "\x1b[" not in context_content
