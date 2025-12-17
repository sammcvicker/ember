"""Status use case for showing ember index state and configuration."""

import logging
from dataclasses import dataclass
from pathlib import Path

from ember.domain.config import EmberConfig
from ember.ports.repositories import ChunkRepository, MetaRepository
from ember.ports.vcs import VCS

logger = logging.getLogger(__name__)


@dataclass
class StatusRequest:
    """Request to get ember status.

    Attributes:
        repo_root: Absolute path to repository root.
    """

    repo_root: Path


@dataclass
class StatusResponse:
    """Response containing ember status information.

    Attributes:
        initialized: Whether ember is initialized.
        repo_root: Repository root path.
        indexed_files: Number of unique files indexed.
        total_chunks: Total number of chunks in index.
        last_tree_sha: Last indexed tree SHA (or None if never synced).
        is_stale: Whether index is out of sync with working tree.
        model_fingerprint: Model fingerprint string (or None).
        config: Current configuration.
        success: Whether status check succeeded.
        error: Error message if status check failed.
    """

    initialized: bool
    repo_root: Path | None = None
    indexed_files: int = 0
    total_chunks: int = 0
    last_tree_sha: str | None = None
    is_stale: bool = False
    model_fingerprint: str | None = None
    config: EmberConfig | None = None
    success: bool = True
    error: str | None = None


class StatusUseCase:
    """Use case for retrieving ember index status."""

    def __init__(
        self,
        vcs: VCS,
        chunk_repo: ChunkRepository,
        meta_repo: MetaRepository,
        config: EmberConfig,
    ) -> None:
        """Initialize status use case.

        Args:
            vcs: Version control system adapter.
            chunk_repo: Chunk repository for counting chunks/files.
            meta_repo: Metadata repository for last sync info.
            config: Configuration object.
        """
        self.vcs = vcs
        self.chunk_repo = chunk_repo
        self.meta_repo = meta_repo
        self.config = config

    def execute(self, request: StatusRequest) -> StatusResponse:
        """Execute status check.

        Args:
            request: Status request with repo root.

        Returns:
            StatusResponse with index state and configuration.
        """
        try:
            # Get last indexed tree SHA
            last_tree_sha = self.meta_repo.get("last_tree_sha")

            # Get current worktree tree SHA
            current_tree_sha = self.vcs.get_worktree_tree_sha()

            # Check if index is stale
            is_stale = last_tree_sha != current_tree_sha

            # Get counts
            total_chunks = self.chunk_repo.count_chunks()
            indexed_files = self.chunk_repo.count_unique_files()

            # Get model fingerprint
            model_fingerprint = self.meta_repo.get("model_fingerprint")

            return StatusResponse(
                initialized=True,
                repo_root=request.repo_root,
                indexed_files=indexed_files,
                total_chunks=total_chunks,
                last_tree_sha=last_tree_sha,
                is_stale=is_stale,
                model_fingerprint=model_fingerprint,
                config=self.config,
                success=True,
                error=None,
            )

        except Exception as e:
            logger.error(f"Failed to get status: {e}", exc_info=True)
            return StatusResponse(
                initialized=True,
                repo_root=request.repo_root,
                success=False,
                error=str(e),
            )
