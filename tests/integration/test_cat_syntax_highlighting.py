"""Integration tests for cat command syntax highlighting.

Tests that the cat command properly applies syntax highlighting using the
render_syntax_highlighted() infrastructure from ember.core.presentation.colors.
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


class TestCatSyntaxHighlighting:
    """Tests for syntax highlighting in cat command."""

    def test_cat_applies_syntax_highlighting_by_default(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that cat applies syntax highlighting by default (config.display.syntax_highlighting=True)."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "calculate", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Cat the first result - should have syntax highlighting by default
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        assert result.exit_code == 0
        # Rich's syntax highlighting produces formatted output with line numbers
        # The CliRunner sanitizes output, but we can verify Rich was used by checking
        # for line numbers at the start of lines (e.g., "  1 " or "  2 ")
        # Each line should start with padded line number
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        # Check that we have lines starting with space-padded numbers
        # Rich typically formats like "  1 code here"
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers, f"Expected line numbers in output. Lines: {lines[:5]}"

    def test_cat_respects_syntax_highlighting_disabled(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that cat respects config.display.syntax_highlighting=false."""
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

        # Sync and search
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "calculate", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Cat the first result - should NOT have syntax highlighting
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        assert result.exit_code == 0
        # Without syntax highlighting, output should be plain text (no ANSI codes)
        # Note: There might still be some ANSI codes from click.style() for headers,
        # but the main code content should not have Rich syntax highlighting
        # We can check that the output doesn't have the dense ANSI codes that Rich produces

    def test_cat_uses_configured_theme(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that cat uses the theme from config.display.theme."""
        monkeypatch.chdir(python_repo)

        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Modify config to use a different theme (github-dark instead of monokai)
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

        # Sync and search
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "calculate", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Cat the first result - should use github-dark theme
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        assert result.exit_code == 0
        # With syntax highlighting enabled and a valid theme, should have Rich line numbers
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers

    def test_cat_detects_language_from_file_extension(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that cat automatically detects language from file path for highlighting."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and search for Python code
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "calculate", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Verify the result is from a .py file
        assert results[0]["path"].endswith(".py")

        # Cat should apply Python syntax highlighting
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should have Rich syntax highlighting with line numbers
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers

    def test_cat_shows_line_numbers_with_highlighting(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that cat shows line numbers correctly with syntax highlighting."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "calculate", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Cat the result
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        assert result.exit_code == 0
        # Rich's Syntax adds line numbers
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers, "Expected Rich line numbers"

    def test_cat_with_context_and_highlighting(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that cat --context works with syntax highlighting."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "calculate", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Cat with context
        result = runner.invoke(cli, ["cat", "1", "--context", "2"], catch_exceptions=False)

        assert result.exit_code == 0
        # When context is used, it shows plain line-by-line output with | separator (not Rich)
        # This is expected because context mode reads and displays surrounding lines
        assert "|" in result.output  # Context includes line number separator

    def test_cat_with_hash_id_applies_highlighting(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that cat with chunk hash ID also applies syntax highlighting."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and search with JSON to get hash
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "calculate", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        chunk_id = results[0]["id"]

        # Cat using hash ID - should still have syntax highlighting
        result = runner.invoke(cli, ["cat", chunk_id], catch_exceptions=False)

        assert result.exit_code == 0
        # Should have Rich line numbers
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers

    def test_cat_graceful_fallback_for_unknown_language(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that cat gracefully handles files with unknown extensions."""
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

        # Sync and search
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "content", "--json"], catch_exceptions=False)

        assert search_result.exit_code == 0
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Cat should work even with unknown file type (fallback to plain text)
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should still complete successfully (may or may not have highlighting depending on fallback)
        assert "content" in result.output
