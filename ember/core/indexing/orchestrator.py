"""Indexing orchestrator that coordinates the indexing pipeline.

Separates pipeline orchestration from the core use case logic,
making both easier to test and maintain.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ember.core.indexing.types import IndexingContext, IndexRequest, IndexResponse
from ember.ports.progress import ProgressCallback

if TYPE_CHECKING:
    from ember.core.indexing.index_usecase import IndexingUseCase

logger = logging.getLogger(__name__)


class IndexingOrchestrator:
    """Orchestrates the indexing pipeline phases.

    Separates the indexing workflow into discrete, testable phases:
    1. Verification - Check model compatibility
    2. Detection - Identify files needing indexing
    3. Preparation - Handle deletions and load model
    4. Indexing - Process files and store chunks/vectors
    5. Finalization - Update metadata and create response
    """

    def __init__(self, usecase: IndexingUseCase) -> None:
        """Initialize orchestrator with reference to use case.

        Args:
            usecase: The IndexingUseCase containing dependencies.
        """
        self._usecase = usecase

    def run(
        self, request: IndexRequest, progress: ProgressCallback | None = None
    ) -> IndexResponse:
        """Execute the complete indexing pipeline.

        Args:
            request: Indexing request with mode and filters.
            progress: Optional progress callback for reporting progress.

        Returns:
            IndexResponse with statistics about what was indexed.
        """
        ctx = IndexingContext(request=request)

        # Phase 1: Verify model compatibility
        self._usecase._verify_model_compatibility(request.force_reindex)

        # Phase 2: Detect files to index
        ctx.tree_sha = self._usecase._get_tree_sha(request.repo_root, request.sync_mode)
        logger.debug(f"Tree SHA for indexing: {ctx.tree_sha}")

        ctx.files_to_index, ctx.is_incremental = self._usecase._get_files_to_index(
            request.repo_root,
            ctx.tree_sha,
            request.path_filters,
            request.force_reindex,
        )

        sync_type = "incremental" if ctx.is_incremental else "full"
        logger.info(f"Indexing {len(ctx.files_to_index)} file(s) ({sync_type} sync)")

        # Phase 3: Prepare - handle deletions and load model
        ctx.chunks_deleted = self._handle_deletions_if_incremental(ctx)
        self._load_model_if_needed(ctx, progress)

        # Phase 4: Index files
        ctx.stats = self._usecase._index_files_with_progress(
            files_to_index=ctx.files_to_index,
            repo_root=request.repo_root,
            tree_sha=ctx.tree_sha,
            sync_mode=request.sync_mode,
            sync_type=sync_type,
            progress=progress,
        )

        # Phase 5: Finalize - update metadata and create response
        self._usecase._update_metadata(ctx.tree_sha, request.sync_mode)

        return self._usecase._create_success_response(
            files_indexed=ctx.stats["files_indexed"],
            chunks_created=ctx.stats["chunks_created"],
            chunks_updated=ctx.stats["chunks_updated"],
            chunks_deleted=ctx.chunks_deleted,
            vectors_stored=ctx.stats["vectors_stored"],
            tree_sha=ctx.tree_sha,
            is_incremental=ctx.is_incremental,
            files_failed=ctx.stats["files_failed"],
        )

    def _handle_deletions_if_incremental(self, ctx: IndexingContext) -> int:
        """Handle deletions for incremental syncs.

        Args:
            ctx: Current indexing context.

        Returns:
            Number of chunks deleted.
        """
        if not ctx.is_incremental:
            return 0

        chunks_deleted = self._usecase._handle_deletions(
            repo_root=ctx.request.repo_root,
            tree_sha=ctx.tree_sha,
        )
        if chunks_deleted > 0:
            logger.info(f"Deleted {chunks_deleted} chunk(s) from removed files")
        return chunks_deleted

    def _load_model_if_needed(
        self, ctx: IndexingContext, progress: ProgressCallback | None
    ) -> None:
        """Load embedding model if there are files to index.

        Args:
            ctx: Current indexing context.
            progress: Optional progress callback.
        """
        if ctx.files_to_index:
            self._usecase._ensure_model_loaded(progress)
