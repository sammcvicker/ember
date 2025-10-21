"""Integration tests for init command and use case.

Tests the complete init flow including database schema creation,
config file generation, and state initialization.
"""

import sqlite3
from pathlib import Path

import pytest

from ember.core.config.init_usecase import InitRequest, InitUseCase
from ember.shared.config_io import load_config
from ember.shared.state_io import load_state


def test_init_creates_all_files(tmp_path: Path) -> None:
    """Test that init creates all required files and directories."""
    # Execute init
    use_case = InitUseCase(version="0.1.0")
    request = InitRequest(repo_root=tmp_path, force=False)
    response = use_case.execute(request)

    # Verify directory structure
    assert response.ember_dir.exists()
    assert response.ember_dir.is_dir()
    assert response.ember_dir == tmp_path / ".ember"

    # Verify all files exist
    assert response.config_path.exists()
    assert response.db_path.exists()
    assert response.state_path.exists()

    # Verify was_reinitialized is False for new init
    assert not response.was_reinitialized


def test_init_config_is_valid_toml(tmp_path: Path) -> None:
    """Test that created config.toml is valid and loadable."""
    use_case = InitUseCase(version="0.1.0")
    request = InitRequest(repo_root=tmp_path)
    response = use_case.execute(request)

    # Load and verify config
    config = load_config(response.config_path)

    # Check index section
    assert config.index.model == "local-default-code-embed"
    assert config.index.chunk == "symbol"
    assert config.index.line_window == 120
    assert "**/*.py" in config.index.include
    assert ".git/" in config.index.ignore

    # Check search section
    assert config.search.topk == 20
    assert config.search.rerank is False

    # Check redaction section
    assert len(config.redaction.patterns) > 0
    assert config.redaction.max_file_mb == 5


def test_init_creates_valid_database_schema(tmp_path: Path) -> None:
    """Test that SQLite database has correct schema."""
    use_case = InitUseCase(version="0.1.0")
    request = InitRequest(repo_root=tmp_path)
    response = use_case.execute(request)

    # Connect to database and check schema
    conn = sqlite3.connect(response.db_path)
    cursor = conn.cursor()

    # Check all required tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}

    required_tables = {"chunks", "chunk_text", "vectors", "meta", "tags", "files"}
    assert required_tables.issubset(tables)

    # Check chunks table schema
    cursor.execute("PRAGMA table_info(chunks)")
    chunk_columns = {row[1] for row in cursor.fetchall()}
    assert "id" in chunk_columns
    assert "path" in chunk_columns
    assert "content" in chunk_columns
    assert "content_hash" in chunk_columns
    assert "tree_sha" in chunk_columns

    # Check meta table has schema_version
    cursor.execute("SELECT key, value FROM meta WHERE key = 'schema_version'")
    row = cursor.fetchone()
    assert row is not None
    assert int(row[1]) >= 1

    conn.close()


def test_init_creates_valid_state_json(tmp_path: Path) -> None:
    """Test that state.json is created with correct initial values."""
    use_case = InitUseCase(version="0.1.0")
    request = InitRequest(repo_root=tmp_path)
    response = use_case.execute(request)

    # Load and verify state
    state = load_state(response.state_path)

    assert state.last_tree_sha == ""
    assert state.last_sync_mode == "none"
    assert state.model_fingerprint == ""
    assert state.version == "0.1.0"
    assert state.indexed_at  # Should have a timestamp


def test_init_fails_if_ember_dir_exists(tmp_path: Path) -> None:
    """Test that init fails if .ember/ already exists without --force."""
    # First init
    use_case = InitUseCase(version="0.1.0")
    request = InitRequest(repo_root=tmp_path, force=False)
    use_case.execute(request)

    # Second init without force should fail
    with pytest.raises(FileExistsError, match="already exists"):
        use_case.execute(request)


def test_init_force_reinitializes(tmp_path: Path) -> None:
    """Test that init --force reinitializes existing .ember/ directory."""
    use_case = InitUseCase(version="0.1.0")

    # First init
    request1 = InitRequest(repo_root=tmp_path, force=False)
    response1 = use_case.execute(request1)
    assert not response1.was_reinitialized

    # Modify config to verify it gets replaced
    config_path = response1.config_path
    original_content = config_path.read_text()
    config_path.write_text("# Modified")

    # Second init with force
    request2 = InitRequest(repo_root=tmp_path, force=True)
    response2 = use_case.execute(request2)
    assert response2.was_reinitialized

    # Verify config was replaced
    new_content = config_path.read_text()
    assert new_content == original_content
    assert "# Modified" not in new_content


def test_init_database_has_fts5_triggers(tmp_path: Path) -> None:
    """Test that FTS5 triggers are created for automatic indexing."""
    use_case = InitUseCase(version="0.1.0")
    request = InitRequest(repo_root=tmp_path)
    response = use_case.execute(request)

    conn = sqlite3.connect(response.db_path)
    cursor = conn.cursor()

    # Check triggers exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")
    triggers = {row[0] for row in cursor.fetchall()}

    assert "chunks_ai" in triggers  # After insert
    assert "chunks_ad" in triggers  # After delete
    assert "chunks_au" in triggers  # After update

    conn.close()
