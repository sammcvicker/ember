"""Git adapter implementing VCS protocol using subprocess git commands."""

import logging
import subprocess
from pathlib import Path

from ember.ports.vcs import FileStatus

# Standard git empty tree SHA (used when comparing against non-existent tree)
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

logger = logging.getLogger(__name__)


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

    def _format_git_error(
        self,
        error: subprocess.CalledProcessError,
        context: str,
    ) -> str:
        """Format git error with full context.

        Args:
            error: The CalledProcessError from git command.
            context: Human-readable description of what was being done.

        Returns:
            Formatted error message with exit code and stderr.
        """
        stderr = error.stderr.decode("utf-8", errors="replace").strip() if error.stderr else ""

        msg = f"{context} (git exit code {error.returncode})"
        if stderr:
            msg += f": {stderr}"
        else:
            msg += " (no error output from git)"

        return msg

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
            tree_sha = result.stdout.decode("utf-8", errors="replace").strip()
            return tree_sha
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""

            # Check for empty repository (no commits yet) - only for HEAD ref
            # Various git error messages for empty repos:
            # - "does not have any commit"
            # - "bad default revision 'HEAD'"
            # - "unknown revision or path not in the working tree" when asking for HEAD
            if ref == "HEAD" and (
                "does not have any commit" in stderr
                or "bad default revision 'HEAD'" in stderr.lower()
                or ("unknown revision" in stderr and "HEAD" in stderr)
            ):
                raise RuntimeError(
                    f"Repository at {self.repo_root} has no commits yet. "
                    f"Make an initial commit before indexing."
                ) from e

            # Generic error with full context
            error_msg = self._format_git_error(e, f"Failed to get tree SHA for ref '{ref}'")
            raise RuntimeError(error_msg) from e

    def get_worktree_tree_sha(self) -> str:
        """Get tree SHA representing current worktree state.

        This computes a virtual tree SHA that represents the actual file contents
        in the worktree, including unstaged changes. We do this by:
        1. Saving the current index state
        2. Temporarily adding all tracked files to the index
        3. Using git write-tree to compute the tree SHA
        4. Restoring the index to its previous state (guaranteed via try/finally)

        Returns:
            Tree SHA representing current worktree.

        Raises:
            RuntimeError: If not a git repository or git commands fail.
        """
        index_tree = None
        try:
            # Save current index state
            # First, get the index tree (what's currently staged)
            try:
                index_tree = self._run_git(["write-tree"]).stdout.decode("utf-8", errors="replace").strip()
            except subprocess.CalledProcessError:
                # No index yet (initial commit scenario)
                index_tree = None

            # Add all tracked files to the index (update with worktree content)
            # This temporarily stages everything but doesn't commit
            self._run_git(["add", "-u"])  # Update tracked files only

            # Write the tree from the current index
            result = self._run_git(["write-tree"])
            worktree_tree_sha = result.stdout.decode("utf-8", errors="replace").strip()

            return worktree_tree_sha

        except subprocess.CalledProcessError as e:
            error_msg = self._format_git_error(e, "Failed to compute worktree tree SHA")
            raise RuntimeError(error_msg) from e

        finally:
            # ALWAYS restore index to previous state, even if exception occurred
            # This prevents leaving the repository in a modified state
            if index_tree:
                try:
                    self._run_git(["read-tree", index_tree])
                except subprocess.CalledProcessError:
                    # Log but don't raise - original error is more important
                    logger.warning("Failed to restore index state after computing worktree tree SHA")
            else:
                # If there was no index, reset it
                try:
                    self._run_git(["reset"], check=False)
                except subprocess.CalledProcessError:
                    logger.warning("Failed to reset index after computing worktree tree SHA")

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
            from_ref = from_sha if from_sha else EMPTY_TREE_SHA
            args = ["diff-tree", "--no-commit-id", "--name-status", "-r", "-M", from_ref, to_sha]

            result = self._run_git(args)
            output = result.stdout.decode("utf-8", errors="replace").strip()

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
                elif status_code.startswith("C"):  # Copy
                    logger.warning(
                        f"Git status 'C' (copy) detected for path {parts[2] if len(parts) > 2 else '?'}. "
                        f"Treating as added file."
                    )
                    status = "added"
                    path = Path(parts[2]) if len(parts) > 2 else Path(parts[1])
                elif status_code == "T":  # Type change (e.g., file -> submodule)
                    logger.warning(
                        f"Git status 'T' (type change) detected for path {parts[1]}. "
                        f"Treating as modified file."
                    )
                    status = "modified"
                    path = Path(parts[1])
                else:
                    # Unknown status code - log and skip
                    path_info = parts[1] if len(parts) > 1 else "?"
                    logger.warning(
                        f"Unknown git status code '{status_code}' for path '{path_info}'. Skipping."
                    )
                    continue

                changes.append((status, path))

            return changes

        except subprocess.CalledProcessError as e:
            error_msg = self._format_git_error(e, f"Failed to diff trees {from_sha} -> {to_sha}")
            raise RuntimeError(error_msg) from e

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
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            if "does not exist" in stderr or "exists on disk, but not in" in stderr:
                raise FileNotFoundError(
                    f"File '{path}' not found at ref '{ref}'"
                ) from e
            error_msg = self._format_git_error(e, f"Failed to get content for '{path}' at ref '{ref}'")
            raise RuntimeError(error_msg) from e

    def list_tracked_files(self) -> list[Path]:
        """Get list of all tracked files in the repository.

        Returns:
            List of paths relative to repository root.

        Raises:
            RuntimeError: If not a git repository.
        """
        try:
            result = self._run_git(["ls-files", "-z"])
            files_output = result.stdout.decode("utf-8", errors="replace")

            if not files_output:
                return []

            # Split on null bytes and convert to Path objects
            tracked_files = [
                Path(f) for f in files_output.split("\0") if f
            ]
            return tracked_files

        except subprocess.CalledProcessError as e:
            error_msg = self._format_git_error(e, "Failed to list tracked files")
            raise RuntimeError(error_msg) from e
