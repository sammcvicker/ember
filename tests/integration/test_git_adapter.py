"""Integration tests for Git adapter.

These tests create real git repositories and exercise all VCS protocol methods.
"""

import subprocess
from pathlib import Path

import pytest

from ember.adapters.git_cmd import GitAdapter


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with some commits.

    Returns:
        Path to the git repository root.
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Create initial commit
    (repo / "file1.txt").write_text("Hello world\n")
    (repo / "file2.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    return repo


@pytest.fixture
def git_adapter(git_repo: Path) -> GitAdapter:
    """Create a GitAdapter for the test repository."""
    return GitAdapter(git_repo)


def test_git_adapter_initialization(git_repo: Path):
    """Test GitAdapter can be initialized with a valid git repo."""
    adapter = GitAdapter(git_repo)
    assert adapter.repo_root == git_repo.resolve()


def test_git_adapter_rejects_non_repo(tmp_path: Path):
    """Test GitAdapter raises error for non-git directories."""
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()

    with pytest.raises(RuntimeError, match="Not a git repository"):
        GitAdapter(non_repo)


def test_get_tree_sha_for_head(git_adapter: GitAdapter):
    """Test getting tree SHA for HEAD."""
    tree_sha = git_adapter.get_tree_sha("HEAD")

    # Tree SHA should be 40 hex characters
    assert len(tree_sha) == 40
    assert all(c in "0123456789abcdef" for c in tree_sha)


def test_get_tree_sha_for_invalid_ref(git_adapter: GitAdapter):
    """Test getting tree SHA for invalid ref raises error."""
    with pytest.raises(RuntimeError, match="Failed to get tree SHA"):
        git_adapter.get_tree_sha("nonexistent-ref")


def test_get_worktree_tree_sha(git_adapter: GitAdapter, git_repo: Path):
    """Test getting tree SHA for current worktree."""
    tree_sha = git_adapter.get_worktree_tree_sha()

    # Should return valid tree SHA
    assert len(tree_sha) == 40
    assert all(c in "0123456789abcdef" for c in tree_sha)

    # For a clean worktree, should match HEAD tree
    head_tree = git_adapter.get_tree_sha("HEAD")
    assert tree_sha == head_tree


def test_get_worktree_tree_sha_with_unstaged_changes(git_adapter: GitAdapter, git_repo: Path):
    """Test worktree tree SHA changes with unstaged modifications."""
    # Get initial tree SHA
    initial_tree = git_adapter.get_worktree_tree_sha()

    # Modify a tracked file (unstaged change)
    (git_repo / "file1.txt").write_text("Modified content\n")

    # Worktree tree SHA should be different
    modified_tree = git_adapter.get_worktree_tree_sha()
    assert modified_tree != initial_tree

    # Should also differ from HEAD since changes are unstaged
    head_tree = git_adapter.get_tree_sha("HEAD")
    assert modified_tree != head_tree


def test_diff_files_between_commits(git_adapter: GitAdapter, git_repo: Path):
    """Test getting diff between two commits."""
    # Get initial tree SHA
    initial_tree = git_adapter.get_tree_sha("HEAD")

    # Create a new commit with changes
    (git_repo / "file3.txt").write_text("New file\n")
    (git_repo / "file1.txt").write_text("Modified\n")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Second commit"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    new_tree = git_adapter.get_tree_sha("HEAD")

    # Get diff
    changes = git_adapter.diff_files(initial_tree, new_tree)

    # Should have 2 changes: 1 added, 1 modified
    assert len(changes) == 2

    # Convert to dict for easier checking
    changes_dict = {str(path): status for status, path in changes}

    assert "file3.txt" in changes_dict
    assert changes_dict["file3.txt"] == "added"

    assert "file1.txt" in changes_dict
    assert changes_dict["file1.txt"] == "modified"


def test_diff_files_from_empty_tree(git_adapter: GitAdapter):
    """Test diff from empty tree (initial commit)."""
    current_tree = git_adapter.get_tree_sha("HEAD")

    # Diff from None (empty tree)
    changes = git_adapter.diff_files(None, current_tree)

    # Should show all files as added
    assert len(changes) >= 2  # file1.txt and file2.py

    statuses = [status for status, _ in changes]
    assert all(status == "added" for status in statuses)


def test_diff_files_with_deletions(git_adapter: GitAdapter, git_repo: Path):
    """Test diff detects file deletions."""
    initial_tree = git_adapter.get_tree_sha("HEAD")

    # Delete a file
    (git_repo / "file1.txt").unlink()
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Delete file"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    new_tree = git_adapter.get_tree_sha("HEAD")
    changes = git_adapter.diff_files(initial_tree, new_tree)

    # Should have 1 deletion
    assert len(changes) == 1
    status, path = changes[0]
    assert status == "deleted"
    assert str(path) == "file1.txt"


def test_diff_files_with_renames(git_adapter: GitAdapter, git_repo: Path):
    """Test diff detects file renames."""
    initial_tree = git_adapter.get_tree_sha("HEAD")

    # Rename a file
    (git_repo / "file1.txt").rename(git_repo / "renamed.txt")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Rename file"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    new_tree = git_adapter.get_tree_sha("HEAD")
    changes = git_adapter.diff_files(initial_tree, new_tree)

    # Should detect rename (git uses -M flag)
    # Rename should be reported as one change
    assert len(changes) == 1
    status, path = changes[0]
    assert status == "renamed"
    assert str(path) == "renamed.txt"  # New name


def test_get_file_content_at_head(git_adapter: GitAdapter):
    """Test getting file content at HEAD."""
    content = git_adapter.get_file_content(Path("file1.txt"), "HEAD")
    assert content == b"Hello world\n"


def test_get_file_content_nonexistent_file(git_adapter: GitAdapter):
    """Test getting content for nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="not found"):
        git_adapter.get_file_content(Path("nonexistent.txt"), "HEAD")


def test_get_file_content_invalid_ref(git_adapter: GitAdapter):
    """Test getting content with invalid ref raises RuntimeError."""
    with pytest.raises(RuntimeError, match="Failed to get content"):
        git_adapter.get_file_content(Path("file1.txt"), "invalid-ref")


def test_diff_files_returns_empty_for_identical_trees(git_adapter: GitAdapter):
    """Test diff returns empty list when trees are identical."""
    tree = git_adapter.get_tree_sha("HEAD")
    changes = git_adapter.diff_files(tree, tree)
    assert changes == []


def test_empty_repository_detection(tmp_path: Path):
    """Test that empty repository (no commits) is detected with clear error message."""
    repo = tmp_path / "empty_repo"
    repo.mkdir()

    # Initialize git repo but don't make any commits
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    adapter = GitAdapter(repo)

    # Should raise clear error about no commits
    with pytest.raises(RuntimeError, match="has no commits yet"):
        adapter.get_tree_sha("HEAD")


def test_worktree_tree_sha_restores_index_on_error(git_adapter: GitAdapter, git_repo: Path):
    """Test that index is restored even if error occurs during worktree tree computation."""
    # Stage a file
    (git_repo / "staged.txt").write_text("Staged content\n")
    subprocess.run(
        ["git", "add", "staged.txt"], cwd=git_repo, check=True, capture_output=True, timeout=5
    )

    # Get current index state
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    staged_before = result.stdout.decode().strip()
    assert "staged.txt" in staged_before

    # Call get_worktree_tree_sha (should succeed)
    git_adapter.get_worktree_tree_sha()

    # Verify index was restored (staged.txt should still be staged)
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    staged_after = result.stdout.decode().strip()
    assert staged_after == staged_before, "Index should be restored after get_worktree_tree_sha"


def test_error_messages_include_exit_code(tmp_path: Path):
    """Test that error messages include git exit code and context."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Create a commit
    (repo / "file.txt").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    adapter = GitAdapter(repo)

    # Try to get tree for invalid ref
    with pytest.raises(RuntimeError) as exc_info:
        adapter.get_tree_sha("invalid-ref-12345")

    error_msg = str(exc_info.value)
    # Should include exit code
    assert "exit code" in error_msg.lower()


def test_list_tracked_files(git_adapter: GitAdapter):
    """Test listing all tracked files in repository."""
    files = git_adapter.list_tracked_files()

    # Should include the files from fixture
    file_strs = [str(f) for f in files]
    assert "file1.txt" in file_strs
    assert "file2.py" in file_strs


def test_list_tracked_files_empty_repo_with_commit(tmp_path: Path):
    """Test listing tracked files in repo with no tracked files."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize and create empty commit
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "Empty commit"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    adapter = GitAdapter(repo)
    files = adapter.list_tracked_files()

    # Should return empty list for repo with no files
    assert files == []


def test_list_tracked_files_includes_untracked(git_adapter: GitAdapter, git_repo: Path):
    """Test that list_tracked_files includes untracked files."""
    # Create an untracked file
    (git_repo / "untracked.py").write_text("print('untracked')\n")

    files = git_adapter.list_tracked_files()
    file_strs = [str(f) for f in files]

    # Should include both tracked and untracked files
    assert "file1.txt" in file_strs  # Tracked
    assert "file2.py" in file_strs  # Tracked
    assert "untracked.py" in file_strs  # Untracked


def test_list_tracked_files_respects_gitignore(git_adapter: GitAdapter, git_repo: Path):
    """Test that list_tracked_files respects .gitignore patterns."""
    # Create .gitignore
    (git_repo / ".gitignore").write_text("*.log\nnode_modules/\n")

    # Create ignored files
    (git_repo / "debug.log").write_text("log content\n")
    (git_repo / "node_modules").mkdir()
    (git_repo / "node_modules" / "package.js").write_text("package content\n")

    # Create non-ignored file
    (git_repo / "app.py").write_text("print('app')\n")

    files = git_adapter.list_tracked_files()
    file_strs = [str(f) for f in files]

    # Should include non-ignored files
    assert "app.py" in file_strs

    # Should NOT include ignored files
    assert "debug.log" not in file_strs
    assert "node_modules/package.js" not in file_strs


def test_get_worktree_tree_sha_changes_with_untracked_files(
    git_adapter: GitAdapter, git_repo: Path
):
    """Test that worktree tree SHA changes when untracked files are added."""
    # Get initial tree SHA (clean worktree)
    initial_tree = git_adapter.get_worktree_tree_sha()

    # Create an untracked file
    (git_repo / "new_feature.py").write_text("def new_function():\n    pass\n")

    # Worktree tree SHA should change because of the untracked file
    modified_tree = git_adapter.get_worktree_tree_sha()
    assert modified_tree != initial_tree

    # Should also differ from HEAD since file is untracked
    head_tree = git_adapter.get_tree_sha("HEAD")
    assert modified_tree != head_tree


def test_get_worktree_tree_sha_ignores_gitignored_files(
    git_adapter: GitAdapter, git_repo: Path
):
    """Test that worktree tree SHA doesn't change for .gitignore'd files."""
    # Create .gitignore
    (git_repo / ".gitignore").write_text("*.tmp\n")
    subprocess.run(
        ["git", "add", ".gitignore"], cwd=git_repo, check=True, capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "commit", "-m", "Add gitignore"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Get tree SHA with clean worktree
    clean_tree = git_adapter.get_worktree_tree_sha()

    # Create a .gitignore'd file (should be ignored)
    (git_repo / "debug.tmp").write_text("temporary debug file\n")

    # Tree SHA should NOT change because file is ignored
    tree_with_ignored = git_adapter.get_worktree_tree_sha()
    assert tree_with_ignored == clean_tree


def test_get_worktree_tree_sha_raises_on_index_restoration_failure(
    git_adapter: GitAdapter, git_repo: Path, monkeypatch
):
    """Test that get_worktree_tree_sha raises exception when index restoration fails.

    This ensures users are notified about potential repository corruption rather
    than silently leaving the index in an inconsistent state.
    """
    original_run_git = git_adapter._run_git
    call_count = {"count": 0}

    def mock_run_git(args, check=True, capture_output=True):
        call_count["count"] += 1
        # Let add and write-tree succeed, then fail on read-tree (restoration)
        if args[0] == "read-tree":
            raise subprocess.CalledProcessError(1, ["git", "read-tree"], stderr=b"simulated failure")
        return original_run_git(args, check=check, capture_output=capture_output)

    monkeypatch.setattr(git_adapter, "_run_git", mock_run_git)

    # Should raise RuntimeError about restoration failure
    with pytest.raises(RuntimeError, match="index restoration failed"):
        git_adapter.get_worktree_tree_sha()


def test_get_worktree_tree_sha_raises_on_reset_failure_in_empty_repo(
    tmp_path: Path, monkeypatch
):
    """Test that get_worktree_tree_sha raises exception when reset fails for empty-index case.

    When there's no index tree (e.g., fresh repo), restoration uses 'git reset'.
    If that fails, we should raise an exception.
    """
    repo = tmp_path / "fresh_repo"
    repo.mkdir()

    # Initialize git repo with one commit but empty index tree scenario
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )
    # Create initial commit
    (repo / "file.txt").write_text("content\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    adapter = GitAdapter(repo)
    original_run_git = adapter._run_git
    first_write_tree = {"done": False}

    def mock_run_git(args, check=True, capture_output=True):
        # Make the first write-tree fail so index_tree is None
        if args[0] == "write-tree" and not first_write_tree["done"]:
            first_write_tree["done"] = True
            raise subprocess.CalledProcessError(1, ["git", "write-tree"], stderr=b"")
        # Then fail on reset (restoration)
        if args[0] == "reset":
            raise subprocess.CalledProcessError(1, ["git", "reset"], stderr=b"simulated reset failure")
        return original_run_git(args, check=check, capture_output=capture_output)

    monkeypatch.setattr(adapter, "_run_git", mock_run_git)

    with pytest.raises(RuntimeError, match="index restoration failed"):
        adapter.get_worktree_tree_sha()


def test_get_worktree_tree_sha_error_message_includes_recovery_guidance(
    git_adapter: GitAdapter, git_repo: Path, monkeypatch
):
    """Test that restoration failure error message includes helpful recovery guidance."""
    original_run_git = git_adapter._run_git

    def mock_run_git(args, check=True, capture_output=True):
        if args[0] == "read-tree":
            raise subprocess.CalledProcessError(1, ["git", "read-tree"], stderr=b"simulated failure")
        return original_run_git(args, check=check, capture_output=capture_output)

    monkeypatch.setattr(git_adapter, "_run_git", mock_run_git)

    with pytest.raises(RuntimeError) as exc_info:
        git_adapter.get_worktree_tree_sha()

    error_msg = str(exc_info.value).lower()
    # Should mention git status for verification
    assert "git status" in error_msg
