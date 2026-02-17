"""Tests for surfacing tree-sitter parse failures to users.

Issue #438: Tree-sitter chunker silently returns empty list on parse failure.
This module tests the end-to-end flow of detecting, propagating, and displaying
parse failures from tree-sitter through the chunking use case and sync output.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ember.core.chunking.chunk_usecase import ChunkFileRequest, ChunkFileResponse, ChunkFileUseCase
from ember.ports.chunkers import ChunkData, ParseWarning


class TestParseWarningDataclass:
    """Tests for the ParseWarning dataclass."""

    def test_parse_warning_creation(self) -> None:
        """ParseWarning stores file path and reason."""
        warning = ParseWarning(
            path=Path("src/broken.py"),
            language="py",
            reason="Failed to parse as python: syntax error",
        )
        assert warning.path == Path("src/broken.py")
        assert warning.language == "py"
        assert "syntax error" in warning.reason

    def test_parse_warning_immutable(self) -> None:
        """ParseWarning is frozen (immutable)."""
        warning = ParseWarning(
            path=Path("test.py"),
            language="py",
            reason="parse error",
        )
        with pytest.raises(AttributeError):
            warning.path = Path("other.py")  # type: ignore[misc]


class TestChunkFileResponseWarnings:
    """Tests for parse warnings in ChunkFileResponse."""

    def test_response_has_empty_warnings_by_default(self) -> None:
        """ChunkFileResponse defaults to empty parse_warnings list."""
        response = ChunkFileResponse.create_success(
            chunks=[], strategy="none"
        )
        assert response.parse_warnings == []

    def test_response_create_success_with_warnings(self) -> None:
        """ChunkFileResponse can be created with parse warnings."""
        warning = ParseWarning(
            path=Path("broken.py"),
            language="py",
            reason="parse failed",
        )
        response = ChunkFileResponse.create_success(
            chunks=[], strategy="line-based", parse_warnings=[warning]
        )
        assert len(response.parse_warnings) == 1
        assert response.parse_warnings[0].path == Path("broken.py")
        assert response.success is True

    def test_error_response_has_empty_warnings(self) -> None:
        """Error responses have empty parse_warnings."""
        response = ChunkFileResponse.create_error("something broke")
        assert response.parse_warnings == []


class TestChunkUseCaseParseFailureFallback:
    """Tests for ChunkFileUseCase recording parse warnings on fallback."""

    def test_tree_sitter_parse_error_records_warning(self) -> None:
        """When tree-sitter raises ParseError, use case falls back and records warning."""
        from ember.ports.chunkers import ParseError

        mock_tree_sitter = MagicMock()
        mock_tree_sitter.supported_languages = {"py"}
        mock_tree_sitter.chunk_file.side_effect = ParseError(
            "Failed to parse test.py as python: unexpected token"
        )

        mock_line_chunker = MagicMock()
        mock_line_chunker.chunk_file.return_value = [
            ChunkData(
                start_line=1, end_line=5, content="line content",
                symbol=None, lang="py",
            )
        ]

        use_case = ChunkFileUseCase(mock_tree_sitter, mock_line_chunker)
        request = ChunkFileRequest(
            content="def broken(\n  return 42\n",
            path=Path("test.py"),
            lang="py",
        )

        response = use_case.execute(request)

        assert response.success is True
        assert response.strategy == "line-based"
        assert len(response.parse_warnings) == 1
        assert response.parse_warnings[0].path == Path("test.py")
        assert response.parse_warnings[0].language == "py"
        assert "unexpected token" in response.parse_warnings[0].reason

    def test_tree_sitter_success_no_warnings(self) -> None:
        """Successful tree-sitter parsing produces no warnings."""
        mock_tree_sitter = MagicMock()
        mock_tree_sitter.supported_languages = {"py"}
        mock_tree_sitter.chunk_file.return_value = [
            ChunkData(
                start_line=1, end_line=3, content="def add():\n  return 1",
                symbol="add", lang="py",
            )
        ]

        mock_line_chunker = MagicMock()

        use_case = ChunkFileUseCase(mock_tree_sitter, mock_line_chunker)
        request = ChunkFileRequest(
            content="def add():\n  return 1\n",
            path=Path("math.py"),
            lang="py",
        )

        response = use_case.execute(request)

        assert response.success is True
        assert response.strategy == "tree-sitter"
        assert response.parse_warnings == []

    def test_unsupported_language_no_warnings(self) -> None:
        """Unsupported languages fall back to line-based without warnings."""
        mock_tree_sitter = MagicMock()
        mock_tree_sitter.supported_languages = set()

        mock_line_chunker = MagicMock()
        mock_line_chunker.chunk_file.return_value = [
            ChunkData(
                start_line=1, end_line=3, content="data",
                symbol=None, lang="sql",
            )
        ]

        use_case = ChunkFileUseCase(mock_tree_sitter, mock_line_chunker)
        request = ChunkFileRequest(
            content="SELECT * FROM users;",
            path=Path("query.sql"),
            lang="sql",
        )

        response = use_case.execute(request)

        assert response.success is True
        assert response.strategy == "line-based"
        assert response.parse_warnings == []

    def test_tree_sitter_no_definitions_no_warning(self) -> None:
        """When tree-sitter returns empty list (no definitions), no warning is generated.

        This is the normal case for files with only statements (no functions/classes).
        """
        mock_tree_sitter = MagicMock()
        mock_tree_sitter.supported_languages = {"py"}
        mock_tree_sitter.chunk_file.return_value = []  # No definitions found

        mock_line_chunker = MagicMock()
        mock_line_chunker.chunk_file.return_value = [
            ChunkData(
                start_line=1, end_line=3, content="x = 42",
                symbol=None, lang="py",
            )
        ]

        use_case = ChunkFileUseCase(mock_tree_sitter, mock_line_chunker)
        request = ChunkFileRequest(
            content="x = 42\ny = x + 1\n",
            path=Path("script.py"),
            lang="py",
        )

        response = use_case.execute(request)

        assert response.success is True
        assert response.strategy == "line-based"
        # No warning: tree-sitter didn't fail, it just found no definitions
        assert response.parse_warnings == []


class TestTreeSitterChunkerParseError:
    """Tests for TreeSitterChunker raising ParseError on parse failure."""

    def test_parse_failure_raises_parse_error(self) -> None:
        """Tree-sitter chunker raises ParseError when parsing fails."""
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
        from ember.ports.chunkers import ParseError

        chunker = TreeSitterChunker()

        # Patch the parser to raise an exception during parse
        with patch.object(chunker, "_registry") as mock_registry:
            mock_config = MagicMock()
            mock_config.name = "python"
            mock_registry.get_by_identifier.return_value = mock_config

            mock_parser = MagicMock()
            mock_parser.parse.side_effect = RuntimeError("segfault in tree-sitter")
            mock_registry.get_parser.return_value = mock_parser
            mock_registry.get_query.return_value = MagicMock()

            with pytest.raises(ParseError) as exc_info:
                chunker.chunk_file("broken content", Path("test.py"), "py")

            assert "test.py" in str(exc_info.value)
            assert "python" in str(exc_info.value)

    def test_unicode_encode_failure_raises_parse_error(self) -> None:
        """Tree-sitter chunker raises ParseError on UTF-8 encoding failure."""
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
        from ember.ports.chunkers import ParseError

        chunker = TreeSitterChunker()

        with patch.object(chunker, "_registry") as mock_registry:
            mock_config = MagicMock()
            mock_config.name = "python"
            mock_registry.get_by_identifier.return_value = mock_config

            mock_parser = MagicMock()
            mock_parser.parse.side_effect = UnicodeEncodeError(
                "utf-8", "", 0, 1, "invalid"
            )
            mock_registry.get_parser.return_value = mock_parser
            mock_registry.get_query.return_value = MagicMock()

            with pytest.raises(ParseError) as exc_info:
                chunker.chunk_file("content", Path("test.py"), "py")

            assert "test.py" in str(exc_info.value)

    def test_query_execution_failure_raises_parse_error(self) -> None:
        """Tree-sitter chunker raises ParseError when query execution fails."""
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
        from ember.ports.chunkers import ParseError

        chunker = TreeSitterChunker()

        with patch.object(chunker, "_registry") as mock_registry:
            mock_config = MagicMock()
            mock_config.name = "python"
            mock_registry.get_by_identifier.return_value = mock_config

            mock_parser = MagicMock()
            mock_registry.get_parser.return_value = mock_parser
            mock_registry.get_query.return_value = MagicMock()

            # Make QueryCursor raise
            with patch(
                "ember.adapters.parsers.tree_sitter_chunker.QueryCursor",
                side_effect=RuntimeError("query failed"),
            ):
                with pytest.raises(ParseError) as exc_info:
                    chunker.chunk_file("def foo(): pass", Path("test.py"), "py")

                assert "test.py" in str(exc_info.value)

    def test_parser_init_failure_raises_parse_error(self) -> None:
        """Tree-sitter chunker raises ParseError when parser init fails."""
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
        from ember.ports.chunkers import ParseError

        chunker = TreeSitterChunker()

        with patch.object(chunker, "_registry") as mock_registry:
            mock_config = MagicMock()
            mock_config.name = "python"
            mock_registry.get_by_identifier.return_value = mock_config
            mock_registry.get_parser.return_value = None  # Parser init failed
            mock_registry.get_query.return_value = MagicMock()

            with pytest.raises(ParseError) as exc_info:
                chunker.chunk_file("content", Path("test.py"), "py")

            assert "test.py" in str(exc_info.value)

    def test_unsupported_language_returns_empty_no_error(self) -> None:
        """Unsupported language still returns empty list (not an error)."""
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker

        chunker = TreeSitterChunker()
        result = chunker.chunk_file("SELECT 1;", Path("q.sql"), "sql")
        assert result == []

    def test_successful_parse_returns_chunks(self) -> None:
        """Successful parse returns chunks as before (no behavioral change)."""
        from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker

        chunker = TreeSitterChunker()
        content = "def add(a, b):\n    return a + b\n"
        chunks = chunker.chunk_file(content, Path("math.py"), "py")
        assert len(chunks) == 1
        assert chunks[0].symbol == "add"


class TestIndexResponseParseWarnings:
    """Tests for parse warnings in IndexResponse."""

    def test_index_response_has_parse_warnings(self) -> None:
        """IndexResponse includes parse_warnings field."""
        from ember.core.indexing.types import IndexResponse

        warnings = [
            ParseWarning(path=Path("a.py"), language="py", reason="parse failed"),
            ParseWarning(path=Path("b.ts"), language="ts", reason="syntax error"),
        ]
        response = IndexResponse.create_success(
            files_indexed=10,
            chunks_created=20,
            chunks_updated=0,
            chunks_deleted=0,
            vectors_stored=20,
            tree_sha="abc123",
            parse_warnings=warnings,
        )
        assert len(response.parse_warnings) == 2
        assert response.parse_warnings[0].path == Path("a.py")

    def test_index_response_default_empty_warnings(self) -> None:
        """IndexResponse defaults to empty parse_warnings."""
        from ember.core.indexing.types import IndexResponse

        response = IndexResponse.create_success(
            files_indexed=5,
            chunks_created=10,
            chunks_updated=0,
            chunks_deleted=0,
            vectors_stored=10,
            tree_sha="abc123",
        )
        assert response.parse_warnings == []

    def test_error_response_has_empty_warnings(self) -> None:
        """Error response has empty parse_warnings."""
        from ember.core.indexing.types import IndexResponse

        response = IndexResponse.create_error("something broke")
        assert response.parse_warnings == []


class TestSyncOutputParseFailures:
    """Tests for parse failure display in sync output."""

    def test_format_sync_results_shows_parse_failures(self) -> None:
        """Sync output shows parse failure count when there are parse warnings."""
        from ember.entrypoints.cli import _format_sync_results

        warnings = [
            ParseWarning(path=Path("a.py"), language="py", reason="parse failed"),
            ParseWarning(path=Path("b.py"), language="py", reason="parse failed"),
            ParseWarning(path=Path("c.ts"), language="ts", reason="parse failed"),
        ]

        response = MagicMock()
        response.files_indexed = 10
        response.chunks_created = 20
        response.chunks_updated = 0
        response.chunks_deleted = 0
        response.vectors_stored = 20
        response.files_failed = 0
        response.is_incremental = False
        response.tree_sha = "abc123def456"
        response.parse_warnings = warnings

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            # Should show parse failure count
            assert any("3" in c and "parse" in c.lower() for c in calls)

    def test_format_sync_results_no_failures_no_message(self) -> None:
        """Sync output does not show parse failure line when count is 0."""
        from ember.entrypoints.cli import _format_sync_results

        response = MagicMock()
        response.files_indexed = 5
        response.chunks_created = 10
        response.chunks_updated = 0
        response.chunks_deleted = 0
        response.vectors_stored = 10
        response.files_failed = 0
        response.is_incremental = False
        response.tree_sha = "abc123def456"
        response.parse_warnings = []

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            # Should NOT show parse failure line
            assert not any("parse" in c.lower() for c in calls)

    def test_format_sync_results_verbose_lists_files(self) -> None:
        """With verbose=True, sync output lists specific files that failed to parse."""
        from ember.entrypoints.cli import _format_sync_results

        warnings = [
            ParseWarning(path=Path("src/broken.py"), language="py", reason="parse failed"),
            ParseWarning(path=Path("lib/bad.ts"), language="ts", reason="syntax error"),
        ]

        response = MagicMock()
        response.files_indexed = 10
        response.chunks_created = 20
        response.chunks_updated = 0
        response.chunks_deleted = 0
        response.vectors_stored = 20
        response.files_failed = 2
        response.is_incremental = False
        response.tree_sha = "abc123def456"
        response.parse_warnings = warnings

        with patch("click.echo") as mock_echo:
            _format_sync_results(response, verbose=True)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            all_output = "\n".join(calls)
            # Should list the specific files
            assert "src/broken.py" in all_output
            assert "lib/bad.ts" in all_output

    def test_format_sync_results_non_verbose_no_file_list(self) -> None:
        """Without verbose, sync output shows count but not individual files."""
        from ember.entrypoints.cli import _format_sync_results

        warnings = [
            ParseWarning(path=Path("src/broken.py"), language="py", reason="parse failed"),
        ]

        response = MagicMock()
        response.files_indexed = 10
        response.chunks_created = 20
        response.chunks_updated = 0
        response.chunks_deleted = 0
        response.vectors_stored = 20
        response.files_failed = 0
        response.is_incremental = False
        response.tree_sha = "abc123def456"
        response.parse_warnings = warnings

        with patch("click.echo") as mock_echo:
            _format_sync_results(response, verbose=False)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            all_output = "\n".join(calls)
            # Should NOT list specific files in non-verbose mode
            # But should mention the count and suggest --verbose
            assert "src/broken.py" not in all_output
            assert "--verbose" in all_output


class TestParseErrorException:
    """Tests for the ParseError exception class."""

    def test_parse_error_is_exception(self) -> None:
        """ParseError is a proper exception."""
        from ember.ports.chunkers import ParseError

        error = ParseError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_parse_error_not_caught_by_generic_ember_error(self) -> None:
        """ParseError is not an EmberError - it's caught specifically by chunk use case."""
        from ember.core.use_case_errors import EmberError
        from ember.ports.chunkers import ParseError

        error = ParseError("test")
        assert not isinstance(error, EmberError)
