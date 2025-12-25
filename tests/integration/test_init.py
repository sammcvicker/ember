"""Integration tests for init command and use case.

Tests the complete init flow including database schema creation
and config file generation.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from ember.adapters.config.toml_config_provider import TomlConfigProvider
from ember.adapters.sqlite.initializer import SqliteDatabaseInitializer
from ember.core.config.init_usecase import InitRequest, InitUseCase
from ember.shared.config_io import load_config


@pytest.fixture
def db_initializer() -> SqliteDatabaseInitializer:
    """Provide a database initializer for tests."""
    return SqliteDatabaseInitializer()


def test_init_creates_all_files(tmp_path: Path, db_initializer: SqliteDatabaseInitializer) -> None:
    """Test that init creates all required files and directories."""
    # Use a temp global config path to avoid affecting real global config
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        # Execute init
        use_case = InitUseCase(db_initializer=db_initializer)
        request = InitRequest(repo_root=tmp_path, force=False)
        response = use_case.execute(request)

    # Verify directory structure
    assert response.ember_dir.exists()
    assert response.ember_dir.is_dir()
    assert response.ember_dir == tmp_path / ".ember"

    # Verify all files exist
    assert response.config_path.exists()
    assert response.db_path.exists()

    # Verify global config was created
    assert response.global_config_created
    assert response.global_config_path == temp_global_path
    assert temp_global_path.exists()

    # Verify was_reinitialized is False for new init
    assert not response.was_reinitialized


def test_init_config_is_valid_toml(tmp_path: Path, db_initializer: SqliteDatabaseInitializer) -> None:
    """Test that created config files are valid and loadable.

    Init now creates:
    - A minimal project config (.ember/config.toml)
    - A global config (~/.config/ember/config.toml) on first run
    """
    # Use a temp global config path to avoid affecting real global config
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        use_case = InitUseCase(db_initializer=db_initializer)
        request = InitRequest(repo_root=tmp_path)
        response = use_case.execute(request)

    # Verify global config was created
    assert response.global_config_created
    assert temp_global_path.exists()

    # Load and verify global config has all defaults
    global_config = load_config(temp_global_path)
    assert global_config.index.model == "local-default-code-embed"
    assert global_config.index.chunk == "symbol"
    assert global_config.index.line_window == 120
    assert "**/*.py" in global_config.index.include
    assert ".git/" in global_config.index.ignore
    assert global_config.search.topk == 20
    assert global_config.search.rerank is False

    # Load and verify project config is minimal (relies on defaults)
    # Use TomlConfigProvider to get merged config
    with patch(
        "ember.adapters.config.toml_config_provider.get_global_config_path",
        return_value=temp_global_path,
    ):
        provider = TomlConfigProvider()
        merged_config = provider.load(response.ember_dir)

    # Merged config should have all values from global config
    assert merged_config.index.model == "local-default-code-embed"
    assert merged_config.index.chunk == "symbol"
    assert merged_config.search.topk == 20


def test_init_creates_valid_database_schema(tmp_path: Path, db_initializer: SqliteDatabaseInitializer) -> None:
    """Test that SQLite database has correct schema."""
    # Use a temp global config path to avoid affecting real global config
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        use_case = InitUseCase(db_initializer=db_initializer)
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


def test_init_fails_if_ember_dir_exists(tmp_path: Path, db_initializer: SqliteDatabaseInitializer) -> None:
    """Test that init fails if .ember/ already exists without --force."""
    # Use a temp global config path to avoid affecting real global config
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        # First init
        use_case = InitUseCase(db_initializer=db_initializer)
        request = InitRequest(repo_root=tmp_path, force=False)
        response = use_case.execute(request)
        assert response.success

        # Second init without force should return error response
        response2 = use_case.execute(request)
        assert not response2.success
        assert response2.already_exists
        assert "already exists" in (response2.error or "")


def test_init_force_reinitializes(tmp_path: Path, db_initializer: SqliteDatabaseInitializer) -> None:
    """Test that init --force reinitializes existing .ember/ directory."""
    # Use a temp global config path to avoid affecting real global config
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        use_case = InitUseCase(db_initializer=db_initializer)

        # First init
        request1 = InitRequest(repo_root=tmp_path, force=False)
        response1 = use_case.execute(request1)
        assert not response1.was_reinitialized
        assert response1.global_config_created  # First run creates global config

        # Modify config to verify it gets replaced
        config_path = response1.config_path
        original_content = config_path.read_text()
        config_path.write_text("# Modified")

        # Second init with force
        request2 = InitRequest(repo_root=tmp_path, force=True)
        response2 = use_case.execute(request2)
        assert response2.was_reinitialized
        assert not response2.global_config_created  # Global config already exists

        # Verify config was replaced
        new_content = config_path.read_text()
        assert new_content == original_content
        assert "# Modified" not in new_content


def test_init_database_has_fts5_triggers(tmp_path: Path, db_initializer: SqliteDatabaseInitializer) -> None:
    """Test that FTS5 triggers are created for automatic indexing."""
    # Use a temp global config path to avoid affecting real global config
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        use_case = InitUseCase(db_initializer=db_initializer)
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


def test_init_with_custom_model(tmp_path: Path, db_initializer: SqliteDatabaseInitializer) -> None:
    """Test that init with custom model sets it in global config."""
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        use_case = InitUseCase(db_initializer=db_initializer)
        request = InitRequest(repo_root=tmp_path, model="jina-code-v2")
        response = use_case.execute(request)

    # Global config should have the custom model
    global_config = load_config(temp_global_path)
    assert global_config.index.model == "jina-code-v2"

    # Project config should be minimal (no model set)
    project_content = response.config_path.read_text()
    assert "model =" not in project_content or project_content.count("# model") > 0


def test_init_respects_existing_global_config(
    tmp_path: Path, db_initializer: SqliteDatabaseInitializer
) -> None:
    """Test that init doesn't overwrite existing global config."""
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    # Create existing global config
    temp_global_path.parent.mkdir(parents=True)
    temp_global_path.write_text('[index]\nmodel = "minilm"\n')

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        use_case = InitUseCase(db_initializer=db_initializer)
        request = InitRequest(repo_root=tmp_path, model="jina-code-v2")
        response = use_case.execute(request)

    # Global config should NOT be overwritten
    assert not response.global_config_created
    global_config = load_config(temp_global_path)
    assert global_config.index.model == "minilm"  # Original value preserved


def test_project_config_overrides_global(
    tmp_path: Path, db_initializer: SqliteDatabaseInitializer
) -> None:
    """Test that project config overrides global config values."""
    temp_global_path = tmp_path / "global_config" / "ember" / "config.toml"

    with patch(
        "ember.core.config.init_usecase.get_global_config_path",
        return_value=temp_global_path,
    ):
        use_case = InitUseCase(db_initializer=db_initializer)
        request = InitRequest(repo_root=tmp_path, model="jina-code-v2")
        response = use_case.execute(request)

    # Now add a project-specific override
    project_config = response.config_path
    project_config.write_text('[index]\nmodel = "bge-small"\n')

    # Load merged config
    with patch(
        "ember.adapters.config.toml_config_provider.get_global_config_path",
        return_value=temp_global_path,
    ):
        provider = TomlConfigProvider()
        merged_config = provider.load(response.ember_dir)

    # Project config should override global
    assert merged_config.index.model == "bge-small"
