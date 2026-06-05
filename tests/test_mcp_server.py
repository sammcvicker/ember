"""Tests for the Ember MCP server entrypoint.

Tests the MCP tool functions in isolation by mocking the underlying
use cases and repositories.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We test the tool functions directly, not through the MCP protocol
from ember.entrypoints.mcp_server import (
    _get_repo_context,
    _result_to_dict,
    ember_cat,
    ember_search,
    ember_status,
)


class TestResultToDict:
    """Tests for _result_to_dict helper."""

    def test_converts_search_result_to_dict(self):
        """Result dict includes all expected fields."""
        mock_chunk = MagicMock()
        mock_chunk.path = Path("src/auth/login.py")
        mock_chunk.symbol = "authenticate_user"
        mock_chunk.lang = "py"
        mock_chunk.start_line = 15
        mock_chunk.end_line = 42
        mock_chunk.content = "def authenticate_user(): pass"
        mock_chunk.id = "abc123"

        mock_result = MagicMock()
        mock_result.rank = 1
        mock_result.score = 0.8247123456
        mock_result.chunk = mock_chunk

        result = _result_to_dict(mock_result)

        assert result["rank"] == 1
        assert result["score"] == 0.824712
        assert result["path"] == "src/auth/login.py"
        assert result["symbol"] == "authenticate_user"
        assert result["lang"] == "py"
        assert result["start_line"] == 15
        assert result["end_line"] == 42
        assert result["content"] == "def authenticate_user(): pass"
        assert result["chunk_id"] == "abc123"

    def test_handles_none_symbol(self):
        """Line chunks may have None symbol."""
        mock_chunk = MagicMock()
        mock_chunk.path = Path("data.txt")
        mock_chunk.symbol = None
        mock_chunk.lang = "text"
        mock_chunk.start_line = 1
        mock_chunk.end_line = 10
        mock_chunk.content = "some content"
        mock_chunk.id = "def456"

        mock_result = MagicMock()
        mock_result.rank = 2
        mock_result.score = 0.5
        mock_result.chunk = mock_chunk

        result = _result_to_dict(mock_result)
        assert result["symbol"] is None


class TestGetRepoContext:
    """Tests for _get_repo_context helper."""

    @patch("ember.core.repo_utils.find_repo_root")
    def test_returns_repo_root_and_paths(self, mock_find):
        """Returns tuple of (repo_root, ember_dir, db_path)."""
        repo_root = Path("/tmp/test-repo")
        ember_dir = Path("/tmp/test-repo/.ember")
        mock_find.return_value = (repo_root, ember_dir)

        root, edir, db = _get_repo_context()

        assert root == repo_root
        assert edir == ember_dir
        assert db == ember_dir / "index.db"

    @patch("ember.core.repo_utils.find_repo_root")
    def test_raises_when_not_in_repo(self, mock_find):
        """Raises RuntimeError when not in an ember repository."""
        mock_find.side_effect = RuntimeError("Not an ember repository")

        with pytest.raises(RuntimeError, match="Not an ember repository"):
            _get_repo_context()


class TestEmberSearch:
    """Tests for ember_search MCP tool."""

    @patch("ember.entrypoints.mcp_server._create_search_deps")
    @patch("ember.entrypoints.mcp_server._load_config")
    @patch("ember.entrypoints.mcp_server._get_repo_context")
    @patch("ember.entrypoints.cli.ensure_synced")
    def test_returns_json_results(
        self, mock_sync, mock_ctx, mock_config, mock_deps
    ):
        """Search returns JSON array of results."""
        import json

        repo_root = Path("/tmp/test-repo")
        ember_dir = Path("/tmp/test-repo/.ember")
        db_path = ember_dir / "index.db"
        mock_ctx.return_value = (repo_root, ember_dir, db_path)
        mock_config.return_value = MagicMock()

        # Mock search results
        mock_chunk = MagicMock()
        mock_chunk.path = Path("src/main.py")
        mock_chunk.symbol = "main"
        mock_chunk.lang = "py"
        mock_chunk.start_line = 1
        mock_chunk.end_line = 10
        mock_chunk.content = "def main(): pass"
        mock_chunk.id = "hash123"

        mock_result = MagicMock()
        mock_result.rank = 1
        mock_result.score = 0.9
        mock_result.chunk = mock_chunk

        mock_usecase = MagicMock()
        mock_usecase.search.return_value = [mock_result]
        mock_deps.return_value = mock_usecase

        result = ember_search("main function")
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0]["path"] == "src/main.py"
        assert parsed[0]["symbol"] == "main"

    @patch("ember.entrypoints.mcp_server._create_search_deps")
    @patch("ember.entrypoints.mcp_server._load_config")
    @patch("ember.entrypoints.mcp_server._get_repo_context")
    @patch("ember.entrypoints.cli.ensure_synced")
    def test_calls_ensure_synced(
        self, mock_sync, mock_ctx, mock_config, mock_deps
    ):
        """Search calls ensure_synced before executing."""
        repo_root = Path("/tmp/test-repo")
        ember_dir = Path("/tmp/test-repo/.ember")
        db_path = ember_dir / "index.db"
        mock_ctx.return_value = (repo_root, ember_dir, db_path)
        mock_config.return_value = MagicMock()
        mock_deps.return_value = MagicMock(search=MagicMock(return_value=[]))

        ember_search("test query")

        mock_sync.assert_called_once_with(
            repo_root=repo_root,
            db_path=db_path,
            config=mock_config.return_value,
            show_progress=False,
            verbose=False,
        )

    @patch("ember.entrypoints.mcp_server._create_search_deps")
    @patch("ember.entrypoints.mcp_server._load_config")
    @patch("ember.entrypoints.mcp_server._get_repo_context")
    @patch("ember.entrypoints.cli.ensure_synced")
    def test_passes_filters_to_query(
        self, mock_sync, mock_ctx, mock_config, mock_deps
    ):
        """Filters are passed through to Query object."""
        mock_ctx.return_value = (
            Path("/tmp/repo"),
            Path("/tmp/repo/.ember"),
            Path("/tmp/repo/.ember/index.db"),
        )
        mock_config.return_value = MagicMock()
        mock_usecase = MagicMock(search=MagicMock(return_value=[]))
        mock_deps.return_value = mock_usecase

        ember_search("test", topk=5, path_filter="*.py", lang_filter="py")

        call_args = mock_usecase.search.call_args[0][0]
        assert call_args.text == "test"
        assert call_args.topk == 5
        assert call_args.path_filter == "*.py"
        assert call_args.lang_filter == "py"

    @patch("ember.entrypoints.mcp_server._create_search_deps")
    @patch("ember.entrypoints.mcp_server._load_config")
    @patch("ember.entrypoints.mcp_server._get_repo_context")
    @patch("ember.entrypoints.cli.ensure_synced")
    def test_empty_results(
        self, mock_sync, mock_ctx, mock_config, mock_deps
    ):
        """Returns empty JSON array when no results."""
        import json

        mock_ctx.return_value = (
            Path("/tmp/repo"),
            Path("/tmp/repo/.ember"),
            Path("/tmp/repo/.ember/index.db"),
        )
        mock_config.return_value = MagicMock()
        mock_deps.return_value = MagicMock(search=MagicMock(return_value=[]))

        result = ember_search("nonexistent")
        parsed = json.loads(result)
        assert parsed == []


class TestEmberStatus:
    """Tests for ember_status MCP tool."""

    @patch("ember.adapters.sqlite.meta_repository.SQLiteMetaRepository")
    @patch("ember.adapters.sqlite.chunk_repository.SQLiteChunkRepository")
    @patch("ember.adapters.git_cmd.git_adapter.GitAdapter")
    @patch("ember.core.status.status_usecase.StatusUseCase")
    @patch("ember.entrypoints.mcp_server._load_config")
    @patch("ember.entrypoints.mcp_server._get_repo_context")
    def test_returns_status_json(
        self, mock_ctx, mock_config, mock_usecase_cls,
        mock_git, mock_chunk, mock_meta
    ):
        """Status returns JSON with expected fields."""
        import json

        repo_root = Path("/tmp/test-repo")
        ember_dir = Path("/tmp/test-repo/.ember")
        db_path = ember_dir / "index.db"
        mock_ctx.return_value = (repo_root, ember_dir, db_path)

        mock_cfg = MagicMock()
        mock_cfg.index.model = "jina-code-v2"
        mock_cfg.index.chunk = "symbol"
        mock_cfg.search.topk = 20
        mock_config.return_value = mock_cfg

        mock_response = MagicMock()
        mock_response.initialized = True
        mock_response.repo_root = repo_root
        mock_response.indexed_files = 42
        mock_response.total_chunks = 300
        mock_response.is_stale = False
        mock_response.last_tree_sha = "abc123"
        mock_response.success = True
        mock_response.error = None
        mock_response.config = mock_cfg
        mock_response.model_fingerprint = "jina-code-v2:768"

        mock_usecase = MagicMock()
        mock_usecase.execute.return_value = mock_response
        mock_usecase_cls.return_value = mock_usecase

        result = ember_status()
        parsed = json.loads(result)

        assert parsed["initialized"] is True
        assert parsed["indexed_files"] == 42
        assert parsed["total_chunks"] == 300
        assert parsed["is_stale"] is False
        assert parsed["success"] is True
        assert parsed["config"]["model"] == "jina-code-v2"
        assert parsed["model_fingerprint"] == "jina-code-v2:768"


class TestEmberCat:
    """Tests for ember_cat MCP tool."""

    @patch("ember.core.cli_utils.lookup_result_from_cache")
    @patch("ember.entrypoints.mcp_server._get_repo_context")
    def test_numeric_index_lookup(self, mock_ctx, mock_lookup):
        """Numeric identifiers use cache lookup."""
        import json

        mock_ctx.return_value = (
            Path("/tmp/repo"),
            Path("/tmp/repo/.ember"),
            Path("/tmp/repo/.ember/index.db"),
        )
        mock_lookup.return_value = {
            "path": "src/main.py",
            "symbol": "main",
            "lang": "py",
            "start_line": 1,
            "end_line": 10,
            "content": "def main(): pass",
            "id": "hash123",
        }

        result = ember_cat("1")
        parsed = json.loads(result)

        assert parsed["path"] == "src/main.py"
        assert parsed["content"] == "def main(): pass"
        mock_lookup.assert_called_once()

    @patch("ember.core.cli_utils.lookup_result_by_hash")
    @patch("ember.adapters.sqlite.chunk_repository.SQLiteChunkRepository")
    @patch("ember.entrypoints.mcp_server._get_repo_context")
    def test_hash_lookup(self, mock_ctx, mock_repo, mock_lookup):
        """Non-numeric identifiers use hash lookup."""
        import json

        mock_ctx.return_value = (
            Path("/tmp/repo"),
            Path("/tmp/repo/.ember"),
            Path("/tmp/repo/.ember/index.db"),
        )
        mock_lookup.return_value = {
            "path": "src/utils.py",
            "symbol": "helper",
            "lang": "py",
            "start_line": 5,
            "end_line": 15,
            "content": "def helper(): pass",
            "chunk_id": "abcdef12",
        }

        result = ember_cat("abcdef12")
        parsed = json.loads(result)

        assert parsed["path"] == "src/utils.py"
        assert parsed["chunk_id"] == "abcdef12"
        mock_lookup.assert_called_once()


class TestMcpServerCreation:
    """Tests for MCP server object creation."""

    def test_mcp_server_has_name(self):
        """MCP server is named 'ember'."""
        from ember.entrypoints.mcp_server import mcp

        assert mcp.name == "ember"

    def test_mcp_server_has_instructions(self):
        """MCP server has usage instructions."""
        from ember.entrypoints.mcp_server import mcp

        assert mcp.instructions is not None
        assert "search" in mcp.instructions.lower()
