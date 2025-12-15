"""Tests for TOML config provider."""

import tempfile
from pathlib import Path

from ember.adapters.config.toml_config_provider import TomlConfigProvider
from ember.shared.config_io import create_default_config_file


def test_load_config_with_valid_file():
    """Test loading a valid config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ember_dir = Path(tmpdir) / ".ember"
        ember_dir.mkdir()

        # Create a default config file
        config_path = ember_dir / "config.toml"
        create_default_config_file(config_path)

        # Load it
        provider = TomlConfigProvider()
        config = provider.load(ember_dir)

        # Verify defaults are loaded
        assert config.search.topk == 20
        assert config.index.line_window == 120
        assert config.index.line_stride == 100
        assert config.redaction.max_file_mb == 5


def test_load_config_with_custom_values():
    """Test loading a config file with custom values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ember_dir = Path(tmpdir) / ".ember"
        ember_dir.mkdir()

        # Write a custom config
        config_path = ember_dir / "config.toml"
        config_path.write_text("""
[search]
topk = 50
rerank = true

[index]
line_window = 200
line_stride = 150
""")

        # Load it
        provider = TomlConfigProvider()
        config = provider.load(ember_dir)

        # Verify custom values
        assert config.search.topk == 50
        assert config.search.rerank is True
        assert config.index.line_window == 200
        assert config.index.line_stride == 150


def test_load_config_missing_file_returns_defaults():
    """Test that missing config file returns defaults without error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ember_dir = Path(tmpdir) / ".ember"
        ember_dir.mkdir()

        # No config file created
        provider = TomlConfigProvider()
        config = provider.load(ember_dir)

        # Should return default config
        assert config.search.topk == 20
        assert config.index.line_window == 120


def test_load_config_invalid_toml_returns_defaults():
    """Test that invalid TOML returns defaults without error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ember_dir = Path(tmpdir) / ".ember"
        ember_dir.mkdir()

        # Write invalid TOML
        config_path = ember_dir / "config.toml"
        config_path.write_text("this is [[ not valid toml")

        # Load it - should fall back to defaults
        provider = TomlConfigProvider()
        config = provider.load(ember_dir)

        # Should return default config (graceful fallback)
        assert config.search.topk == 20
        assert config.index.line_window == 120


def test_load_config_invalid_toml_logs_warning(caplog):
    """Test that invalid TOML logs a warning message."""
    import logging

    with tempfile.TemporaryDirectory() as tmpdir:
        ember_dir = Path(tmpdir) / ".ember"
        ember_dir.mkdir()

        # Write invalid TOML
        config_path = ember_dir / "config.toml"
        config_path.write_text("this is [[ not valid toml")

        # Load with logging captured
        with caplog.at_level(logging.WARNING):
            provider = TomlConfigProvider()
            provider.load(ember_dir)

        # Verify warning was logged
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert "config.toml" in caplog.text
        assert "Invalid TOML" in caplog.text


def test_load_config_missing_file_no_warning(caplog):
    """Test that missing config file does NOT log a warning."""
    import logging

    with tempfile.TemporaryDirectory() as tmpdir:
        ember_dir = Path(tmpdir) / ".ember"
        ember_dir.mkdir()

        # No config file created - this is expected behavior
        with caplog.at_level(logging.WARNING):
            provider = TomlConfigProvider()
            provider.load(ember_dir)

        # No warnings should be logged for missing file
        assert len(caplog.records) == 0


def test_load_config_partial_config():
    """Test loading a partial config (only some sections defined)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ember_dir = Path(tmpdir) / ".ember"
        ember_dir.mkdir()

        # Write partial config (only search section)
        config_path = ember_dir / "config.toml"
        config_path.write_text("""
[search]
topk = 100
""")

        # Load it
        provider = TomlConfigProvider()
        config = provider.load(ember_dir)

        # Custom value from config
        assert config.search.topk == 100
        # Defaults for missing sections
        assert config.index.line_window == 120
        assert config.redaction.max_file_mb == 5
