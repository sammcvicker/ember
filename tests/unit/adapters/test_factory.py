"""Unit tests for use case factory module.

Tests the factory classes that centralize adapter instantiation,
ensuring clean architecture separation between CLI and adapters.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ember.adapters.factory import (
    ConfigFactory,
    DaemonFactory,
    EmbedderFactory,
    RepositoryFactory,
    UseCaseFactory,
)
from ember.domain.config import EmberConfig


class TestEmbedderFactory:
    """Tests for EmbedderFactory class."""

    def test_create_daemon_embedder_when_running(self):
        """When daemon is running, should return client without starting daemon."""
        config = EmberConfig.default()

        with patch(
            "ember.adapters.daemon.lifecycle.DaemonLifecycle"
        ) as mock_lifecycle_cls, patch(
            "ember.adapters.daemon.client.DaemonEmbedderClient"
        ) as mock_client_cls:
            mock_lifecycle = MagicMock()
            mock_lifecycle.is_running.return_value = True
            mock_lifecycle_cls.return_value = mock_lifecycle

            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            factory = EmbedderFactory(config)
            result = factory.create_embedder(show_progress=True)

            assert result == mock_client
            mock_lifecycle.is_running.assert_called_once()
            # Should not attempt to start daemon
            mock_lifecycle.start.assert_not_called()

    def test_create_daemon_embedder_starts_daemon_with_progress(self):
        """When daemon not running and show_progress=True, start with progress."""
        config = EmberConfig.default()

        with patch(
            "ember.adapters.daemon.lifecycle.DaemonLifecycle"
        ) as mock_lifecycle_cls, patch(
            "ember.adapters.daemon.client.DaemonEmbedderClient"
        ) as mock_client_cls, patch(
            "ember.core.cli_utils.ensure_daemon_with_progress"
        ) as mock_ensure:
            mock_lifecycle = MagicMock()
            mock_lifecycle.is_running.return_value = False
            mock_lifecycle_cls.return_value = mock_lifecycle

            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            factory = EmbedderFactory(config)
            result = factory.create_embedder(show_progress=True)

            assert result == mock_client
            mock_ensure.assert_called_once_with(mock_lifecycle, quiet=False)

    def test_create_daemon_embedder_starts_silently_without_progress(self):
        """When daemon not running and show_progress=False, start silently."""
        config = EmberConfig.default()

        with patch(
            "ember.adapters.daemon.lifecycle.DaemonLifecycle"
        ) as mock_lifecycle_cls, patch(
            "ember.adapters.daemon.client.DaemonEmbedderClient"
        ) as mock_client_cls:
            mock_lifecycle = MagicMock()
            mock_lifecycle.is_running.return_value = False
            mock_lifecycle_cls.return_value = mock_lifecycle

            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            factory = EmbedderFactory(config)
            result = factory.create_embedder(show_progress=False)

            assert result == mock_client
            mock_lifecycle.start.assert_called_once_with(foreground=False)

    def test_create_direct_embedder(self):
        """When mode is direct, should create embedder directly."""
        from ember.domain.config import ModelConfig

        config = EmberConfig(model=ModelConfig(mode="direct"))

        with patch(
            "ember.adapters.local_models.registry.create_embedder"
        ) as mock_create:
            mock_embedder = MagicMock()
            mock_create.return_value = mock_embedder

            factory = EmbedderFactory(config)
            result = factory.create_embedder()

            assert result == mock_embedder
            mock_create.assert_called_once_with(
                model_name=config.index.model,
                batch_size=config.index.batch_size,
            )


class TestUseCaseFactory:
    """Tests for UseCaseFactory class."""

    @pytest.fixture
    def mock_embedder(self):
        """Create a mock embedder with required properties."""
        embedder = MagicMock()
        embedder.dim = 768
        return embedder

    def test_create_search_usecase(self, mock_embedder):
        """Should create SearchUseCase with all dependencies."""
        db_path = Path("/tmp/test.db")

        with patch(
            "ember.adapters.fts.sqlite_fts.SQLiteFTS"
        ) as mock_fts_cls, patch(
            "ember.adapters.vss.sqlite_vec_adapter.SqliteVecAdapter"
        ) as mock_vec_cls, patch(
            "ember.adapters.sqlite.chunk_repository.SQLiteChunkRepository"
        ) as mock_chunk_cls, patch(
            "ember.core.retrieval.search_usecase.SearchUseCase"
        ) as mock_usecase_cls:
            mock_fts = MagicMock()
            mock_fts_cls.return_value = mock_fts

            mock_vec = MagicMock()
            mock_vec_cls.return_value = mock_vec

            mock_chunk_repo = MagicMock()
            mock_chunk_cls.return_value = mock_chunk_repo

            mock_usecase = MagicMock()
            mock_usecase_cls.return_value = mock_usecase

            factory = UseCaseFactory()
            result = factory.create_search_usecase(db_path, mock_embedder)

            assert result == mock_usecase
            mock_fts_cls.assert_called_once_with(db_path)
            mock_vec_cls.assert_called_once_with(db_path, vector_dim=768)
            mock_chunk_cls.assert_called_once_with(db_path)
            mock_usecase_cls.assert_called_once_with(
                text_search=mock_fts,
                vector_search=mock_vec,
                chunk_repo=mock_chunk_repo,
                embedder=mock_embedder,
            )

    def test_create_indexing_usecase(self, mock_embedder):
        """Should create IndexingUseCase with all dependencies."""
        repo_root = Path("/tmp/repo")
        db_path = Path("/tmp/test.db")
        config = EmberConfig.default()

        with patch(
            "ember.adapters.git_cmd.git_adapter.GitAdapter"
        ) as mock_git_cls, patch(
            "ember.adapters.fs.local.LocalFileSystem"
        ) as mock_fs_cls, patch(
            "ember.adapters.sqlite.chunk_repository.SQLiteChunkRepository"
        ) as mock_chunk_cls, patch(
            "ember.adapters.sqlite.vector_repository.SQLiteVectorRepository"
        ) as mock_vec_cls, patch(
            "ember.adapters.sqlite.file_repository.SQLiteFileRepository"
        ) as mock_file_cls, patch(
            "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
        ) as mock_meta_cls, patch(
            "ember.adapters.parsers.tree_sitter_chunker.TreeSitterChunker"
        ) as mock_ts_cls, patch(
            "ember.adapters.parsers.line_chunker.LineChunker"
        ) as mock_line_cls, patch(
            "ember.core.chunking.chunk_usecase.ChunkFileUseCase"
        ) as mock_chunk_usecase_cls, patch(
            "ember.core.indexing.index_usecase.IndexingUseCase"
        ) as mock_indexing_cls:
            # Setup mocks
            mock_git = MagicMock()
            mock_git_cls.return_value = mock_git

            mock_fs = MagicMock()
            mock_fs_cls.return_value = mock_fs

            mock_chunk_repo = MagicMock()
            mock_chunk_cls.return_value = mock_chunk_repo

            mock_vec_repo = MagicMock()
            mock_vec_cls.return_value = mock_vec_repo

            mock_file_repo = MagicMock()
            mock_file_cls.return_value = mock_file_repo

            mock_meta_repo = MagicMock()
            mock_meta_cls.return_value = mock_meta_repo

            mock_ts = MagicMock()
            mock_ts_cls.return_value = mock_ts

            mock_line = MagicMock()
            mock_line_cls.return_value = mock_line

            mock_chunk_usecase = MagicMock()
            mock_chunk_usecase_cls.return_value = mock_chunk_usecase

            mock_indexing = MagicMock()
            mock_indexing_cls.return_value = mock_indexing

            factory = UseCaseFactory()
            result = factory.create_indexing_usecase(
                repo_root, db_path, config, mock_embedder
            )

            assert result == mock_indexing
            mock_git_cls.assert_called_once_with(repo_root)
            mock_fs_cls.assert_called_once()
            mock_chunk_cls.assert_called_once_with(db_path)
            mock_vec_cls.assert_called_once_with(db_path, expected_dim=768)
            mock_file_cls.assert_called_once_with(db_path)
            mock_meta_cls.assert_called_once_with(db_path)
            mock_line_cls.assert_called_once_with(
                window_size=config.index.line_window,
                stride=config.index.line_stride,
            )


class TestRepositoryFactory:
    """Tests for RepositoryFactory class."""

    def test_create_git_adapter(self):
        """Should create GitAdapter instance."""
        repo_root = Path("/tmp/repo")

        with patch(
            "ember.adapters.git_cmd.git_adapter.GitAdapter"
        ) as mock_git_cls:
            mock_git = MagicMock()
            mock_git_cls.return_value = mock_git

            factory = RepositoryFactory()
            result = factory.create_git_adapter(repo_root)

            assert result == mock_git
            mock_git_cls.assert_called_once_with(repo_root)

    def test_create_meta_repository(self):
        """Should create SQLiteMetaRepository instance."""
        db_path = Path("/tmp/test.db")

        with patch(
            "ember.adapters.sqlite.meta_repository.SQLiteMetaRepository"
        ) as mock_meta_cls:
            mock_meta = MagicMock()
            mock_meta_cls.return_value = mock_meta

            factory = RepositoryFactory()
            result = factory.create_meta_repository(db_path)

            assert result == mock_meta
            mock_meta_cls.assert_called_once_with(db_path)

    def test_create_chunk_repository(self):
        """Should create SQLiteChunkRepository instance."""
        db_path = Path("/tmp/test.db")

        with patch(
            "ember.adapters.sqlite.chunk_repository.SQLiteChunkRepository"
        ) as mock_chunk_cls:
            mock_chunk = MagicMock()
            mock_chunk_cls.return_value = mock_chunk

            factory = RepositoryFactory()
            result = factory.create_chunk_repository(db_path)

            assert result == mock_chunk
            mock_chunk_cls.assert_called_once_with(db_path)


class TestDaemonFactory:
    """Tests for DaemonFactory class."""

    def test_create_daemon_lifecycle(self):
        """Should create DaemonLifecycle with parameters."""
        with patch(
            "ember.adapters.daemon.lifecycle.DaemonLifecycle"
        ) as mock_lifecycle_cls:
            mock_lifecycle = MagicMock()
            mock_lifecycle_cls.return_value = mock_lifecycle

            factory = DaemonFactory()
            result = factory.create_daemon_lifecycle(
                idle_timeout=600,
                model_name="test-model",
                batch_size=16,
            )

            assert result == mock_lifecycle
            mock_lifecycle_cls.assert_called_once_with(
                idle_timeout=600,
                model_name="test-model",
                batch_size=16,
            )

    def test_create_daemon_lifecycle_defaults(self):
        """Should create DaemonLifecycle with default parameters."""
        with patch(
            "ember.adapters.daemon.lifecycle.DaemonLifecycle"
        ) as mock_lifecycle_cls:
            mock_lifecycle = MagicMock()
            mock_lifecycle_cls.return_value = mock_lifecycle

            factory = DaemonFactory()
            result = factory.create_daemon_lifecycle()

            assert result == mock_lifecycle
            mock_lifecycle_cls.assert_called_once_with(
                idle_timeout=900,
                model_name=None,
                batch_size=32,
            )


class TestConfigFactory:
    """Tests for ConfigFactory class."""

    def test_create_config_provider(self):
        """Should create TomlConfigProvider instance."""
        with patch(
            "ember.adapters.config.toml_config_provider.TomlConfigProvider"
        ) as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider_cls.return_value = mock_provider

            factory = ConfigFactory()
            result = factory.create_config_provider()

            assert result == mock_provider
            mock_provider_cls.assert_called_once()

    def test_create_db_initializer(self):
        """Should create SqliteDatabaseInitializer instance."""
        with patch(
            "ember.adapters.sqlite.initializer.SqliteDatabaseInitializer"
        ) as mock_init_cls:
            mock_init = MagicMock()
            mock_init_cls.return_value = mock_init

            factory = ConfigFactory()
            result = factory.create_db_initializer()

            assert result == mock_init
            mock_init_cls.assert_called_once()


class TestFactoryIntegration:
    """Integration tests for factory classes working together."""

    def test_factory_module_imports_cleanly(self):
        """Verify factory module can be imported without side effects."""
        import importlib
        import sys

        # Remove cached module if exists
        module_name = "ember.adapters.factory"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Should import without errors
        module = importlib.import_module(module_name)

        # Verify all expected classes are present
        assert hasattr(module, "EmbedderFactory")
        assert hasattr(module, "UseCaseFactory")
        assert hasattr(module, "RepositoryFactory")
        assert hasattr(module, "DaemonFactory")
        assert hasattr(module, "ConfigFactory")
