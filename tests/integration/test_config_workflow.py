"""Integration tests for config workflow.

Tests that config is created during init and used during sync/find.
"""

import tempfile
from pathlib import Path

from ember.adapters.config.toml_config_provider import TomlConfigProvider
from ember.adapters.sqlite.initializer import SqliteDatabaseInitializer
from ember.core.config.init_usecase import InitRequest, InitUseCase
from ember.shared.config_io import load_config


def test_init_creates_valid_config():
    """Test that init creates a valid config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "test_repo"
        repo_root.mkdir()

        # Initialize ember
        db_initializer = SqliteDatabaseInitializer()
        use_case = InitUseCase(db_initializer=db_initializer, version="0.1.0")
        request = InitRequest(repo_root=repo_root, force=False)
        response = use_case.execute(request)

        # Verify config file was created
        assert response.config_path.exists()

        # Verify config can be loaded
        config = load_config(response.config_path)
        assert config.search.topk == 20
        assert config.index.line_window == 120


def test_config_provider_loads_init_config():
    """Test that config provider can load config created by init."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "test_repo"
        repo_root.mkdir()

        # Initialize ember
        db_initializer = SqliteDatabaseInitializer()
        use_case = InitUseCase(db_initializer=db_initializer, version="0.1.0")
        request = InitRequest(repo_root=repo_root, force=False)
        response = use_case.execute(request)

        # Load config using provider
        provider = TomlConfigProvider()
        config = provider.load(response.ember_dir)

        # Verify defaults
        assert config.search.topk == 20
        assert config.index.line_window == 120
        assert config.index.chunk == "symbol"


def test_modified_config_is_loaded():
    """Test that modified config values are properly loaded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "test_repo"
        repo_root.mkdir()

        # Initialize ember
        db_initializer = SqliteDatabaseInitializer()
        use_case = InitUseCase(db_initializer=db_initializer, version="0.1.0")
        request = InitRequest(repo_root=repo_root, force=False)
        response = use_case.execute(request)

        # Modify the config file
        config_path = response.config_path
        with open(config_path, "a") as f:
            # Append custom settings at the end
            f.write("\n# Custom settings\n")
            # Note: Can't override in append mode, so we'll test with a fresh config

        # Actually, let's rewrite with custom values
        config_path.write_text("""
[search]
topk = 50

[index]
line_window = 200
line_stride = 150
chunk = "lines"

[redaction]
max_file_mb = 10
""")

        # Load config using provider
        provider = TomlConfigProvider()
        config = provider.load(response.ember_dir)

        # Verify custom values
        assert config.search.topk == 50
        assert config.index.line_window == 200
        assert config.index.line_stride == 150
        assert config.index.chunk == "lines"
        assert config.redaction.max_file_mb == 10
