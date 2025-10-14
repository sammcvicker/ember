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
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    (repo / "file1.txt").write_text("Hello world\n")
    (repo / "file2.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
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


def test_get_worktree_tree_sha_with_unstaged_changes(
    git_adapter: GitAdapter, git_repo: Path
):
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
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Second commit"],
        cwd=git_repo,
        check=True,
        capture_output=True,
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
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Delete file"],
        cwd=git_repo,
        check=True,
        capture_output=True,
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
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Rename file"],
        cwd=git_repo,
        check=True,
        capture_output=True,
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
