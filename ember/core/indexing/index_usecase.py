"""Indexing use case for syncing code chunks to the index.

This use case orchestrates the complete indexing pipeline:
1. Detect changed files via git
2. Chunk files into semantic units
3. Generate embeddings
4. Store chunks and vectors
"""

import logging
import time
from pathlib import Path

from ember.core.chunking.chunk_usecase import ChunkFileRequest, ChunkFileUseCase
from ember.core.indexing.chunk_storage import ChunkStorageService
from ember.core.indexing.file_detection import FileDetectionService
from ember.core.indexing.file_filter import FileFilterService
from ember.core.indexing.file_preprocessor import FilePreprocessor, PreprocessedFile
from ember.core.indexing.orchestrator import IndexingOrchestrator
from ember.core.indexing.types import (
    IndexRequest,
    IndexResponse,
    ModelMismatchError,
)
from ember.core.use_case_errors import (
    format_error_message,
    log_use_case_error,
)
from ember.domain.entities import Chunk
from ember.ports.chunkers import ChunkData
from ember.ports.embedders import Embedder
from ember.ports.fs import FileSystem
from ember.ports.progress import ProgressCallback
from ember.ports.repositories import (
    ChunkRepository,
    FileRepository,
    MetaRepository,
    VectorRepository,
)
from ember.ports.vcs import VCS

logger = logging.getLogger(__name__)


class IndexingUseCase:
    """Use case for indexing code files into searchable chunks.

    Coordinates git change detection, chunking, embedding, and storage
    to maintain an up-to-date index of the codebase.
    """

    def __init__(
        self,
        vcs: VCS,
        fs: FileSystem,
        chunk_usecase: ChunkFileUseCase,
        embedder: Embedder,
        chunk_repo: ChunkRepository,
        vector_repo: VectorRepository,
        file_repo: FileRepository,
        meta_repo: MetaRepository,
        project_id: str,
        *,
        file_preprocessor: FilePreprocessor | None = None,
        chunk_storage: ChunkStorageService | None = None,
        file_detection: FileDetectionService | None = None,
        file_filter: FileFilterService | None = None,
    ) -> None:
        """Initialize indexing use case.

        Args:
            vcs: Version control system adapter (git).
            fs: File system adapter for reading files.
            chunk_usecase: Use case for chunking files.
            embedder: Embedding model for generating vectors.
            chunk_repo: Repository for storing chunks.
            vector_repo: Repository for storing vectors.
            file_repo: Repository for tracking indexed files.
            meta_repo: Repository for metadata (last tree SHA, etc.).
            project_id: Project identifier (typically repo root hash).
            file_preprocessor: Optional preprocessor service (created if not provided).
            chunk_storage: Optional chunk storage service (created if not provided).
            file_detection: Optional file detection service (created if not provided).
            file_filter: Optional file filter service (created if not provided).
        """
        self.vcs = vcs
        self.fs = fs
        self.chunk_usecase = chunk_usecase
        self.embedder = embedder
        self.chunk_repo = chunk_repo
        self.vector_repo = vector_repo
        self.file_repo = file_repo
        self.meta_repo = meta_repo
        self.project_id = project_id

        # Create services if not provided (dependency injection with defaults)
        self.file_preprocessor = file_preprocessor or FilePreprocessor(fs)
        self.chunk_storage = chunk_storage or ChunkStorageService(
            chunk_repo, vector_repo, embedder
        )
        self.file_detection = file_detection or FileDetectionService(vcs, meta_repo)
        self.file_filter = file_filter or FileFilterService()

    def _create_error_response(self, error: str) -> IndexResponse:
        """Create a standardized error response with zero counts."""
        return IndexResponse.create_error(error)

    def _verify_model_compatibility(self, force_reindex: bool) -> None:
        """Verify embedding model compatibility. Raises ModelMismatchError if changed."""
        stored_fingerprint = self.meta_repo.get("model_fingerprint")
        current_fingerprint = self.embedder.fingerprint()

        if stored_fingerprint and stored_fingerprint != current_fingerprint:
            if force_reindex:
                logger.info(
                    f"Embedding model changed: {stored_fingerprint} → {current_fingerprint}. "
                    "Rebuilding index with new model."
                )
            else:
                raise ModelMismatchError(
                    stored_model=stored_fingerprint,
                    current_model=current_fingerprint,
                )

    def _ensure_model_loaded(self, progress: ProgressCallback | None) -> None:
        """Eagerly load embedding model before indexing to prevent misleading progress."""
        if hasattr(self.embedder, "ensure_loaded"):
            logger.debug("Loading embedding model")
            if progress:
                progress.on_start(1, "Loading embedding model")
            self.embedder.ensure_loaded()  # type: ignore[attr-defined]
            if progress:
                progress.on_complete()

    def _index_files_with_progress(
        self,
        files_to_index: list[Path],
        repo_root: Path,
        tree_sha: str,
        sync_mode: str,
        sync_type: str,
        progress: ProgressCallback | None,
    ) -> dict[str, int]:
        """Index all files with progress reporting. Returns counts dict."""
        files_indexed = 0
        chunks_created = 0
        chunks_updated = 0
        vectors_stored = 0
        files_failed = 0

        # Report progress start
        if progress and files_to_index:
            progress.on_start(len(files_to_index), f"Indexing files ({sync_type})")

        for idx, file_path in enumerate(files_to_index, start=1):
            # Report progress for current file
            if progress:
                rel_path = file_path.relative_to(repo_root)
                progress.on_progress(idx, str(rel_path))

            result = self._index_file(
                file_path=file_path,
                repo_root=repo_root,
                tree_sha=tree_sha,
                sync_mode=sync_mode,
            )

            files_indexed += 1
            chunks_created += result["chunks_created"]
            chunks_updated += result["chunks_updated"]
            vectors_stored += result["vectors_stored"]
            files_failed += result["failed"]

        # Report completion
        if progress and files_to_index:
            progress.on_complete()

        return {
            "files_indexed": files_indexed,
            "chunks_created": chunks_created,
            "chunks_updated": chunks_updated,
            "vectors_stored": vectors_stored,
            "files_failed": files_failed,
        }

    def _update_metadata(self, tree_sha: str, sync_mode: str) -> None:
        """Update metadata after successful indexing."""
        self.meta_repo.set("last_tree_sha", tree_sha)
        self.meta_repo.set("last_sync_mode", sync_mode)
        self.meta_repo.set("model_fingerprint", self.embedder.fingerprint())

    def _create_success_response(
        self,
        files_indexed: int,
        chunks_created: int,
        chunks_updated: int,
        chunks_deleted: int,
        vectors_stored: int,
        tree_sha: str,
        is_incremental: bool,
        files_failed: int = 0,
    ) -> IndexResponse:
        """Create a success response with indexing statistics.

        Args:
            files_indexed: Number of files processed.
            chunks_created: Number of chunks created.
            chunks_updated: Number of chunks updated.
            chunks_deleted: Number of chunks deleted.
            vectors_stored: Number of vectors stored.
            tree_sha: Git tree SHA that was indexed.
            is_incremental: Whether this was an incremental sync.
            files_failed: Number of files that failed to chunk.

        Returns:
            IndexResponse with success=True and all statistics.
        """
        log_msg = (
            f"Indexing complete: {files_indexed} files, "
            f"{chunks_created} chunks created, {chunks_updated} updated, "
            f"{chunks_deleted} deleted, {vectors_stored} vectors stored"
        )
        if files_failed > 0:
            log_msg += f", {files_failed} failed"
        logger.info(log_msg)

        return IndexResponse.create_success(
            files_indexed=files_indexed,
            chunks_created=chunks_created,
            chunks_updated=chunks_updated,
            chunks_deleted=chunks_deleted,
            vectors_stored=vectors_stored,
            tree_sha=tree_sha,
            is_incremental=is_incremental,
            files_failed=files_failed,
        )

    def execute(
        self, request: IndexRequest, progress: ProgressCallback | None = None
    ) -> IndexResponse:
        """Execute the indexing operation.

        Delegates to IndexingOrchestrator for the pipeline execution,
        handling all error cases uniformly.

        Error handling contract:
            - KeyboardInterrupt/SystemExit are re-raised (user wants to exit)
            - All other exceptions are caught and converted to error responses
            - See ember.core.use_case_errors for the error handling pattern

        Args:
            request: Indexing request with mode and filters.
            progress: Optional progress callback for reporting progress.

        Returns:
            IndexResponse with statistics about what was indexed.
        """
        logger.info(f"Starting indexing for {request.repo_root} (mode: {request.sync_mode})")

        try:
            orchestrator = IndexingOrchestrator(self)
            return orchestrator.run(request, progress)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Indexing interrupted by user")
            raise
        except Exception as e:
            log_use_case_error(e, "indexing")
            return self._create_error_response(format_error_message(e, "indexing"))

    def _get_tree_sha(self, repo_root: Path, sync_mode: str) -> str:
        """Get tree SHA based on sync mode.

        Args:
            repo_root: Repository root path (unused - VCS is already repo-scoped).
            sync_mode: Sync mode (worktree, staged, or commit SHA).

        Returns:
            Tree SHA string.
        """
        return self.file_detection.get_tree_sha(sync_mode)

    def _get_files_to_index(
        self,
        repo_root: Path,
        tree_sha: str,
        path_filters: list[str],
        force_reindex: bool,
    ) -> tuple[list[Path], bool]:
        """Get list of files that need to be indexed.

        Args:
            repo_root: Repository root path.
            tree_sha: Current tree SHA.
            path_filters: Optional path patterns to filter.
            force_reindex: Whether to reindex all files.

        Returns:
            Tuple of (list of absolute file paths to index, is_incremental flag).
        """
        # Determine which files need syncing based on git state
        sync_result = self.file_detection.determine_files_to_sync(tree_sha, force_reindex)
        if sync_result is None:
            return ([], False)  # No changes since last sync

        relative_files, is_incremental = sync_result

        # Convert to absolute paths
        files = [repo_root / f for f in relative_files]

        # Filter to only include code files (skip docs, data, binary files)
        files = self.file_filter.filter_code_files(files)

        # Apply path filters if provided
        if path_filters:
            files = self.file_filter.apply_path_filters(files, path_filters, repo_root)

        return (files, is_incremental)

    def _handle_deletions(
        self,
        repo_root: Path,
        tree_sha: str,
    ) -> int:
        """Handle deleted files by removing their chunks.

        Args:
            repo_root: Repository root path.
            tree_sha: Current tree SHA.

        Returns:
            Number of chunks deleted.
        """
        # Get last indexed tree SHA
        last_tree_sha = self.file_detection.get_last_tree_sha()
        if last_tree_sha is None:
            return 0  # No previous index, nothing to delete

        # Get deleted files
        deleted_files = self.file_detection.get_deleted_files(tree_sha)

        # Delete chunks for each deleted file
        total_deleted = 0
        for file_path in deleted_files:
            # Delete all chunks for this file (using last_tree_sha since file no longer exists in new tree)
            deleted_count = self.chunk_repo.delete_by_path(path=file_path, tree_sha=last_tree_sha)
            total_deleted += deleted_count

        return total_deleted

    def _index_file(
        self,
        file_path: Path,
        repo_root: Path,
        tree_sha: str,
        sync_mode: str,
    ) -> dict[str, int]:
        """Index a single file.

        This method orchestrates the file indexing pipeline:
        1. Preprocess file (read, hash, decode, detect language)
        2. Chunk the file content
        3. Delete old chunks and store new ones with embeddings
        4. Track file metadata

        Args:
            file_path: Absolute path to file.
            repo_root: Repository root path.
            tree_sha: Current tree SHA.
            sync_mode: Sync mode (for rev field).

        Returns:
            Dict with counts: chunks_created, chunks_updated, vectors_stored, failed.
            On failure, failed=1 and other counts are 0.
        """
        # Step 1: Preprocess file (I/O, hashing, decoding, language detection)
        preprocessed = self.file_preprocessor.preprocess(file_path, repo_root)

        # Step 2: Chunk the file
        chunk_request = ChunkFileRequest(
            content=preprocessed.content,
            path=preprocessed.rel_path,
            lang=preprocessed.lang,
        )
        chunk_response = self.chunk_usecase.execute(chunk_request)

        if not chunk_response.success:
            logger.warning(
                f"Failed to chunk {preprocessed.rel_path}: {chunk_response.error}. "
                f"Preserving existing chunks to avoid data loss."
            )
            return {"chunks_created": 0, "chunks_updated": 0, "vectors_stored": 0, "failed": 1}

        # Step 3: Delete old chunks (done AFTER chunking succeeds to prevent data loss)
        if not self.chunk_storage.delete_old_chunks(preprocessed.rel_path):
            return {"chunks_created": 0, "chunks_updated": 0, "vectors_stored": 0, "failed": 1}

        # Step 4: Create Chunk entities from ChunkData
        chunks = self._create_chunks(
            chunk_data_list=chunk_response.chunks,
            rel_path=preprocessed.rel_path,
            file_hash=preprocessed.file_hash,
            tree_sha=tree_sha,
            rev=sync_mode if sync_mode != "worktree" else "worktree",
        )

        # Step 5: Store chunks and embeddings (with rollback on failure)
        result = self.chunk_storage.store_chunks_and_embeddings(
            chunks, preprocessed.rel_path
        )

        if result.failed:
            return {"chunks_created": 0, "chunks_updated": 0, "vectors_stored": 0, "failed": 1}

        # Step 6: Track file metadata (non-critical, failures logged but don't fail indexing)
        self._track_file_metadata(file_path, preprocessed)

        return {
            "chunks_created": result.chunks_created,
            "chunks_updated": result.chunks_updated,
            "vectors_stored": result.vectors_stored,
            "failed": 0,
        }

    def _track_file_metadata(
        self, file_path: Path, preprocessed: PreprocessedFile
    ) -> None:
        """Track file metadata after successful indexing.

        Args:
            file_path: Absolute path to file.
            preprocessed: Preprocessed file data.
        """
        try:
            self.file_repo.track_file(
                path=file_path,
                file_hash=preprocessed.file_hash,
                size=preprocessed.file_size,
                mtime=time.time(),
            )
        except Exception as e:
            logger.warning(
                f"Failed to track file {preprocessed.rel_path}: {e}", exc_info=True
            )
            # Continue - file tracking is not critical

    def _create_chunks(
        self,
        chunk_data_list: list[ChunkData],
        rel_path: Path,
        file_hash: str,
        tree_sha: str,
        rev: str,
    ) -> list[Chunk]:
        """Create Chunk entities from ChunkData.

        Args:
            chunk_data_list: List of ChunkData from chunker.
            rel_path: Relative path to file.
            file_hash: Hash of entire file.
            tree_sha: Git tree SHA.
            rev: Git revision or "worktree".

        Returns:
            List of Chunk entities.
        """
        chunks = []
        for chunk_data in chunk_data_list:
            content_hash = Chunk.compute_content_hash(chunk_data.content)
            chunk_id = Chunk.compute_id(
                self.project_id,
                rel_path,
                chunk_data.start_line,
                chunk_data.end_line,
            )

            chunk = Chunk(
                id=chunk_id,
                project_id=self.project_id,
                path=rel_path,
                lang=chunk_data.lang,
                symbol=chunk_data.symbol,
                start_line=chunk_data.start_line,
                end_line=chunk_data.end_line,
                content=chunk_data.content,
                content_hash=content_hash,
                file_hash=file_hash,
                tree_sha=tree_sha,
                rev=rev,
            )
            chunks.append(chunk)

        return chunks

