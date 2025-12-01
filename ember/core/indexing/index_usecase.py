"""Indexing use case for syncing code chunks to the index.

This use case orchestrates the complete indexing pipeline:
1. Detect changed files via git
2. Chunk files into semantic units
3. Generate embeddings
4. Store chunks and vectors
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import blake3

from ember.core.chunking.chunk_usecase import ChunkFileRequest, ChunkFileUseCase
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

# Code file extensions to index (whitelist approach)
# Only source code files are indexed - data, config, docs, and binary files are skipped
CODE_FILE_EXTENSIONS = frozenset(
    {
        # Python
        ".py",
        ".pyi",
        # JavaScript/TypeScript
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        # Go
        ".go",
        # Rust
        ".rs",
        # Java/JVM
        ".java",
        ".kt",
        ".scala",
        # C/C++
        ".c",
        ".cpp",
        ".cc",
        ".cxx",
        ".h",
        ".hpp",
        ".hh",
        ".hxx",
        # C#
        ".cs",
        # Ruby
        ".rb",
        # PHP
        ".php",
        # Swift
        ".swift",
        # Shell
        ".sh",
        ".bash",
        ".zsh",
        # Web frameworks
        ".vue",
        ".svelte",
        # Other
        ".sql",
        ".proto",
        ".graphql",
    }
)


@dataclass
class IndexRequest:
    """Request to index (or re-index) files.

    Attributes:
        repo_root: Absolute path to repository root.
        sync_mode: Mode to sync - "worktree" (uncommitted changes), "staged", or commit SHA.
        path_filters: Optional list of path patterns to filter (e.g., ["src/**/*.py"]).
        force_reindex: If True, reindex even if files haven't changed.
    """

    repo_root: Path
    sync_mode: str = "worktree"
    path_filters: list[str] = field(default_factory=list)
    force_reindex: bool = False


@dataclass
class IndexResponse:
    """Response from indexing operation.

    Attributes:
        files_indexed: Number of files processed.
        chunks_created: Number of chunks created.
        chunks_updated: Number of chunks updated (deduplicated).
        chunks_deleted: Number of chunks deleted (from removed files).
        vectors_stored: Number of vectors stored.
        tree_sha: Git tree SHA that was indexed.
        files_failed: Number of files that failed to chunk.
        is_incremental: Whether this was an incremental sync (vs full reindex).
        success: Whether indexing succeeded.
        error: Error message if indexing failed.
    """

    files_indexed: int
    chunks_created: int
    chunks_updated: int
    chunks_deleted: int
    vectors_stored: int
    tree_sha: str
    files_failed: int = 0
    is_incremental: bool = False
    success: bool = True
    error: str | None = None


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

    def _create_error_response(self, error: str) -> IndexResponse:
        """Create a standardized error response with zero counts.

        Args:
            error: Error message to include in the response.

        Returns:
            IndexResponse with success=False and all counts set to zero.
        """
        return IndexResponse(
            files_indexed=0,
            chunks_created=0,
            chunks_updated=0,
            chunks_deleted=0,
            vectors_stored=0,
            tree_sha="",
            is_incremental=False,
            success=False,
            error=error,
        )

    def _verify_model_compatibility(self) -> None:
        """Verify embedding model compatibility with stored fingerprint.

        Logs a warning if the model has changed, indicating that existing
        vectors may be incompatible and a force reindex should be considered.
        """
        stored_fingerprint = self.meta_repo.get("model_fingerprint")
        current_fingerprint = self.embedder.fingerprint()

        if stored_fingerprint and stored_fingerprint != current_fingerprint:
            logger.warning(
                f"Embedding model changed: {stored_fingerprint} → {current_fingerprint}"
            )
            logger.warning(
                "Existing vectors may be incompatible with the new model. "
                "Run 'ember sync --force' to rebuild the index with the new model."
            )

    def _ensure_model_loaded(self, progress: ProgressCallback | None) -> None:
        """Eagerly load embedding model before indexing.

        Loading the model upfront (can take 2-3 seconds) prevents misleading
        progress reporting on the first file.

        Args:
            progress: Optional progress callback for reporting model loading.
        """
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
        """Index all files with progress reporting.

        Args:
            files_to_index: List of absolute file paths to index.
            repo_root: Repository root path.
            tree_sha: Current tree SHA.
            sync_mode: Sync mode (for rev field).
            sync_type: Human-readable sync type ("incremental" or "full").
            progress: Optional progress callback.

        Returns:
            Dict with counts: files_indexed, chunks_created, chunks_updated,
            vectors_stored, files_failed.
        """
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
        """Update metadata after successful indexing.

        Args:
            tree_sha: Current tree SHA.
            sync_mode: Sync mode that was used.
        """
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

        return IndexResponse(
            files_indexed=files_indexed,
            chunks_created=chunks_created,
            chunks_updated=chunks_updated,
            chunks_deleted=chunks_deleted,
            vectors_stored=vectors_stored,
            tree_sha=tree_sha,
            files_failed=files_failed,
            is_incremental=is_incremental,
            success=True,
            error=None,
        )

    def execute(
        self, request: IndexRequest, progress: ProgressCallback | None = None
    ) -> IndexResponse:
        """Execute the indexing operation.

        Args:
            request: Indexing request with mode and filters.
            progress: Optional progress callback for reporting progress.

        Returns:
            IndexResponse with statistics about what was indexed.
        """
        logger.info(f"Starting indexing for {request.repo_root} (mode: {request.sync_mode})")

        try:
            # Check if embedding model has changed
            self._verify_model_compatibility()

            # Get current tree SHA based on sync mode
            tree_sha = self._get_tree_sha(request.repo_root, request.sync_mode)
            logger.debug(f"Tree SHA for indexing: {tree_sha}")

            # Get files to index (returns tuple of files and is_incremental flag)
            files_to_index, is_incremental = self._get_files_to_index(
                request.repo_root,
                tree_sha,
                request.path_filters,
                request.force_reindex,
            )

            sync_type = "incremental" if is_incremental else "full"
            logger.info(f"Indexing {len(files_to_index)} file(s) ({sync_type} sync)")

            # Handle deletions for incremental sync
            chunks_deleted = 0
            if is_incremental:
                chunks_deleted = self._handle_deletions(
                    repo_root=request.repo_root,
                    tree_sha=tree_sha,
                )
                if chunks_deleted > 0:
                    logger.info(f"Deleted {chunks_deleted} chunk(s) from removed files")

            # Eagerly load embedding model before indexing
            if files_to_index:
                self._ensure_model_loaded(progress)

            # Index all files with progress reporting
            stats = self._index_files_with_progress(
                files_to_index=files_to_index,
                repo_root=request.repo_root,
                tree_sha=tree_sha,
                sync_mode=request.sync_mode,
                sync_type=sync_type,
                progress=progress,
            )

            # Update metadata with new tree SHA
            self._update_metadata(tree_sha, request.sync_mode)

            # Return success response
            return self._create_success_response(
                files_indexed=stats["files_indexed"],
                chunks_created=stats["chunks_created"],
                chunks_updated=stats["chunks_updated"],
                chunks_deleted=chunks_deleted,
                vectors_stored=stats["vectors_stored"],
                tree_sha=tree_sha,
                is_incremental=is_incremental,
                files_failed=stats["files_failed"],
            )

        except (KeyboardInterrupt, SystemExit):
            # Always let these propagate - user requested termination
            logger.info("Indexing interrupted by user")
            raise

        except FileNotFoundError as e:
            # File was deleted between detection and indexing
            logger.warning(f"File not found during indexing: {e}")
            return self._create_error_response(
                f"File not found: {e}. The file may have been deleted during indexing."
            )

        except PermissionError as e:
            # Permission denied reading file or accessing repository
            logger.error(f"Permission denied during indexing: {e}")
            return self._create_error_response(
                f"Permission denied: {e}. Check file and directory permissions."
            )

        except OSError as e:
            # I/O errors (disk full, network filesystem issues, etc.)
            logger.error(f"I/O error during indexing: {e}")
            return self._create_error_response(
                f"I/O error: {e}. Check disk space and filesystem access."
            )

        except ValueError as e:
            # Invalid configuration or parameters
            logger.error(f"Invalid configuration during indexing: {e}")
            return self._create_error_response(f"Configuration error: {e}")

        except RuntimeError as e:
            # Git errors, repository state errors, etc.
            logger.error(f"Runtime error during indexing: {e}")
            return self._create_error_response(f"Indexing error: {e}")

        except Exception:
            # Unexpected errors - log full traceback for debugging
            logger.exception("Unexpected error during indexing")
            return self._create_error_response(
                "Internal error during indexing. Check logs for details."
            )

    def _get_tree_sha(self, repo_root: Path, sync_mode: str) -> str:
        """Get tree SHA based on sync mode.

        Args:
            repo_root: Repository root path (unused - VCS is already repo-scoped).
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
        # Check if we can do incremental indexing
        last_tree_sha = self.meta_repo.get("last_tree_sha")

        if force_reindex or last_tree_sha is None:
            # Full reindex: get all tracked files
            relative_files = self.vcs.list_tracked_files()
            files = [repo_root / f for f in relative_files]
            is_incremental = False
        elif last_tree_sha == tree_sha:
            # No changes since last sync - skip indexing
            return ([], False)
        else:
            # Incremental sync: only get changed files
            changes = self.vcs.diff_files(from_sha=last_tree_sha, to_sha=tree_sha)

            # Get added and modified files (deletions handled separately)
            relative_files = [
                path for status, path in changes if status in ("added", "modified", "renamed")
            ]
            files = [repo_root / f for f in relative_files]
            is_incremental = True

        # Filter to only include code files (skip docs, data, binary files)
        files = [f for f in files if self._is_code_file(f)]

        # Apply path filters if provided
        if path_filters:
            # Use glob pattern matching for flexible filtering
            filtered = []
            for f in files:
                # Convert to relative path for pattern matching
                try:
                    rel_path = f.relative_to(repo_root)
                except ValueError:
                    # File is not relative to repo_root, skip it
                    continue

                # Check if file matches any of the glob patterns
                for pattern in path_filters:
                    if rel_path.match(pattern):
                        filtered.append(f)
                        break
            files = filtered

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
        last_tree_sha = self.meta_repo.get("last_tree_sha")
        if last_tree_sha is None:
            return 0  # No previous index, nothing to delete

        # Get deleted files from git diff
        changes = self.vcs.diff_files(from_sha=last_tree_sha, to_sha=tree_sha)
        deleted_files = [path for status, path in changes if status == "deleted"]

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

        Args:
            file_path: Absolute path to file.
            repo_root: Repository root path.
            tree_sha: Current tree SHA.
            sync_mode: Sync mode (for rev field).

        Returns:
            Dict with counts: chunks_created, chunks_updated, vectors_stored.
        """
        # Get relative path
        rel_path = file_path.relative_to(repo_root)

        # Read file content (returns bytes)
        content_bytes = self.fs.read(file_path)

        # Compute file hash and size from original bytes (avoids re-encoding)
        file_hash = blake3.blake3(content_bytes).hexdigest()
        file_size = len(content_bytes)

        # Decode to string for chunking (decode once)
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Fall back to replace mode if strict UTF-8 fails
            content = content_bytes.decode("utf-8", errors="replace")

        # Detect language from file extension
        lang = self._detect_language(file_path)

        # Chunk the file
        chunk_request = ChunkFileRequest(
            content=content,
            path=rel_path,
            lang=lang,
        )
        chunk_response = self.chunk_usecase.execute(chunk_request)

        if not chunk_response.success:
            # Log warning with file path and error for debugging
            logger.warning(
                f"Failed to chunk {rel_path}: {chunk_response.error}. "
                f"Preserving existing chunks to avoid data loss."
            )
            # Skip files that fail to chunk - preserve existing chunks to avoid data loss
            return {"chunks_created": 0, "chunks_updated": 0, "vectors_stored": 0, "failed": 1}

        # Clean up ALL old chunks for this file from any previous tree SHA
        # This prevents accumulation of duplicate chunks across multiple syncs
        # Since we're re-indexing this file now, we want to completely replace
        # all old chunks with the new chunks
        # NOTE: This is done AFTER validation to prevent data loss if chunking fails
        self.chunk_repo.delete_all_for_path(path=rel_path)

        # Create Chunk entities from ChunkData
        chunks = self._create_chunks(
            chunk_data_list=chunk_response.chunks,
            rel_path=rel_path,
            file_hash=file_hash,
            tree_sha=tree_sha,
            rev=sync_mode if sync_mode != "worktree" else "worktree",
        )

        # Store chunks and embed
        chunks_created = 0
        chunks_updated = 0
        vectors_stored = 0

        # First pass: store all chunks and track statistics
        for chunk in chunks:
            # Check if chunk already exists (by content hash)
            existing = self.chunk_repo.find_by_content_hash(chunk.content_hash)
            is_new = len(existing) == 0

            # Store chunk
            self.chunk_repo.add(chunk)

            if is_new:
                chunks_created += 1
            else:
                chunks_updated += 1

        # Second pass: batch embed all chunks at once for efficiency
        if chunks:
            # Collect all chunk contents
            contents = [chunk.content for chunk in chunks]

            # Single batch embedding call
            embeddings = self.embedder.embed_texts(contents)

            # Compute fingerprint once (avoids repeated function calls)
            model_fingerprint = self.embedder.fingerprint()

            # Store vectors for each chunk
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                self.vector_repo.add(
                    chunk_id=chunk.id,
                    embedding=embedding,
                    model_fingerprint=model_fingerprint,
                )
                vectors_stored += 1

        # Track file (use pre-computed file_size, avoids re-encoding)
        self.file_repo.track_file(
            path=file_path,
            file_hash=file_hash,
            size=file_size,
            mtime=time.time(),
        )

        return {
            "chunks_created": chunks_created,
            "chunks_updated": chunks_updated,
            "vectors_stored": vectors_stored,
            "failed": 0,
        }

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

    def _is_code_file(self, file_path: Path) -> bool:
        """Check if file is a code file that should be indexed.

        Args:
            file_path: Path to file.

        Returns:
            True if file should be indexed, False otherwise.
        """
        suffix = file_path.suffix.lower()
        return suffix in CODE_FILE_EXTENSIONS

    def _detect_language(self, file_path: Path) -> str:
        """Detect language from file extension.

        Args:
            file_path: Path to file.

        Returns:
            Language code (py, ts, go, rs, txt, etc.).
        """
        # Simple mapping based on extension
        ext_map = {
            ".py": "py",
            ".ts": "ts",
            ".tsx": "ts",
            ".js": "js",
            ".jsx": "js",
            ".go": "go",
            ".rs": "rs",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".md": "txt",
            ".txt": "txt",
        }

        suffix = file_path.suffix.lower()
        return ext_map.get(suffix, "txt")
