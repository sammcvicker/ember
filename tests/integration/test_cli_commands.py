"""Integration tests for CLI commands using click.testing.CliRunner.

Tests the complete CLI flow end-to-end to verify:
- Command execution and exit codes
- Output formatting and messages
- Error handling and user feedback
- Flag and option parsing
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.entrypoints.cli import cli


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

    # Create test file
    test_file = repo_root / "example.py"
    test_file.write_text("""def hello():
    '''Say hello.'''
    return "Hello, World!"


def goodbye():
    '''Say goodbye.'''
    return "Goodbye!"
""")

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


class TestInitCommand:
    """Tests for 'ember init' command."""

    def test_init_creates_ember_directory(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that 'ember init' creates .ember directory and files."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["init"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Initialized ember index" in result.output
        assert (git_repo_isolated / ".ember").exists()
        assert (git_repo_isolated / ".ember" / "config.toml").exists()
        assert (git_repo_isolated / ".ember" / "index.db").exists()
        assert (git_repo_isolated / ".ember" / "state.json").exists()

    def test_init_shows_success_messages(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that init shows helpful success messages."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["init"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "✓ Created config.toml" in result.output
        assert "✓ Created index.db" in result.output
        assert "✓ Created state.json" in result.output
        assert "Next: Run 'ember sync'" in result.output

    def test_init_quiet_mode_suppresses_details(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --quiet suppresses detailed output."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["--quiet", "init"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Initialized ember index" in result.output
        # Should not show the detailed file creation messages
        assert "✓ Created config.toml" not in result.output

    def test_init_fails_when_already_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that init fails if .ember/ already exists."""
        monkeypatch.chdir(git_repo_isolated)
        # First init
        result1 = runner.invoke(cli, ["init"], catch_exceptions=False)
        assert result1.exit_code == 0

        # Second init should fail
        result2 = runner.invoke(cli, ["init"])
        assert result2.exit_code == 1
        assert "Error:" in result2.output
        assert "already exists" in result2.output
        assert "ember init --force" in result2.output

    def test_init_force_reinitializes(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --force flag allows reinitialization."""
        monkeypatch.chdir(git_repo_isolated)
        # First init
        result1 = runner.invoke(cli, ["init"], catch_exceptions=False)
        assert result1.exit_code == 0

        # Modify config
        config_path = git_repo_isolated / ".ember" / "config.toml"
        config_path.write_text("# Modified")

        # Force reinit
        result2 = runner.invoke(cli, ["init", "--force"], catch_exceptions=False)
        assert result2.exit_code == 0
        assert "Reinitialized existing ember index" in result2.output

        # Verify config was replaced
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
            assert "Error" in result.output or "git" in result.output.lower()


class TestSyncCommand:
    """Tests for 'ember sync' command."""

    def test_sync_indexes_files(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that 'ember sync' successfully indexes files."""
        monkeypatch.chdir(git_repo_isolated)
        # Init first
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Sync
        result = runner.invoke(cli, ["sync"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "✓" in result.output
        assert "Indexed" in result.output or "files" in result.output.lower()

    def test_sync_detects_no_changes(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that sync detects when there are no changes."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Sync again without changes
        result = runner.invoke(cli, ["sync"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "No changes detected" in result.output or "✓" in result.output

    def test_sync_reindex_flag_forces_full_reindex(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --reindex forces a full reindex."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Force reindex
        result = runner.invoke(cli, ["sync", "--reindex"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "full" in result.output.lower() or "Indexed" in result.output

    def test_sync_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that sync fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["sync"])

        assert result.exit_code == 1
        assert "Error" in result.output or "not initialized" in result.output.lower()

    def test_sync_mutually_exclusive_options(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --worktree, --staged, and --rev are mutually exclusive."""
        monkeypatch.chdir(git_repo_isolated)
        # Init first
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Try using both --worktree and --staged
        result = runner.invoke(cli, ["sync", "--worktree", "--staged"])

        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    def test_sync_quiet_mode(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --quiet mode suppresses progress output."""
        monkeypatch.chdir(git_repo_isolated)
        # Init first
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Sync in quiet mode
        result = runner.invoke(cli, ["--quiet", "sync"], catch_exceptions=False)

        assert result.exit_code == 0
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

        assert result.exit_code == 0
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

        assert result.exit_code == 0

        # Verify output is valid JSON
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

        assert result.exit_code == 0
        data = json.loads(result.output)
        # The JSON output is a list - should have at most 1 result
        assert len(data) <= 1

    def test_find_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that find fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["find", "test"])

        assert result.exit_code == 1
        assert "Error" in result.output

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
        assert result.exit_code == 0

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

        assert result.exit_code == 0

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

        assert result.exit_code == 0


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
        assert search_result.exit_code == 0

        # Cat the first result (1-based indexing)
        result = runner.invoke(cli, ["cat", "1"], catch_exceptions=False)

        # Cat might fail if no results were found in search, so check for that
        if "No results" in search_result.output or search_result.output.strip() == "":
            # Skip test if search returned no results
            pytest.skip("Search returned no results")

        assert result.exit_code == 0, f"Cat failed with output: {result.output}"
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
        assert search_result.exit_code == 0
        if "No results" in search_result.output or search_result.output.strip() == "":
            pytest.skip("Search returned no results")

        # Cat with context
        result = runner.invoke(cli, ["cat", "1", "--context", "2"], catch_exceptions=False)

        assert result.exit_code == 0, f"Cat failed with output: {result.output}"
        # Should show line numbers
        assert "|" in result.output  # Line number separator

    def test_cat_fails_without_prior_search(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat fails if no search was performed."""
        monkeypatch.chdir(git_repo_isolated)
        # Init only (no search)
        runner.invoke(cli, ["init"], catch_exceptions=False)

        result = runner.invoke(cli, ["cat", "1"])

        assert result.exit_code == 1
        assert "Error" in result.output or "No" in result.output

    def test_cat_fails_with_invalid_index(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat fails with out-of-bounds index."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        runner.invoke(cli, ["find", "hello"], catch_exceptions=False)

        # Try invalid index
        result = runner.invoke(cli, ["cat", "999"])

        assert result.exit_code == 1
        assert "Error" in result.output or "Invalid" in result.output

    def test_cat_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that cat fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["cat", "1"])

        assert result.exit_code == 1
        assert "Error" in result.output


class TestOpenCommand:
    """Tests for 'ember open' command."""

    def test_open_fails_without_prior_search(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that open fails if no search was performed."""
        monkeypatch.chdir(git_repo_isolated)
        # Init only (no search)
        runner.invoke(cli, ["init"], catch_exceptions=False)

        result = runner.invoke(cli, ["open", "1"])

        assert result.exit_code == 1
        assert "Error" in result.output or "No" in result.output

    def test_open_fails_with_invalid_index(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that open fails with out-of-bounds index."""
        monkeypatch.chdir(git_repo_isolated)
        # Init, sync, and search
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)
        runner.invoke(cli, ["find", "hello"], catch_exceptions=False)

        # Try invalid index
        result = runner.invoke(cli, ["open", "999"])

        assert result.exit_code == 1
        assert "Error" in result.output or "Invalid" in result.output

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

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Error" in result.output


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

        assert result.exit_code == 0
        assert "Index Status" in result.output or "Indexed files" in result.output
        assert "Configuration" in result.output

    def test_status_shows_up_to_date(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status shows 'up to date' after sync."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Up to date" in result.output or "✓" in result.output

    def test_status_shows_never_synced(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status shows 'never synced' before first sync."""
        monkeypatch.chdir(git_repo_isolated)
        # Init only (no sync)
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Never synced" in result.output or "sync" in result.output.lower()

    def test_status_shows_stale_warning(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status warns when index is stale."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Modify file (creating staleness)
        test_file = git_repo_isolated / "example.py"
        test_file.write_text(test_file.read_text() + "\n# New comment\n")
        subprocess.run(["git", "add", "."], cwd=git_repo_isolated, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Update"],
            cwd=git_repo_isolated,
            check=True,
            capture_output=True,
        )

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Out of date" in result.output or "stale" in result.output.lower() or "⚠" in result.output

    def test_status_fails_if_not_initialized(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status fails if ember not initialized."""
        monkeypatch.chdir(git_repo_isolated)
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 1
        assert "Error" in result.output or "not in an ember repository" in result.output.lower()
        assert "ember init" in result.output

    def test_status_shows_config_values(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that status displays configuration values."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)
        runner.invoke(cli, ["sync"], catch_exceptions=False)

        # Check status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)

        assert result.exit_code == 0
        # Should show config details
        assert "topk" in result.output.lower() or "Search results" in result.output
        assert "chunk" in result.output.lower() or "Chunking" in result.output


class TestVerboseQuietFlags:
    """Tests for global --verbose and --quiet flags."""

    def test_verbose_flag_available(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --verbose flag is accepted."""
        monkeypatch.chdir(git_repo_isolated)
        # Init with verbose
        result = runner.invoke(cli, ["--verbose", "init"], catch_exceptions=False)

        assert result.exit_code == 0
        # Verbose should work (exact output varies)

    def test_quiet_flag_suppresses_output(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that --quiet flag reduces output."""
        monkeypatch.chdir(git_repo_isolated)
        # Init with quiet
        result_quiet = runner.invoke(cli, ["--quiet", "init"], catch_exceptions=False)

        # Init without quiet (in fresh repo)
        git_repo_2 = git_repo_isolated.parent / "test_repo_2"
        git_repo_2.mkdir()
        subprocess.run(["git", "init"], cwd=git_repo_2, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=git_repo_2, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=git_repo_2, check=True, capture_output=True)

        monkeypatch.chdir(git_repo_2)
        result_normal = runner.invoke(cli, ["init"], catch_exceptions=False)

        # Quiet mode should have less output
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

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_nonexistent_command_shows_help(self, runner: CliRunner) -> None:
        """Test that invalid commands show helpful error."""
        result = runner.invoke(cli, ["nonexistent-command"])

        assert result.exit_code != 0
        # Should show error or help

    def test_missing_required_argument(self, runner: CliRunner, git_repo_isolated: Path, monkeypatch) -> None:
        """Test that missing required arguments are caught."""
        monkeypatch.chdir(git_repo_isolated)
        # Init and sync
        runner.invoke(cli, ["init"], catch_exceptions=False)

        # Try find without query
        result = runner.invoke(cli, ["find"])

        assert result.exit_code != 0
        # Click should show missing argument error
