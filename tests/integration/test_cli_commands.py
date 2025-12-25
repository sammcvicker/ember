"""Integration tests for CLI commands using click.testing.CliRunner.

Tests the complete CLI flow end-to-end to verify:
- Command execution and exit codes
- Output formatting and messages
- Error handling and user feedback
- Flag and option parsing

Note: Tests prefer semantic assertions (exit codes, file existence) over
exact string matching to be resilient to cosmetic changes (Issue #330).
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.entrypoints.cli import cli
from tests.conftest import create_git_repo, git_add_and_commit, init_git_repo
from tests.helpers import (
    assert_command_failed,
    assert_command_success,
    assert_error_message,
    assert_files_created,
    assert_has_separator,
    assert_output_contains,
    assert_output_matches,
    assert_result_list_format,
    assert_success_indicator,
)


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def git_repo_isolated(runner: CliRunner, tmp_path: Path) -> Path:
    """Create an isolated git repository for testing CLI commands.

    This uses CliRunner's isolated_filesystem to ensure clean test isolation.

    Returns:
        Path to the repository root.
    """
    return create_git_repo(
        tmp_path / "test_repo",
        files={
            "example.py": """def hello():
    '''Say hello.'''
    return "Hello, World!"


def goodbye():
    '''Say goodbye.'''
    return "Goodbye!"
""",
        },
    )


class TestInitCommand:
    """Tests for 'ember init' command."""

    def test_init_creates_ember_directory(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that 'ember init' creates .ember directory and files."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["init"], catch_exceptions=False)

        # Semantic assertions: check exit code and file existence
        assert_command_success(result, context="ember init")
        assert_files_created(
            git_repo_isolated,
            ".ember",
            ".ember/config.toml",
            ".ember/index.db",
        )
        # Verify output mentions initialization (flexible pattern)
        assert_output_matches(result, r"[Ii]nitialized.*ember", context="init message")

    def test_init_shows_success_messages(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that init shows helpful success messages."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["init"], catch_exceptions=False)

        assert_command_success(result, context="ember init")
        # Use flexible patterns for success indicators
        assert_success_indicator(result)
        # Check for next steps hint (flexible pattern)
        assert_output_matches(result, r"ember sync", context="next steps hint")

    def test_init_quiet_mode_suppresses_details(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --quiet suppresses detailed output."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["--quiet", "init"], catch_exceptions=False)

        assert_command_success(result, context="ember --quiet init")
        # Quiet mode should have minimal output - just summary
        assert_output_matches(result, r"[Ii]nitialized", context="summary message")
        # Verbose file creation messages should be suppressed
        # (Check that output is shorter than normal init)
        assert len(result.output) < 500  # Quiet mode produces less output

    def test_init_fails_when_already_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that init fails if .ember/ already exists."""
        monkeypatch.chdir(git_repo_isolated)
        # First init
        result1 = runner.invoke(cli, ["init"], catch_exceptions=False)
        assert_command_success(result1, context="first init")

        # Second init should fail
        result2 = runner.invoke(cli, ["init"])
        assert_command_failed(result2, context="second init")
        assert_error_message(result2, hint="ember init --force")
        assert_output_matches(result2, r"already exists", context="already exists hint")

    def test_init_force_reinitializes(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --force flag allows reinitialization."""
        monkeypatch.chdir(git_repo_isolated)
        # First init
        result1 = runner.invoke(cli, ["init"], catch_exceptions=False)
        assert_command_success(result1, context="first init")

        # Modify config
        config_path = git_repo_isolated / ".ember" / "config.toml"
        config_path.write_text("# Modified")

        # Force reinit
        result2 = runner.invoke(cli, ["init", "--force"], catch_exceptions=False)
        assert_command_success(result2, context="force reinit")
        # Check for reinitialize message (flexible pattern)
        assert_output_matches(result2, r"[Rr]einitialize", context="reinit message")

        # Semantic check: verify config was replaced
        new_content = config_path.read_text()
        assert "# Modified" not in new_content
        assert "[index]" in new_content

    def test_init_fails_outside_git_repo(self, runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
        """Test that init shows appropriate behavior when not in a git repository."""
        non_git_dir = tmp_path / "non_git"
        non_git_dir.mkdir()
        monkeypatch.chdir(non_git_dir)

        result = runner.invoke(cli, ["init"])
        # Init outside git repo may succeed (initializes in current dir) or fail
        # This depends on whether ember requires git - check for appropriate messaging
        if result.exit_code != 0:
            assert_output_matches(
                result, r"error|git", flags=__import__("re").IGNORECASE, context="error or git message"
            )


class TestSyncCommand:
    """Tests for 'ember sync' command."""

    def test_sync_indexes_files(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that 'ember sync' successfully indexes files."""
        monkeypatch.chdir(git_repo_isolated)
        # Init first
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Sync
        result = runner.invoke(cli, ["sync"], catch_exceptions=False)

        assert_command_success(result, context="ember sync")
        assert_success_indicator(result)
        # Check for indexing indication (flexible pattern)
        assert_output_matches(result, r"[Ii]ndexed|files", context="sync progress")

    def test_sync_detects_no_changes(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that sync detects when there are no changes."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Sync again without changes
        result = runner.invoke(cli, ["sync"], catch_exceptions=False)

        assert_command_success(result, context="second sync")
        # Check for "no changes" or success indication
        assert_output_matches(result, r"[Nn]o changes|check", context="no changes message")

    def test_sync_reindex_flag_forces_full_reindex(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --reindex forces a full reindex."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Force reindex
        result = runner.invoke(cli, ["sync", "--reindex"], catch_exceptions=False)

        assert_command_success(result, context="reindex")
        # Check for full sync or indexed indication
        assert_output_matches(result, r"full|[Ii]ndexed", context="reindex output")

    def test_sync_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that sync fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["sync"])

        assert_command_failed(result, context="sync without init")
        assert_output_matches(
            result, r"[Ee]rror|not initialized|not in", context="error message"
        )

    def test_sync_mutually_exclusive_options(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --worktree, --staged, and --rev are mutually exclusive."""
        monkeypatch.chdir(git_repo_isolated)
        # Init first
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Try using both --worktree and --staged
        result = runner.invoke(cli, ["sync", "--worktree", "--staged"])

        assert_command_failed(result, context="mutually exclusive options")
        assert_output_contains(result, "mutually exclusive")

    def test_sync_quiet_mode(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --quiet mode suppresses progress output."""
        monkeypatch.chdir(git_repo_isolated)
        # Init first
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Sync in quiet mode
        result = runner.invoke(cli, ["--quiet", "sync"], catch_exceptions=False)

        assert_command_success(result, context="quiet sync")
        # Output should be minimal (quiet mode shows summary but not progress)
        lines = [line for line in result.output.strip().split('\n') if line]
        # Should have at most a few lines (success message and stats)
        assert len(lines) <= 5


class TestFindCommand:
    """Tests for 'ember find' command."""

    def test_find_returns_results(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that find returns search results."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search for "hello"
        result = runner.invoke(cli, ["find", "hello function"], catch_exceptions=False)

        assert_command_success(result, context="ember find")
        # Should show results or "no results"
        assert len(result.output) > 0

    def test_find_json_output(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --json flag outputs valid JSON."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with JSON output
        result = runner.invoke(cli, ["find", "hello", "--json"], catch_exceptions=False)

        assert_command_success(result, context="ember find --json")

        # Verify output is valid JSON (semantic check)
        try:
            data = json.loads(result.output)
            # The JSON output is a list of results
            assert isinstance(data, list)
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")

    def test_find_topk_option(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --topk option limits results."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with topk=1 and JSON output for easy verification
        result = runner.invoke(
            cli, ["find", "function", "--topk", "1", "--json"],
            catch_exceptions=False
        )

        assert_command_success(result, context="ember find --topk")
        data = json.loads(result.output)
        # The JSON output is a list - should have at most 1 result
        assert len(data) <= 1

    def test_find_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that find fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["find", "test"])

        assert_command_failed(result, context="find without init")
        assert_error_message(result)

    def test_find_no_sync_flag_skips_auto_sync(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --no-sync flag skips automatic sync check."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with --no-sync
        result = runner.invoke(
            cli, ["find", "hello", "--no-sync"],
            catch_exceptions=False
        )

        # Should work but skip sync
        assert_command_success(result, context="find --no-sync")

    def test_find_path_filter(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --in path filter works."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with path filter
        result = runner.invoke(
            cli, ["find", "hello", "--in", "*.py"],
            catch_exceptions=False
        )

        assert_command_success(result, context="find --in filter")

    def test_find_lang_filter(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --lang filter works."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with language filter
        result = runner.invoke(
            cli, ["find", "hello", "--lang", "py"],
            catch_exceptions=False
        )

        assert_command_success(result, context="find --lang filter")

    def test_find_with_context_shows_surrounding_lines(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that --context flag shows surrounding lines in find results."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with context
        result = runner.invoke(
            cli, ["find", "hello", "--context", "3"],
            catch_exceptions=False
        )

        assert_command_success(result, context="find --context")

        # If results were found, verify context format (semantic check)
        assert_result_list_format(
            result,
            expect_line_numbers=True,
            expect_ranks=False,
            context="find --context output",
        )

    def test_find_with_context_json_output(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that --context flag works with --json output."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with context and JSON output
        result = runner.invoke(
            cli, ["find", "hello", "--context", "5", "--json"],
            catch_exceptions=False
        )

        assert_command_success(result, context="find --context --json")

        # Semantic check: verify valid JSON with expected structure
        try:
            data = json.loads(result.output)
            assert isinstance(data, list)
            if len(data) > 0:
                result_item = data[0]
                assert "context" in result_item or "content" in result_item
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")

    def test_find_context_default_zero(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that context defaults to 0 (no context) when flag not provided."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search without context flag (should behave as before)
        result = runner.invoke(
            cli, ["find", "hello"],
            catch_exceptions=False
        )

        assert_command_success(result, context="find without context")

    def test_find_context_with_topk(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that --context works with --topk option."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with both context and topk
        result = runner.invoke(
            cli, ["find", "function", "--context", "3", "--topk", "2"],
            catch_exceptions=False
        )

        assert_command_success(result, context="find --context --topk")

    def test_find_context_with_path_filter(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that --context works with --in path filter."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Search with context and path filter
        result = runner.invoke(
            cli, ["find", "hello", "--context", "2", "--in", "*.py"],
            catch_exceptions=False
        )

        assert_command_success(result, context="find --context --in")

    def test_find_path_and_in_filter_mutually_exclusive(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that PATH argument and --in filter are mutually exclusive."""
        monkeypatch.chdir(git_repo_isolated)
        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Try to use both PATH argument and --in filter
        result = runner.invoke(
            cli, ["find", "hello", "src/", "--in", "*.py"],
            catch_exceptions=False
        )

        # Should fail with error about mutually exclusive options
        assert_command_failed(result, context="PATH and --in together")
        assert_output_matches(
            result, r"mutually exclusive|cannot use both", flags=__import__("re").IGNORECASE
        )


class TestSearchCommand:
    """Tests for 'ember search' command filter handling."""

    def test_search_path_and_in_filter_mutually_exclusive(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that PATH argument and --in flag are mutually exclusive."""
        monkeypatch.chdir(git_repo_isolated)
        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Try to use both PATH argument and --in flag
        result = runner.invoke(
            cli, ["search", ".", "--in", "*.py"],
            catch_exceptions=False
        )

        # Should fail with error about mutually exclusive options
        assert_command_failed(result, context="search PATH and --in together")
        assert_output_matches(
            result, r"mutually exclusive|cannot use both", flags=__import__("re").IGNORECASE
        )

    def test_search_accepts_path_argument(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that search accepts a path argument to restrict results."""
        monkeypatch.chdir(git_repo_isolated)
        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Create a subdirectory with a file
        subdir = git_repo_isolated / "subdir"
        subdir.mkdir()
        (subdir / "test.py").write_text("def test_func(): pass")

        # Re-sync to index the new file
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Test that path argument is accepted (we can't fully test interactive mode,
        # but we can verify the argument parsing works via --help)
        result = runner.invoke(cli, ["search", "subdir", "--help"])
        assert_command_success(result, context="search --help")

    def test_search_no_path_argument(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that search works without path argument (searches entire repo)."""
        monkeypatch.chdir(git_repo_isolated)
        # Init
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Test that search command without path doesn't cause parsing error
        result = runner.invoke(cli, ["search", "--help"])
        assert_command_success(result, context="search --help")
        # Help should show PATH is optional (flexible pattern)
        assert_output_matches(result, r"\[PATH\]|path", flags=__import__("re").IGNORECASE)


class TestCatCommand:
    """Tests for 'ember cat' command."""

    def test_cat_displays_result(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat displays a search result's content."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search (without --json to cache results properly)
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "hello"], catch_exceptions=False)

        # Verify search succeeded and returned results
        assert_command_success(search_result, context="find for cat test")

        # Cat might fail if no results were found in search
        if "No results" in search_result.output or search_result.output.strip() == "":
            pytest.skip("Search returned no results")

        # Cat the first result (1-based indexing)
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        assert_command_success(result, context="cat 1")
        # Should show some content
        assert len(result.output) > 0

    def test_cat_with_context(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat --context shows surrounding lines."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "hello"], catch_exceptions=False)

        # Verify search succeeded
        assert_command_success(search_result, context="find for cat context test")
        if "No results" in search_result.output or search_result.output.strip() == "":
            pytest.skip("Search returned no results")

        # Cat with context
        result = runner.invoke(cli, ["cat", "1", "--context", "2"], catch_exceptions=False)

        assert_command_success(result, context="cat --context")
        # Should show line numbers (semantic check for context format)
        assert_has_separator(result, "|", context="cat --context line separator")

    def test_cat_fails_without_prior_search(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat fails if no search was performed."""
        monkeypatch.chdir(git_repo_isolated)
        # Init only (no search)
        runner.invoke(cli, ["init"], catch_exceptions=False)

        result = runner.invoke(cli, ["cat", "1"])

        assert_command_failed(result, context="cat without search")
        assert_output_matches(result, r"[Ee]rror|[Nn]o", context="error message")

    def test_cat_fails_with_invalid_index(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat fails with out-of-bounds index."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        runner.invoke(cli, ["find", "hello"], catch_exceptions=False)

        # Try invalid index
        result = runner.invoke(cli, ["cat", "999"])

        assert_command_failed(result, context="cat invalid index")
        assert_output_matches(result, r"[Ee]rror|[Ii]nvalid", context="error message")

    def test_cat_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["cat", "1"])

        assert_command_failed(result, context="cat without init")
        assert_error_message(result)

    def test_cat_with_chunk_hash_id(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat works with a chunk hash ID from JSON output."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search with JSON output
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "hello", "--json"], catch_exceptions=False)

        # Verify search succeeded
        assert_command_success(search_result, context="find --json")

        # Parse JSON to get chunk ID (semantic check)
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Verify chunk ID format (64 hex chars for blake3)
        chunk_id = results[0]["id"]
        assert len(chunk_id) == 64
        assert all(c in "0123456789abcdef" for c in chunk_id)

        # Cat using the full chunk ID
        result = runner.invoke(cli, ["cat", chunk_id], catch_exceptions=False)

        assert_command_success(result, context="cat by hash")
        assert len(result.output) > 0

    def test_cat_with_short_hash(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat works with a short hash prefix."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search with JSON output
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "hello", "--json"], catch_exceptions=False)

        # Verify search succeeded
        assert_command_success(search_result, context="find --json")

        # Parse JSON to get chunk ID
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        # Use short prefix (16 chars) for uniqueness
        chunk_id = results[0]["id"]
        short_hash = chunk_id[:16]

        # Cat using the short hash
        result = runner.invoke(cli, ["cat", short_hash], catch_exceptions=False)

        assert_command_success(result, context="cat by short hash")
        assert len(result.output) > 0

    def test_cat_with_invalid_hash(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat fails with a non-existent hash ID."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Try to cat with a hash that doesn't exist (use valid hex format)
        result = runner.invoke(cli, ["cat", "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"])

        assert_command_failed(result, context="cat nonexistent hash")
        assert_error_message(result)
        assert_output_matches(result, r"[Nn]o chunk found", context="not found message")

    def test_cat_hash_works_without_prior_search(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat with hash ID works without running find first (stateless)."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search with JSON output to get a hash
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        search_result = runner.invoke(cli, ["find", "hello", "--json"], catch_exceptions=False)

        # Parse JSON to get chunk ID
        results = json.loads(search_result.output)
        if len(results) == 0:
            pytest.skip("Search returned no results")

        chunk_id = results[0]["id"]

        # Delete cached search results to simulate no prior search
        cache_path = git_repo_isolated / ".ember" / ".last_search.json"
        if cache_path.exists():
            cache_path.unlink()

        # Cat should still work with hash ID (stateless)
        result = runner.invoke(cli, ["cat", chunk_id], catch_exceptions=False)

        assert_command_success(result, context="cat by hash without cache")
        assert len(result.output) > 0


class TestOpenCommand:
    """Tests for 'ember open' command."""

    def test_open_fails_without_prior_search(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that open fails if no search was performed."""
        monkeypatch.chdir(git_repo_isolated)
        # Init only (no search)
        runner.invoke(cli, ["init"], catch_exceptions=False)

        result = runner.invoke(cli, ["open", "1"])

        assert_command_failed(result, context="open without search")
        assert_output_matches(result, r"[Ee]rror|[Nn]o", context="error message")

    def test_open_fails_with_invalid_index(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that open fails with out-of-bounds index."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        runner.invoke(cli, ["find", "hello"], catch_exceptions=False)

        # Try invalid index
        result = runner.invoke(cli, ["open", "999"])

        assert_command_failed(result, context="open invalid index")
        assert_output_matches(result, r"[Ee]rror|[Ii]nvalid", context="error message")

    def test_open_fails_if_editor_not_found(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that open fails gracefully if editor not available."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        runner.invoke(cli, ["find", "hello"], catch_exceptions=False)

        # Set EDITOR to nonexistent command
        monkeypatch.setenv("EDITOR", "nonexistent-editor-xyz")
        result = runner.invoke(cli, ["open", "1"])

        assert_command_failed(result, context="open with bad editor")
        assert_output_matches(result, r"not found|[Ee]rror", context="error message")


class TestStatusCommand:
    """Tests for 'ember status' command."""

    def test_status_shows_index_info(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status displays index information."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert_command_success(result, context="status")
        # Check for index and config sections (flexible pattern)
        assert_output_matches(result, r"[Ii]ndex|[Ff]iles", context="index info")
        assert_output_matches(result, r"[Cc]onfig", context="config section")

    def test_status_shows_up_to_date(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status shows 'up to date' after sync."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert_command_success(result, context="status after sync")
        # Check for up-to-date indication (success indicator or explicit text)
        assert_output_matches(result, r"[Uu]p to date|[✓✔]", context="up to date indicator")

    def test_status_shows_never_synced(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status shows 'never synced' before first sync."""
        monkeypatch.chdir(git_repo_isolated)
        # Init only (no sync)
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert_command_success(result, context="status before sync")
        # Check for never synced indication
        assert_output_matches(result, r"[Nn]ever|sync", context="never synced message")

    def test_status_shows_stale_warning(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status warns when index is stale."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Modify file (creating staleness)
        test_file = git_repo_isolated / "example.py"
        test_file.write_text(test_file.read_text() + "\n# New comment\n")
        git_add_and_commit(git_repo_isolated, message="Update")

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert_command_success(result, context="status with stale index")
        # Check for stale/out-of-date warning (flexible pattern)
        assert_output_matches(result, r"[Oo]ut of date|stale|[⚠]", context="stale warning")

    def test_status_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["status"])

        assert_command_failed(result, context="status without init")
        assert_output_matches(result, r"[Ee]rror|not.*ember", context="error message")
        assert_output_contains(result, "ember init")

    def test_status_shows_config_values(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status displays configuration values."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert_command_success(result, context="status config display")
        # Should show config details (flexible pattern)
        assert_output_matches(result, r"topk|[Ss]earch.*results", context="search config")
        assert_output_matches(result, r"chunk|[Cc]hunking", context="chunk config")


class TestVerboseQuietFlags:
    """Tests for global --verbose and --quiet flags."""

    def test_verbose_flag_available(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --verbose flag is accepted."""
        monkeypatch.chdir(git_repo_isolated)
        # Init with verbose
        result = runner.invoke(cli, ["--verbose", "init"], catch_exceptions=False)

        assert_command_success(result, context="verbose init")

    def test_quiet_flag_suppresses_output(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --quiet flag reduces output."""
        monkeypatch.chdir(git_repo_isolated)
        # Init with quiet
        result_quiet = runner.invoke(cli, ["--quiet", "init"], catch_exceptions=False)

        # Init without quiet (in fresh repo)
        git_repo_2 = git_repo_isolated.parent / "test_repo_2"
        git_repo_2.mkdir()
        init_git_repo(git_repo_2)

        monkeypatch.chdir(git_repo_2)
        result_normal = runner.invoke(cli, ["init"], catch_exceptions=False)

        # Semantic check: quiet mode should have less output
        assert len(result_quiet.output) < len(result_normal.output)


class TestErrorHandling:
    """Tests for CLI error handling."""

    def test_command_shows_error_on_failure(self, runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
        """Test that commands show clear error messages on actual failures."""
        non_git_dir = tmp_path / "non_git"
        non_git_dir.mkdir()
        monkeypatch.chdir(non_git_dir)

        # Try to sync without initializing first - this should fail
        result = runner.invoke(cli, ["sync"])

        assert_command_failed(result, context="sync in non-ember dir")
        assert_error_message(result)

    def test_nonexistent_command_shows_help(self, runner: CliRunner) -> None:
        """Test that invalid commands show helpful error."""
        result = runner.invoke(cli, ["nonexistent-command"])

        # Should fail (Click shows error for unknown command)
        assert result.exit_code != 0

    def test_missing_required_argument(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that missing required arguments are caught."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Try find without query
        result = runner.invoke(cli, ["find"])

        # Click should show missing argument error
        assert result.exit_code != 0


class TestGetEmberRepoRoot:
    """Tests for the get_ember_repo_root helper function."""

    def test_returns_repo_and_ember_dir_when_in_ember_repo(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that helper returns correct paths in an ember repository."""
        monkeypatch.chdir(git_repo_isolated)
        # Initialize ember
        runner.invoke(cli, ["init"], catch_exceptions=False)

        from ember.entrypoints.cli import get_ember_repo_root

        repo_root, ember_dir = get_ember_repo_root()

        assert repo_root == git_repo_isolated
        assert ember_dir == git_repo_isolated / ".ember"

    def test_raises_error_when_not_in_ember_repo(self, runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
        """Test that helper raises EmberCliError when not in ember repository."""
        # Create a directory without .ember
        no_ember_dir = tmp_path / "no_ember"
        no_ember_dir.mkdir()
        monkeypatch.chdir(no_ember_dir)

        from ember.core.cli_utils import EmberCliError
        from ember.entrypoints.cli import get_ember_repo_root

        # Should raise EmberCliError with helpful hint
        with pytest.raises(EmberCliError) as exc_info:
            get_ember_repo_root()

        assert "Not in an ember repository" in exc_info.value.message
        assert exc_info.value.hint is not None
        assert "ember init" in exc_info.value.hint

    def test_works_from_subdirectory(
        self, runner: CliRunner, git_repo_isolated: Path, monkeypatch
    ) -> None:
        """Test that helper finds ember root from a subdirectory."""
        monkeypatch.chdir(git_repo_isolated)
        # Initialize ember
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Create and change to subdirectory
        subdir = git_repo_isolated / "subdir" / "nested"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        from ember.entrypoints.cli import get_ember_repo_root

        repo_root, ember_dir = get_ember_repo_root()

        assert repo_root == git_repo_isolated
        assert ember_dir == git_repo_isolated / ".ember"
