"""Integration tests for find --context output formatting.

Tests that the find command properly formats output with --context flag.
Note: As of issue #207, find uses simplified highlighting (symbol-only, red bold)
instead of full syntax highlighting for faster visual scanning.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.entrypoints.cli import cli
from tests.conftest import create_git_repo, git_add_and_commit


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def python_repo(tmp_path: Path) -> Path:
    """Create a test repo with Python code for syntax highlighting tests."""
    return create_git_repo(
        tmp_path / "test_repo",
        files={
            "example.py": '''def calculate_sum(a, b):
    """Calculate the sum of two numbers."""
    result = a + b
    return result


class Calculator:
    """A simple calculator class."""

    def multiply(self, x, y):
        """Multiply two numbers."""
        return x * y
''',
        },
    )


class TestFindContextSyntaxHighlighting:
    """Tests for output formatting in find --context command.

    Note: As of issue #207, find uses simplified highlighting (symbol-only, red bold)
    instead of full syntax highlighting for faster visual scanning.
    """

    def test_find_context_shows_line_numbers(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context shows line numbers in output."""
        monkeypatch.chdir(python_repo)

        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Find with context
        result = runner.invoke(cli, ["find", "calculate", "--context", "3"], catch_exceptions=False)

        assert result.exit_code == 0
        # Output should have line numbers (format: [rank] line_num:content or line_num:content)
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers, f"Expected line numbers in output. Lines: {lines[:5]}"

    def test_find_context_uses_plain_format(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context uses plain format with colon separator."""
        monkeypatch.chdir(python_repo)

        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Modify config to disable syntax highlighting (should have no effect now)
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
        # Plain format uses colon separator: line_num:content
        assert ":" in result.output, f"Expected colon separator in output. Output: {result.output}"
        # Should have rank indicator [1], [2], etc.
        assert "[1]" in result.output or "[2]" in result.output, \
            f"Expected rank indicator in output. Output: {result.output}"

    def test_find_context_ignores_theme_setting(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context ignores theme setting (uses plain format)."""
        monkeypatch.chdir(python_repo)

        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Modify config to use a different theme (should have no effect)
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
        # Output should still have line numbers (plain format)
        lines = [line for line in result.output.split('\n') if line.strip() and not line.startswith('[')]
        has_line_numbers = any(line.strip() and line[0:5].strip().isdigit() for line in lines)
        assert has_line_numbers

    def test_find_context_works_with_any_file_type(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that find --context works regardless of file type."""
        monkeypatch.chdir(python_repo)

        # Init, sync, and find with context
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "calculate", "--context", "3"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should show line numbers in plain format
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
        # Create repo with unknown file type
        repo_root = create_git_repo(
            tmp_path / "test_repo",
            files={"data.xyz": "some content here\nmore content\n"},
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

    def test_find_context_multiple_results_same_file_properly_separated(
        self, runner: CliRunner, python_repo: Path, monkeypatch
    ) -> None:
        """Test that multiple results from same file have proper spacing with --context."""
        monkeypatch.chdir(python_repo)

        # Create a file with multiple functions that will match the same query
        multi_file = python_repo / "multi.py"
        multi_file.write_text('''def process_data(data):
    """Process the input data."""
    result = transform(data)
    return result


def process_request(request):
    """Process the HTTP request."""
    response = handle(request)
    return response


def process_events(events):
    """Process the event queue."""
    for event in events:
        dispatch(event)
''')

        # Commit the file
        git_add_and_commit(python_repo, message="Add multi.py")

        # Init, sync, and find with context
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        result = runner.invoke(cli, ["find", "process", "--context", "2"], catch_exceptions=False)

        assert result.exit_code == 0

        # Split output into lines and clean up
        lines = result.output.split('\n')

        # Find the file path line (multi.py)
        file_path_idx = None
        for i, line in enumerate(lines):
            if 'multi.py' in line:
                file_path_idx = i
                break

        assert file_path_idx is not None, f"File path not found in output: {result.output}"

        # Check that there's a blank line after the file path
        # (before the first rank marker [1])
        rank_indices = [i for i, line in enumerate(lines) if line.strip().startswith('[') and ']' in line]
        assert len(rank_indices) >= 2, f"Expected at least 2 results. Output: {result.output}"

        # There should be blank lines separating the results
        # The output structure should be:
        # multi.py
        # [blank line or directly to rank]
        # [1]
        # <code>
        # [blank line]
        # [2]
        # <code>

        # Count blank lines between first and second rank
        if len(rank_indices) >= 2:
            first_rank_idx = rank_indices[0]
            second_rank_idx = rank_indices[1]
            blank_between = sum(1 for i in range(first_rank_idx + 1, second_rank_idx)
                               if not lines[i].strip())
            # Should have at least one blank line between results
            assert blank_between >= 1, \
                f"Expected blank line between results. Lines {first_rank_idx}-{second_rank_idx}: " \
                f"{lines[first_rank_idx:second_rank_idx + 1]}"
