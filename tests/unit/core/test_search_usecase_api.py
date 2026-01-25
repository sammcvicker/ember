"""Unit tests for SearchUseCase API pattern compliance.

Tests for the new SearchRequest/SearchResponse DTOs and execute() method
that align SearchUseCase with the standard use case API pattern.
"""

from unittest.mock import MagicMock

import pytest

from ember.core.retrieval.search_usecase import (
    SearchRequest,
    SearchResponse,
    SearchUseCase,
)
from ember.domain.entities import SearchResult, SearchResultSet


class TestSearchRequest:
    """Tests for SearchRequest dataclass."""

    def test_create_with_required_fields(self):
        """Test creating SearchRequest with only required fields."""
        request = SearchRequest(query_text="test query")

        assert request.query_text == "test query"
        assert request.topk == 20  # default
        assert request.path_filter is None
        assert request.lang_filter is None

    def test_create_with_all_fields(self):
        """Test creating SearchRequest with all fields."""
        request = SearchRequest(
            query_text="test query",
            topk=10,
            path_filter="*.py",
            lang_filter="python",
        )

        assert request.query_text == "test query"
        assert request.topk == 10
        assert request.path_filter == "*.py"
        assert request.lang_filter == "python"

    def test_empty_query_text_is_allowed_in_dto(self):
        """Test that empty query is allowed in DTO (validation is in use case)."""
        # The DTO should allow empty strings - validation happens in execute()
        request = SearchRequest(query_text="")
        assert request.query_text == ""


class TestSearchResponse:
    """Tests for SearchResponse dataclass."""

    def test_create_success_with_results(self):
        """Test creating a success response with results."""
        mock_results = [MagicMock(spec=SearchResult)]
        mock_result_set = MagicMock(spec=SearchResultSet)
        mock_result_set.results = mock_results
        mock_result_set.requested_count = 10
        mock_result_set.missing_chunks = 0
        mock_result_set.warning = None

        response = SearchResponse.create_success(result_set=mock_result_set)

        assert response.success is True
        assert response.error is None
        assert response.result_set is mock_result_set
        assert response.results == mock_results

    def test_create_success_with_empty_results(self):
        """Test creating a success response with empty results."""
        mock_result_set = MagicMock(spec=SearchResultSet)
        mock_result_set.results = []
        mock_result_set.requested_count = 10
        mock_result_set.missing_chunks = 0
        mock_result_set.warning = None

        response = SearchResponse.create_success(result_set=mock_result_set)

        assert response.success is True
        assert response.error is None
        assert response.results == []

    def test_create_error(self):
        """Test creating an error response."""
        response = SearchResponse.create_error("Embedder failed")

        assert response.success is False
        assert response.error == "Embedder failed"
        assert response.result_set is None
        assert response.results == []

    def test_results_property_empty_when_no_result_set(self):
        """Test that results property returns empty list when result_set is None."""
        response = SearchResponse.create_error("Some error")

        assert response.results == []


class TestSearchUseCaseExecute:
    """Tests for SearchUseCase.execute() method."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for SearchUseCase."""
        text_search = MagicMock()
        vector_search = MagicMock()
        chunk_repo = MagicMock()
        embedder = MagicMock()

        # Configure embedder to return a dummy embedding
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

    def test_execute_returns_success_response(self, mock_dependencies):
        """Test that execute() returns a SearchResponse on success."""
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="test query", topk=5)

        response = use_case.execute(request)

        assert response.success is True
        assert response.error is None
        assert response.result_set is not None
        assert isinstance(response.result_set, SearchResultSet)

    def test_execute_with_path_filter(self, mock_dependencies):
        """Test that execute() respects path_filter parameter."""
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(
            query_text="test query",
            topk=5,
            path_filter="*.py",
        )

        use_case.execute(request)

        # Verify path filter was passed to search
        mock_dependencies["text_search"].query.assert_called_once()
        call_kwargs = mock_dependencies["text_search"].query.call_args.kwargs
        assert call_kwargs.get("path_filter") == "*.py"

    def test_execute_with_lang_filter(self, mock_dependencies):
        """Test that execute() respects lang_filter parameter."""
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(
            query_text="test query",
            topk=5,
            lang_filter="py",  # Use short form recognized by language filter
        )

        response = use_case.execute(request)

        assert response.success is True
        # Lang filter is applied after retrieval, so we can't directly verify
        # it was passed to mocks, but we can verify successful execution

    def test_execute_catches_embedder_exception(self, mock_dependencies):
        """Test that execute() catches embedder exceptions."""
        mock_dependencies["embedder"].embed_texts.side_effect = RuntimeError(
            "Model failed to load"
        )
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="test query")

        response = use_case.execute(request)

        assert response.success is False
        assert "error" in response.error.lower() or "Model failed" in response.error

    def test_execute_catches_text_search_exception(self, mock_dependencies):
        """Test that execute() catches text search exceptions."""
        mock_dependencies["text_search"].query.side_effect = OSError(
            "Database locked"
        )
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="test query")

        response = use_case.execute(request)

        assert response.success is False
        assert response.error is not None

    def test_execute_catches_vector_search_exception(self, mock_dependencies):
        """Test that execute() catches vector search exceptions."""
        mock_dependencies["vector_search"].query.side_effect = ValueError(
            "Invalid dimensions"
        )
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="test query")

        response = use_case.execute(request)

        assert response.success is False
        assert response.error is not None

    def test_execute_reraises_keyboard_interrupt(self, mock_dependencies):
        """Test that execute() re-raises KeyboardInterrupt."""
        mock_dependencies["embedder"].embed_texts.side_effect = KeyboardInterrupt()
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="test query")

        with pytest.raises(KeyboardInterrupt):
            use_case.execute(request)

    def test_execute_reraises_system_exit(self, mock_dependencies):
        """Test that execute() re-raises SystemExit."""
        mock_dependencies["embedder"].embed_texts.side_effect = SystemExit()
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="test query")

        with pytest.raises(SystemExit):
            use_case.execute(request)

    def test_execute_returns_error_for_empty_query(self, mock_dependencies):
        """Test that execute() returns error for empty query text."""
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="")

        response = use_case.execute(request)

        assert response.success is False
        assert "empty" in response.error.lower() or "query" in response.error.lower()

    def test_execute_returns_error_for_whitespace_query(self, mock_dependencies):
        """Test that execute() returns error for whitespace-only query."""
        use_case = SearchUseCase(**mock_dependencies)
        request = SearchRequest(query_text="   ")

        response = use_case.execute(request)

        assert response.success is False


class TestSearchUseCaseBackwardCompatibility:
    """Tests to ensure backward compatibility with old search() method."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for SearchUseCase."""
        text_search = MagicMock()
        vector_search = MagicMock()
        chunk_repo = MagicMock()
        embedder = MagicMock()

        # Configure embedder to return a dummy embedding
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

    def test_search_method_still_works(self, mock_dependencies):
        """Test that the old search() method still works for backward compatibility."""
        from ember.domain.entities import Query

        use_case = SearchUseCase(**mock_dependencies)
        query = Query(text="test query", topk=5)

        # Old API should still work
        result = use_case.search(query)

        assert isinstance(result, SearchResultSet)

    def test_execute_and_search_produce_consistent_results(self, mock_dependencies):
        """Test that execute() and search() produce equivalent results."""
        from ember.domain.entities import Query

        use_case = SearchUseCase(**mock_dependencies)

        # Using execute()
        request = SearchRequest(query_text="test query", topk=5)
        response = use_case.execute(request)

        # Using search()
        query = Query(text="test query", topk=5)
        result_set = use_case.search(query)

        # Both should produce same results (empty in this case with mocks)
        assert response.result_set.results == result_set.results
        assert response.result_set.requested_count == result_set.requested_count
