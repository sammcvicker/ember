"""Factory classes for use case and adapter instantiation.

This module centralizes the creation of use cases and their dependencies,
keeping the CLI layer free from direct adapter imports. This follows the
Clean Architecture principle that presentation layers should not know
about concrete infrastructure implementations.

The factories use lazy imports to avoid loading heavy dependencies
(like ML models) until they're actually needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ember.core.indexing.index_usecase import IndexingUseCase
    from ember.core.retrieval.search_usecase import SearchUseCase
    from ember.domain.config import EmberConfig


class Embedder(Protocol):
    """Protocol for embedder implementations."""

    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def fingerprint(self) -> str: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def ensure_loaded(self) -> None: ...


class EmbedderFactory:
    """Factory for creating embedder instances.

    Handles the complexity of daemon vs direct mode, daemon lifecycle
    management, and progress display.

    Args:
        config: EmberConfig with model and daemon settings.
    """

    def __init__(self, config: EmberConfig) -> None:
        """Initialize factory with configuration.

        Args:
            config: Configuration containing model and daemon settings.
        """
        self._config = config

    def create_embedder(self, show_progress: bool = True) -> Embedder:
        """Create embedder based on configuration.

        Args:
            show_progress: Show progress bar during daemon startup.

        Returns:
            Embedder instance (daemon client or direct).

        Raises:
            RuntimeError: If daemon fails to start.
            ValueError: If model name is not recognized.
        """
        model_name = self._config.index.model
        batch_size = self._config.index.batch_size

        if self._config.model.mode == "daemon":
            return self._create_daemon_embedder(model_name, batch_size, show_progress)
        else:
            return self._create_direct_embedder(model_name, batch_size)

    def _create_daemon_embedder(
        self,
        model_name: str,
        batch_size: int,
        show_progress: bool,
    ) -> Embedder:
        """Create daemon-based embedder.

        Args:
            model_name: Name of the embedding model.
            batch_size: Batch size for embedding.
            show_progress: Show progress during daemon startup.

        Returns:
            DaemonEmbedderClient instance.
        """
        # Lazy imports to avoid loading heavy dependencies at module level
        from ember.adapters.daemon.client import DaemonEmbedderClient
        from ember.adapters.daemon.lifecycle import DaemonLifecycle
        from ember.core.cli_utils import ensure_daemon_with_progress

        daemon_manager = DaemonLifecycle(
            idle_timeout=self._config.model.daemon_timeout,
            model_name=model_name,
            batch_size=batch_size,
        )

        # Start daemon if not already running
        if not daemon_manager.is_running():
            if show_progress:
                ensure_daemon_with_progress(daemon_manager, quiet=False)
            else:
                daemon_manager.start(foreground=False)

        return DaemonEmbedderClient(
            fallback=True,
            auto_start=False,  # Daemon already started above
            daemon_timeout=self._config.model.daemon_timeout,
            model_name=model_name,
            batch_size=batch_size,
        )

    def _create_direct_embedder(
        self,
        model_name: str,
        batch_size: int,
    ) -> Embedder:
        """Create direct embedder (no daemon).

        Args:
            model_name: Name of the embedding model.
            batch_size: Batch size for embedding.

        Returns:
            Direct embedder instance.
        """
        # Lazy import
        from ember.adapters.local_models.registry import (
            create_embedder as create_embedder_from_registry,
        )

        return create_embedder_from_registry(
            model_name=model_name,
            batch_size=batch_size,
        )


# Module-level alias for direct embedder creation (used by _create_direct_embedder)
def create_embedder_from_registry(model_name: str, batch_size: int) -> Embedder:
    """Create embedder directly from registry.

    This is a module-level function that provides access to the registry's
    create_embedder function with lazy import.
    """
    from ember.adapters.local_models.registry import create_embedder

    return create_embedder(model_name=model_name, batch_size=batch_size)


class DaemonFactory:
    """Factory for creating daemon-related instances.

    Handles daemon lifecycle management for daemon commands.
    """

    def create_daemon_lifecycle(
        self,
        idle_timeout: int = 900,
        model_name: str | None = None,
        batch_size: int = 32,
    ):
        """Create a DaemonLifecycle instance.

        Args:
            idle_timeout: Idle timeout in seconds.
            model_name: Name of the embedding model.
            batch_size: Batch size for embedding.

        Returns:
            DaemonLifecycle instance.
        """
        from ember.adapters.daemon.lifecycle import DaemonLifecycle

        return DaemonLifecycle(
            idle_timeout=idle_timeout,
            model_name=model_name,
            batch_size=batch_size,
        )


class ConfigFactory:
    """Factory for creating configuration-related instances."""

    def create_config_provider(self):
        """Create a TomlConfigProvider instance.

        Returns:
            TomlConfigProvider instance.
        """
        from ember.adapters.config.toml_config_provider import TomlConfigProvider

        return TomlConfigProvider()

    def create_db_initializer(self):
        """Create a SqliteDatabaseInitializer instance.

        Returns:
            SqliteDatabaseInitializer instance.
        """
        from ember.adapters.sqlite.initializer import SqliteDatabaseInitializer

        return SqliteDatabaseInitializer()


class RepositoryFactory:
    """Factory for creating lightweight repository instances.

    Used for quick operations like staleness checks that don't need
    the full use case infrastructure.
    """

    def create_git_adapter(self, repo_root: Path):
        """Create a GitAdapter instance.

        Args:
            repo_root: Repository root path.

        Returns:
            GitAdapter instance.
        """
        from ember.adapters.git_cmd.git_adapter import GitAdapter

        return GitAdapter(repo_root)

    def create_meta_repository(self, db_path: Path):
        """Create a SQLiteMetaRepository instance.

        Args:
            db_path: Path to the SQLite database.

        Returns:
            SQLiteMetaRepository instance.
        """
        from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository

        return SQLiteMetaRepository(db_path)

    def create_chunk_repository(self, db_path: Path):
        """Create a SQLiteChunkRepository instance.

        Args:
            db_path: Path to the SQLite database.

        Returns:
            SQLiteChunkRepository instance.
        """
        from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository

        return SQLiteChunkRepository(db_path)


class UseCaseFactory:
    """Factory for creating use case instances with all dependencies.

    Centralizes the complex dependency wiring for use cases, keeping
    the CLI layer clean and testable.
    """

    def create_search_usecase(
        self,
        db_path: Path,
        embedder: Embedder,
    ) -> SearchUseCase:
        """Create SearchUseCase with all required dependencies.

        Args:
            db_path: Path to the SQLite database.
            embedder: Embedder instance for query vectorization.

        Returns:
            Configured SearchUseCase ready for search operations.
        """
        # Lazy imports
        from ember.adapters.fts.sqlite_fts import SQLiteFTS
        from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
        from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
        from ember.core.retrieval.search_usecase import SearchUseCase

        text_search = SQLiteFTS(db_path)
        vector_search = SqliteVecAdapter(db_path, vector_dim=embedder.dim)
        chunk_repo = SQLiteChunkRepository(db_path)

        return SearchUseCase(
            text_search=text_search,
            vector_search=vector_search,
            chunk_repo=chunk_repo,
            embedder=embedder,
        )

    def create_indexing_usecase(
        self,
        repo_root: Path,
        db_path: Path,
        config: EmberConfig,
        embedder: Embedder,
    ) -> IndexingUseCase:
        """Create IndexingUseCase with all dependencies.

        Args:
            repo_root: Repository root path.
            db_path: Path to SQLite database.
            config: Configuration object with index settings.
            embedder: Embedder instance for generating embeddings.

        Returns:
            Initialized IndexingUseCase instance.
        """
        # Lazy imports
        import blake3

        from ember.adapters.fs.local import LocalFileSystem
        from ember.adapters.git_cmd.git_adapter import GitAdapter
        from ember.adapters.parsers.line_chunker import LineChunker
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
        from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
        from ember.adapters.sqlite.file_repository import SQLiteFileRepository
        from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
        from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
        from ember.core.chunking.chunk_usecase import ChunkFileUseCase
        from ember.core.indexing.index_usecase import IndexingUseCase

        # Initialize dependencies
        vcs = GitAdapter(repo_root)
        fs = LocalFileSystem()

        # Initialize repositories
        chunk_repo = SQLiteChunkRepository(db_path)
        vector_repo = SQLiteVectorRepository(db_path, expected_dim=embedder.dim)
        file_repo = SQLiteFileRepository(db_path)
        meta_repo = SQLiteMetaRepository(db_path)

        # Initialize chunking use case with config settings
        tree_sitter = TreeSitterChunker()
        line_chunker = LineChunker(
            window_size=config.index.line_window,
            stride=config.index.line_stride,
        )
        chunk_usecase = ChunkFileUseCase(tree_sitter, line_chunker)

        # Compute project ID (hash of repo root path)
        project_id = blake3.blake3(str(repo_root).encode("utf-8")).hexdigest()

        # Create and return indexing use case
        return IndexingUseCase(
            vcs=vcs,
            fs=fs,
            chunk_usecase=chunk_usecase,
            embedder=embedder,
            chunk_repo=chunk_repo,
            vector_repo=vector_repo,
            file_repo=file_repo,
            meta_repo=meta_repo,
            project_id=project_id,
        )
