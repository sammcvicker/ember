"""Integration tests for auto-sync on search functionality."""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def auto_sync_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a test git repo for auto-sync testing."""
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
    from click.testing import CliRunner

    from ember.entrypoints.cli import init, sync

    runner = CliRunner()
    result = runner.invoke(init, [], obj={}, catch_exceptions=False)
    assert result.exit_code == 0

    # Initial sync
    result = runner.invoke(sync, [], obj={}, catch_exceptions=False)
    assert result.exit_code == 0

    return repo


@pytest.mark.slow
def test_auto_sync_on_stale_index(auto_sync_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that find auto-syncs when index is stale."""
    from click.testing import CliRunner

    from ember.entrypoints.cli import find

    # Modify file to make index stale
    test_file = auto_sync_repo / "test.py"
    test_file.write_text("def foo(): pass\ndef bar(): pass\n")
    subprocess.run(
        ["git", "add", "."], cwd=auto_sync_repo, check=True, capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "commit", "-m", "add bar"],
        cwd=auto_sync_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Run find - should auto-sync
    monkeypatch.chdir(auto_sync_repo)
    runner = CliRunner()
    result = runner.invoke(
        find, ["function"], obj={}, catch_exceptions=False
    )

    assert result.exit_code == 0
    # Should see sync message in stderr
    assert "Detected changes, syncing index" in result.stderr or "Synced" in result.stderr
    # Should find the new function
    assert "bar" in result.stdout


@pytest.mark.slow
def test_auto_sync_skipped_with_no_sync_flag(auto_sync_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that --no-sync flag skips auto-sync."""
    from click.testing import CliRunner

    from ember.entrypoints.cli import find

    # Modify file to make index stale
    test_file = auto_sync_repo / "test.py"
    test_file.write_text("def foo(): pass\ndef baz(): pass\n")
    subprocess.run(
        ["git", "add", "."], cwd=auto_sync_repo, check=True, capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "commit", "-m", "add baz"],
        cwd=auto_sync_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Run find with --no-sync - should NOT auto-sync
    monkeypatch.chdir(auto_sync_repo)
    runner = CliRunner()
    result = runner.invoke(
        find, ["function", "--no-sync"], obj={}, catch_exceptions=False
    )

    assert result.exit_code == 0
    # Should NOT see sync message
    assert "Syncing" not in result.stderr
    assert "Detected changes" not in result.stderr
    # Should NOT find the new function (stale results)
    assert "baz" not in result.stdout


@pytest.mark.slow
def test_auto_sync_noop_when_up_to_date(auto_sync_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that auto-sync is a no-op when index is up to date."""
    from click.testing import CliRunner

    from ember.entrypoints.cli import find

    # Run find twice - second time should not sync
    monkeypatch.chdir(auto_sync_repo)
    runner = CliRunner()

    # First find
    result1 = runner.invoke(
        find, ["function"], obj={}, catch_exceptions=False
    )
    assert result1.exit_code == 0

    # Second find - index is up to date, should not sync
    result2 = runner.invoke(
        find, ["function"], obj={}, catch_exceptions=False
    )
    assert result2.exit_code == 0
    # Should not see sync messages when already up to date
    # (No "Synced X files" message, just search results)
    assert "Synced" not in result2.stderr


@pytest.mark.slow
def test_auto_sync_with_json_output(auto_sync_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that auto-sync works with --json output."""
    from click.testing import CliRunner

    from ember.entrypoints.cli import find

    # Modify file
    test_file = auto_sync_repo / "test.py"
    test_file.write_text("def foo(): pass\ndef qux(): pass\n")
    subprocess.run(
        ["git", "add", "."], cwd=auto_sync_repo, check=True, capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "commit", "-m", "add qux"],
        cwd=auto_sync_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Run find with --json
    monkeypatch.chdir(auto_sync_repo)
    runner = CliRunner()
    result = runner.invoke(
        find, ["function", "--json"], obj={}, catch_exceptions=False
    )

    assert result.exit_code == 0
    # Sync messages should go to stderr, not stdout
    assert "Synced" not in result.stdout
    # stdout should be valid JSON
    import json

    data = json.loads(result.stdout)
    assert isinstance(data, list)
    # Should find the new function
    assert any("qux" in str(item) for item in data)
