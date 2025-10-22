"""Integration tests for sync command error handling (Issue #66)."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ember.entrypoints.cli import sync


@pytest.fixture
def sync_test_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a test git repo for sync error handling tests."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Create .gitignore to ignore .ember directory
    gitignore = repo / ".gitignore"
    gitignore.write_text(".ember/\n")

    # Create initial file
    test_file = repo / "test.py"
    test_file.write_text("def foo(): pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Initialize ember
    monkeypatch.chdir(repo)
    from ember.entrypoints.cli import init

    runner = CliRunner()
    result = runner.invoke(init, [], obj={}, catch_exceptions=False)
    assert result.exit_code == 0

    return repo


@pytest.mark.slow
def test_quick_check_message_differs_from_full_scan(
    sync_test_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that quick check and full scan show different messages."""
    monkeypatch.chdir(sync_test_repo)
    runner = CliRunner()

    # First sync - will index
    result1 = runner.invoke(sync, [], obj={}, catch_exceptions=False)
    assert result1.exit_code == 0

    # Second sync with no changes - should use quick check
    result2 = runner.invoke(sync, [], obj={}, catch_exceptions=False)
    assert result2.exit_code == 0
    assert "✓ No changes detected (quick check)" in result2.stdout

    # Force reindex - should skip quick check and do full reindex
    result3 = runner.invoke(sync, ["--reindex"], obj={}, catch_exceptions=False)
    assert result3.exit_code == 0
    # With --reindex, it will actually reindex the files
    assert "full sync" in result3.stdout or "incremental sync" in result3.stdout


@pytest.mark.slow
def test_mutually_exclusive_options_rejected(
    sync_test_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that mutually exclusive sync options are rejected."""
    monkeypatch.chdir(sync_test_repo)
    runner = CliRunner()

    # --rev and --staged should be mutually exclusive
    result = runner.invoke(sync, ["--rev", "HEAD", "--staged"], obj={})
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr

    # --worktree and --staged should be mutually exclusive
    result = runner.invoke(sync, ["--worktree", "--staged"], obj={})
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr

    # --rev and --worktree should be mutually exclusive
    result = runner.invoke(sync, ["--rev", "HEAD", "--worktree"], obj={})
    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr


@pytest.mark.slow
def test_single_sync_mode_options_work(
    sync_test_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that single sync mode options work correctly."""
    monkeypatch.chdir(sync_test_repo)
    runner = CliRunner()

    # Each option should work on its own
    result = runner.invoke(sync, ["--worktree"], obj={}, catch_exceptions=False)
    assert result.exit_code == 0

    result = runner.invoke(sync, ["--staged"], obj={}, catch_exceptions=False)
    assert result.exit_code == 0

    result = runner.invoke(sync, ["--rev", "HEAD"], obj={}, catch_exceptions=False)
    assert result.exit_code == 0
