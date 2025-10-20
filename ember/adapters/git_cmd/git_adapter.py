"""Git adapter implementing VCS protocol using subprocess git commands."""

import subprocess
from pathlib import Path

from ember.ports.vcs import FileStatus


class GitAdapter:
    """Git VCS adapter using subprocess calls to git CLI."""

    def __init__(self, repo_root: Path) -> None:
        """Initialize Git adapter.

        Args:
            repo_root: Absolute path to git repository root.

        Raises:
            RuntimeError: If repo_root is not a git repository.
        """
        self.repo_root = repo_root.resolve()
        # Verify this is a git repo
        if not self._is_git_repo():
            raise RuntimeError(f"Not a git repository: {self.repo_root}")

    def _is_git_repo(self) -> bool:
        """Check if repo_root is a git repository."""
        try:
            self._run_git(["rev-parse", "--git-dir"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _run_git(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run a git command in the repository.

        Args:
            args: Git command arguments (without 'git' prefix).
            check: Whether to raise CalledProcessError on non-zero exit.
            capture_output: Whether to capture stdout/stderr.

        Returns:
            CompletedProcess with command results.

        Raises:
            subprocess.CalledProcessError: If check=True and command fails.
        """
        cmd = ["git", "-C", str(self.repo_root)] + args
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            check=check,
        )
        return result

    def get_tree_sha(self, ref: str = "HEAD") -> str:
        """Get the tree SHA for a given ref.

        Args:
            ref: Git ref (commit SHA, branch name, tag, etc.). Default: HEAD.

        Returns:
            Tree SHA (40-char hex string).

        Raises:
            RuntimeError: If ref is invalid or not a git repository.
        """
        try:
            # Get tree SHA from commit ref using rev-parse
            result = self._run_git(["rev-parse", f"{ref}^{{tree}}"])
            tree_sha = result.stdout.decode().strip()
            return tree_sha
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to get tree SHA for ref '{ref}': {e.stderr.decode()}"
            ) from e

    def get_worktree_tree_sha(self) -> str:
        """Get tree SHA representing current worktree state.

        This computes a virtual tree SHA that represents the actual file contents
        in the worktree, including unstaged changes. We do this by:
        1. Temporarily adding all tracked files to the index with --intent-to-add
        2. Using git write-tree to compute the tree SHA
        3. Restoring the index to its previous state

        Returns:
            Tree SHA representing current worktree.

        Raises:
            RuntimeError: If not a git repository or git commands fail.
        """
        try:
            # Save current index state
            # First, get the index tree (what's currently staged)
            try:
                index_tree = self._run_git(["write-tree"]).stdout.decode().strip()
            except subprocess.CalledProcessError:
                # No index yet (initial commit scenario)
                index_tree = None

            # Add all tracked files to the index (update with worktree content)
            # This temporarily stages everything but doesn't commit
            self._run_git(["add", "-u"])  # Update tracked files only

            # Write the tree from the current index
            result = self._run_git(["write-tree"])
            worktree_tree_sha = result.stdout.decode().strip()

            # Restore index to previous state
            if index_tree:
                self._run_git(["read-tree", index_tree])
            else:
                # If there was no index, reset it
                self._run_git(["reset"], check=False)

            return worktree_tree_sha

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to compute worktree tree SHA: {e.stderr.decode()}"
            ) from e

    def diff_files(
        self,
        from_sha: str | None,
        to_sha: str,
    ) -> list[tuple[FileStatus, Path]]:
        """Get list of changed files between two tree SHAs.

        Args:
            from_sha: Starting tree SHA (None for empty tree).
            to_sha: Ending tree SHA.

        Returns:
            List of (status, path) tuples for changed files.
            Paths are relative to repository root.
        """
        try:
            # Use git diff-tree to compare tree objects
            # --no-commit-id: suppress commit ID output
            # --name-status: show names and status
            # -r: recurse into subdirectories
            # -M: detect renames
            from_ref = from_sha if from_sha else "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # empty tree SHA
            args = ["diff-tree", "--no-commit-id", "--name-status", "-r", "-M", from_ref, to_sha]

            result = self._run_git(args)
            output = result.stdout.decode().strip()

            if not output:
                return []

            # Parse output lines: "STATUS\tPATH" or "RNUM\tOLD\tNEW" for renames
            changes: list[tuple[FileStatus, Path]] = []
            for line in output.split("\n"):
                parts = line.split("\t")
                if len(parts) < 2:
                    continue

                status_code = parts[0]

                # Map git status codes to our FileStatus
                if status_code == "A":
                    status: FileStatus = "added"
                    path = Path(parts[1])
                elif status_code == "D":
                    status = "deleted"
                    path = Path(parts[1])
                elif status_code == "M":
                    status = "modified"
                    path = Path(parts[1])
                elif status_code.startswith("R"):  # R100, R090, etc.
                    status = "renamed"
                    # For renames, use the new path
                    path = Path(parts[2]) if len(parts) > 2 else Path(parts[1])
                else:
                    # Unknown status, skip
                    continue

                changes.append((status, path))

            return changes

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to diff trees {from_sha} -> {to_sha}: {e.stderr.decode()}"
            ) from e

    def get_file_content(self, path: Path, ref: str = "HEAD") -> bytes:
        """Get file content at a specific ref.

        Args:
            path: Path relative to repository root.
            ref: Git ref. Default: HEAD.

        Returns:
            File content as bytes.

        Raises:
            FileNotFoundError: If file doesn't exist at ref.
            RuntimeError: If ref is invalid.
        """
        try:
            # Use git show to get file content at ref
            result = self._run_git(["show", f"{ref}:{path}"])
            return result.stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode()
            if "does not exist" in stderr or "exists on disk, but not in" in stderr:
                raise FileNotFoundError(
                    f"File '{path}' not found at ref '{ref}'"
                ) from e
            raise RuntimeError(
                f"Failed to get content for '{path}' at ref '{ref}': {stderr}"
            ) from e

    def list_tracked_files(self) -> list[Path]:
        """Get list of all tracked files in the repository.

        Returns:
            List of paths relative to repository root.

        Raises:
            RuntimeError: If not a git repository.
        """
        try:
            result = self._run_git(["ls-files", "-z"])
            files_output = result.stdout.decode()

            if not files_output:
                return []

            # Split on null bytes and convert to Path objects
            tracked_files = [
                Path(f) for f in files_output.split("\0") if f
            ]
            return tracked_files

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to list tracked files: {e.stderr.decode()}"
            ) from e
