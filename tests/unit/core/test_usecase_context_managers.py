"""Unit tests for use case context manager protocol.

Tests that SearchUseCase and IndexingUseCase properly implement the context
manager protocol for deterministic resource cleanup (closes repository
connections on exit).

This addresses issue #416: DX: Repository connections not explicitly closed
in CLI layer.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestSearchUseCaseContextManager:
    """Tests for SearchUseCase context manager protocol."""

    @pytest.fixture
    def mock_closeable_dependencies(self):
        """Create mock dependencies with close() methods."""
        text_search = MagicMock()
        vector_search = MagicMock()
        chunk_repo = MagicMock()
        embedder = MagicMock()

        # Configure embedder
        embedder.embed_texts.return_value = [[0.1, 0.2, 0.3]]

        # Configure searches to return empty results
        text_search.query.return_value = []
        vector_search.query.return_value = []

        return {
            "text_search": text_search,
            "vector_search": vector_search,
            "chunk_repo": chunk_repo,
            "embedder": embedder,
        }

    def test_context_manager_returns_self(self, mock_closeable_dependencies):
        """Test that __enter__ returns the use case instance."""
        from ember.core.retrieval.search_usecase import SearchUseCase

        use_case = SearchUseCase(**mock_closeable_dependencies)
        with use_case as ctx:
            assert ctx is use_case

    def test_context_manager_closes_all_repositories(self, mock_closeable_dependencies):
        """Test that __exit__ closes all repository connections."""
        from ember.core.retrieval.search_usecase import SearchUseCase

        use_case = SearchUseCase(**mock_closeable_dependencies)

        with use_case:
            pass

        # Verify close was called on all closeable dependencies
        mock_closeable_dependencies["text_search"].close.assert_called_once()
        mock_closeable_dependencies["vector_search"].close.assert_called_once()
        mock_closeable_dependencies["chunk_repo"].close.assert_called_once()

    def test_context_manager_closes_on_exception(self, mock_closeable_dependencies):
        """Test that connections are closed even when exception occurs."""
        from ember.core.retrieval.search_usecase import SearchUseCase

        use_case = SearchUseCase(**mock_closeable_dependencies)

        try:
            with use_case:
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Connections should still be closed
        mock_closeable_dependencies["text_search"].close.assert_called_once()
        mock_closeable_dependencies["vector_search"].close.assert_called_once()
        mock_closeable_dependencies["chunk_repo"].close.assert_called_once()

    def test_close_method_available(self, mock_closeable_dependencies):
        """Test that close() method is available on use case."""
        from ember.core.retrieval.search_usecase import SearchUseCase

        use_case = SearchUseCase(**mock_closeable_dependencies)
        use_case.close()

        mock_closeable_dependencies["text_search"].close.assert_called_once()
        mock_closeable_dependencies["vector_search"].close.assert_called_once()
        mock_closeable_dependencies["chunk_repo"].close.assert_called_once()

    def test_close_handles_missing_close_method(self, mock_closeable_dependencies):
        """Test close() handles dependencies without close() method gracefully."""
        from ember.core.retrieval.search_usecase import SearchUseCase

        # Remove close method from text_search
        del mock_closeable_dependencies["text_search"].close

        use_case = SearchUseCase(**mock_closeable_dependencies)

        # Should not raise
        use_case.close()

        # Other close methods should still be called
        mock_closeable_dependencies["vector_search"].close.assert_called_once()
        mock_closeable_dependencies["chunk_repo"].close.assert_called_once()

    def test_close_is_idempotent(self, mock_closeable_dependencies):
        """Test that close() can be called multiple times safely."""
        from ember.core.retrieval.search_usecase import SearchUseCase

        use_case = SearchUseCase(**mock_closeable_dependencies)
        use_case.close()
        use_case.close()  # Should not raise

        # close should be called twice (once per close() call)
        assert mock_closeable_dependencies["text_search"].close.call_count == 2


class TestIndexingUseCaseContextManager:
    """Tests for IndexingUseCase context manager protocol."""

    @pytest.fixture
    def mock_indexing_dependencies(self):
        """Create mock dependencies for IndexingUseCase with close() methods."""
        vcs = MagicMock()
        fs = MagicMock()
        chunk_usecase = MagicMock()
        embedder = MagicMock()
        chunk_repo = MagicMock()
        vector_repo = MagicMock()
        file_repo = MagicMock()
        meta_repo = MagicMock()

        # Configure embedder
        embedder.dim = 384
        embedder.fingerprint.return_value = "mock:384"

        return {
            "vcs": vcs,
            "fs": fs,
            "chunk_usecase": chunk_usecase,
            "embedder": embedder,
            "chunk_repo": chunk_repo,
            "vector_repo": vector_repo,
            "file_repo": file_repo,
            "meta_repo": meta_repo,
            "project_id": "test_project",
        }

    def test_context_manager_returns_self(self, mock_indexing_dependencies):
        """Test that __enter__ returns the use case instance."""
        from ember.core.indexing.index_usecase import IndexingUseCase

        use_case = IndexingUseCase(**mock_indexing_dependencies)
        with use_case as ctx:
            assert ctx is use_case

    def test_context_manager_closes_all_repositories(self, mock_indexing_dependencies):
        """Test that __exit__ closes all repository connections."""
        from ember.core.indexing.index_usecase import IndexingUseCase

        use_case = IndexingUseCase(**mock_indexing_dependencies)

        with use_case:
            pass

        # Verify close was called on all repository dependencies
        mock_indexing_dependencies["chunk_repo"].close.assert_called_once()
        mock_indexing_dependencies["vector_repo"].close.assert_called_once()
        mock_indexing_dependencies["file_repo"].close.assert_called_once()
        mock_indexing_dependencies["meta_repo"].close.assert_called_once()

    def test_context_manager_closes_on_exception(self, mock_indexing_dependencies):
        """Test that connections are closed even when exception occurs."""
        from ember.core.indexing.index_usecase import IndexingUseCase

        use_case = IndexingUseCase(**mock_indexing_dependencies)

        try:
            with use_case:
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Connections should still be closed
        mock_indexing_dependencies["chunk_repo"].close.assert_called_once()
        mock_indexing_dependencies["vector_repo"].close.assert_called_once()
        mock_indexing_dependencies["file_repo"].close.assert_called_once()
        mock_indexing_dependencies["meta_repo"].close.assert_called_once()

    def test_close_method_available(self, mock_indexing_dependencies):
        """Test that close() method is available on use case."""
        from ember.core.indexing.index_usecase import IndexingUseCase

        use_case = IndexingUseCase(**mock_indexing_dependencies)
        use_case.close()

        mock_indexing_dependencies["chunk_repo"].close.assert_called_once()
        mock_indexing_dependencies["vector_repo"].close.assert_called_once()
        mock_indexing_dependencies["file_repo"].close.assert_called_once()
        mock_indexing_dependencies["meta_repo"].close.assert_called_once()

    def test_close_handles_missing_close_method(self, mock_indexing_dependencies):
        """Test close() handles dependencies without close() method gracefully."""
        from ember.core.indexing.index_usecase import IndexingUseCase

        # Remove close method from file_repo
        del mock_indexing_dependencies["file_repo"].close

        use_case = IndexingUseCase(**mock_indexing_dependencies)

        # Should not raise
        use_case.close()

        # Other close methods should still be called
        mock_indexing_dependencies["chunk_repo"].close.assert_called_once()
        mock_indexing_dependencies["vector_repo"].close.assert_called_once()
        mock_indexing_dependencies["meta_repo"].close.assert_called_once()

    def test_close_is_idempotent(self, mock_indexing_dependencies):
        """Test that close() can be called multiple times safely."""
        from ember.core.indexing.index_usecase import IndexingUseCase

        use_case = IndexingUseCase(**mock_indexing_dependencies)
        use_case.close()
        use_case.close()  # Should not raise

        # close should be called twice (once per close() call)
        assert mock_indexing_dependencies["chunk_repo"].close.call_count == 2


class TestSimpleVectorSearchContextManager:
    """Tests for SimpleVectorSearch context manager protocol."""

    def test_context_manager_returns_self(self, db_path: Path):
        """Test that __enter__ returns the instance."""
        from ember.adapters.vss.simple_vector_search import SimpleVectorSearch

        adapter = SimpleVectorSearch(db_path)
        with adapter as ctx:
            assert ctx is adapter

    def test_context_manager_closes_connection(self, db_path: Path):
        """Test that __exit__ closes the database connection."""
        from ember.adapters.vss.simple_vector_search import SimpleVectorSearch

        adapter = SimpleVectorSearch(db_path)
        with adapter:
            # Access connection to ensure it's created
            _ = adapter._get_connection()
            assert adapter._conn is not None

        # After exiting context, connection should be closed
        assert adapter._conn is None

    def test_context_manager_closes_on_exception(self, db_path: Path):
        """Test that connection is closed even when exception occurs."""
        from ember.adapters.vss.simple_vector_search import SimpleVectorSearch

        adapter = SimpleVectorSearch(db_path)
        try:
            with adapter:
                _ = adapter._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Connection should still be closed
        assert adapter._conn is None

    def test_close_method_idempotent(self, db_path: Path):
        """Test that close() can be called multiple times safely."""
        from ember.adapters.vss.simple_vector_search import SimpleVectorSearch

        adapter = SimpleVectorSearch(db_path)
        adapter._get_connection()
        adapter.close()
        adapter.close()  # Should not raise
        assert adapter._conn is None

    def test_connection_reuse(self, db_path: Path):
        """Test that connections are reused across multiple operations."""
        from ember.adapters.vss.simple_vector_search import SimpleVectorSearch

        adapter = SimpleVectorSearch(db_path)
        conn1 = adapter._get_connection()
        conn2 = adapter._get_connection()

        # Should be the same connection object
        assert conn1 is conn2
        adapter.close()
