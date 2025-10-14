"""Indexing use case for syncing code chunks to the index.

This use case orchestrates the complete indexing pipeline:
1. Detect changed files via git
2. Chunk files into semantic units
3. Generate embeddings
4. Store chunks and vectors
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import blake3

from ember.core.chunking.chunk_usecase import ChunkFileRequest, ChunkFileUseCase
from ember.domain.entities import Chunk
from ember.ports.chunkers import ChunkData
from ember.ports.embedders import Embedder
from ember.ports.fs import FileSystem
from ember.ports.repositories import (
    ChunkRepository,
    FileRepository,
    MetaRepository,
    VectorRepository,
)
from ember.ports.vcs import VCS


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
        vectors_stored: Number of vectors stored.
        tree_sha: Git tree SHA that was indexed.
        success: Whether indexing succeeded.
        error: Error message if indexing failed.
    """

    files_indexed: int
    chunks_created: int
    chunks_updated: int
    vectors_stored: int
    tree_sha: str
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

    def execute(self, request: IndexRequest) -> IndexResponse:
        """Execute the indexing operation.

        Args:
            request: Indexing request with mode and filters.

        Returns:
            IndexResponse with statistics about what was indexed.
        """
        try:
            # Get current tree SHA based on sync mode
            tree_sha = self._get_tree_sha(request.repo_root, request.sync_mode)

            # Get files to index
            files_to_index = self._get_files_to_index(
                request.repo_root,
                tree_sha,
                request.path_filters,
                request.force_reindex,
            )

            # Index each file
            files_indexed = 0
            chunks_created = 0
            chunks_updated = 0
            vectors_stored = 0

            for file_path in files_to_index:
                result = self._index_file(
                    file_path=file_path,
                    repo_root=request.repo_root,
                    tree_sha=tree_sha,
                    sync_mode=request.sync_mode,
                )

                files_indexed += 1
                chunks_created += result["chunks_created"]
                chunks_updated += result["chunks_updated"]
                vectors_stored += result["vectors_stored"]

            # Update metadata with new tree SHA
            self.meta_repo.set("last_tree_sha", tree_sha)
            self.meta_repo.set("last_sync_mode", request.sync_mode)
            self.meta_repo.set("model_fingerprint", self.embedder.fingerprint())

            return IndexResponse(
                files_indexed=files_indexed,
                chunks_created=chunks_created,
                chunks_updated=chunks_updated,
                vectors_stored=vectors_stored,
                tree_sha=tree_sha,
                success=True,
                error=None,
            )

        except Exception as e:
            return IndexResponse(
                files_indexed=0,
                chunks_created=0,
                chunks_updated=0,
                vectors_stored=0,
                tree_sha="",
                success=False,
                error=str(e),
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
    ) -> list[Path]:
        """Get list of files that need to be indexed.

        Args:
            repo_root: Repository root path.
            tree_sha: Current tree SHA.
            path_filters: Optional path patterns to filter.
            force_reindex: Whether to reindex all files.

        Returns:
            List of absolute file paths to index.
        """
        # For MVP, just get all tracked files from git (returns relative paths)
        # TODO: Implement incremental indexing (only changed files)
        relative_files = self.vcs.list_tracked_files()

        # Convert to absolute paths
        files = [repo_root / f for f in relative_files]

        # Apply path filters if provided
        if path_filters:
            # Simple filtering for now (exact match or contains)
            filtered = []
            for f in files:
                for pattern in path_filters:
                    if pattern in str(f):
                        filtered.append(f)
                        break
            files = filtered

        return files

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
        # Read file content (returns bytes, decode to string)
        content_bytes = self.fs.read(file_path)
        content = content_bytes.decode("utf-8", errors="replace")

        # Detect language from file extension
        lang = self._detect_language(file_path)

        # Get relative path
        rel_path = file_path.relative_to(repo_root)

        # Chunk the file
        chunk_request = ChunkFileRequest(
            content=content,
            path=rel_path,
            lang=lang,
        )
        chunk_response = self.chunk_usecase.execute(chunk_request)

        if not chunk_response.success:
            # Skip files that fail to chunk
            return {"chunks_created": 0, "chunks_updated": 0, "vectors_stored": 0}

        # Compute file hash
        file_hash = blake3.blake3(content.encode("utf-8")).hexdigest()

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

            # Embed and store vector
            embeddings = self.embedder.embed_texts([chunk.content])
            self.vector_repo.add(
                chunk_id=chunk.id,
                embedding=embeddings[0],
                model_fingerprint=self.embedder.fingerprint(),
            )
            vectors_stored += 1

        # Track file
        self.file_repo.track_file(
            path=file_path,
            file_hash=file_hash,
            size=len(content.encode("utf-8")),
            mtime=time.time(),
        )

        return {
            "chunks_created": chunks_created,
            "chunks_updated": chunks_updated,
            "vectors_stored": vectors_stored,
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
