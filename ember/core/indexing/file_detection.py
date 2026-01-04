"""File detection service for determining files to index.

Handles git-based change detection to identify:
- Files that need indexing (added, modified, renamed)
- Files that have been deleted (for cleanup)
- Full reindex vs incremental sync decisions
"""

from ember.ports.repositories import MetaRepository
from ember.ports.vcs import VCS


class FileDetectionService:
    """Detects files needing indexing based on git state.

    Determines whether a full reindex or incremental sync is needed,
    and identifies which files have changed since the last index.
    """

    def __init__(self, vcs: VCS, meta_repo: MetaRepository) -> None:
        """Initialize file detection service.

        Args:
            vcs: Version control system adapter (git).
            meta_repo: Repository for metadata (last tree SHA, etc.).
        """
        self.vcs = vcs
        self.meta_repo = meta_repo

    def get_tree_sha(self, sync_mode: str) -> str:
        """Get tree SHA based on sync mode.

        Args:
            sync_mode: Sync mode (worktree, staged, or commit SHA).

        Returns:
            Tree SHA string.
        """
        if sync_mode == "worktree":
            return self.vcs.get_worktree_tree_sha()
        elif sync_mode == "staged":
            # For now, use worktree SHA (staged support can be added later)
            return self.vcs.get_worktree_tree_sha()
        else:
            # sync_mode is a commit SHA - get its tree SHA
            return self.vcs.get_tree_sha(ref=sync_mode)

    def determine_files_to_sync(
        self,
        tree_sha: str,
        force_reindex: bool,
    ) -> tuple[list[str], bool] | None:
        """Determine which files need to be synced based on git state.

        Args:
            tree_sha: Current tree SHA.
            force_reindex: Whether to force a full reindex.

        Returns:
            Tuple of (relative file paths, is_incremental) or None if no changes.
        """
        last_tree_sha = self.meta_repo.get("last_tree_sha")

        if force_reindex or last_tree_sha is None:
            # Full reindex: get all tracked files
            return (self.vcs.list_tracked_files(), False)

        if last_tree_sha == tree_sha:
            # No changes since last sync
            return None

        # Incremental sync: only get changed files
        changes = self.vcs.diff_files(from_sha=last_tree_sha, to_sha=tree_sha)

        # Get added and modified files (deletions handled separately)
        relative_files = [
            path for status, path in changes if status in ("added", "modified", "renamed")
        ]
        return (relative_files, True)

    def get_deleted_files(self, tree_sha: str) -> list[str]:
        """Get list of deleted files since last index.

        Args:
            tree_sha: Current tree SHA.

        Returns:
            List of relative paths that have been deleted.
        """
        last_tree_sha = self.meta_repo.get("last_tree_sha")
        if last_tree_sha is None:
            return []  # No previous index, nothing to delete

        # Get deleted files from git diff
        changes = self.vcs.diff_files(from_sha=last_tree_sha, to_sha=tree_sha)
        return [path for status, path in changes if status == "deleted"]

    def get_last_tree_sha(self) -> str | None:
        """Get the last indexed tree SHA.

        Returns:
            Last tree SHA or None if never indexed.
        """
        return self.meta_repo.get("last_tree_sha")
