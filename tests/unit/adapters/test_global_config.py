"""Unit tests for global config fallback functionality."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ember.adapters.config.toml_config_provider import TomlConfigProvider
from ember.domain.config import EmberConfig
from ember.shared.config_io import get_global_config_path


class TestGetGlobalConfigPath:
    """Tests for global config path resolution."""

    def test_uses_xdg_config_home_when_set(self) -> None:
        """Test that XDG_CONFIG_HOME is respected on Unix-like systems."""
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}):
            result = get_global_config_path()

        assert result == Path("/custom/config/ember/config.toml")

    def test_defaults_to_home_config_when_xdg_not_set(self) -> None:
        """Test default ~/.config/ember when XDG_CONFIG_HOME not set."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("ember.shared.config_io.Path.home") as mock_home,
        ):
            mock_home.return_value = Path("/home/user")
            # Ensure XDG_CONFIG_HOME is not set
            os.environ.pop("XDG_CONFIG_HOME", None)
            result = get_global_config_path()

        assert result == Path("/home/user/.config/ember/config.toml")

    @patch("ember.shared.config_io.platform.system")
    def test_uses_appdata_on_windows(self, mock_system: object) -> None:
        """Test that %APPDATA%/ember is used on Windows."""
        mock_system.return_value = "Windows"  # type: ignore[attr-defined]
        with patch.dict(os.environ, {"APPDATA": "C:\\Users\\Test\\AppData\\Roaming"}):
            result = get_global_config_path()

        assert result == Path("C:\\Users\\Test\\AppData\\Roaming/ember/config.toml")


class TestGlobalConfigFallback:
    """Tests for global config fallback behavior."""

    @pytest.fixture
    def provider(self) -> TomlConfigProvider:
        """Create a TomlConfigProvider instance."""
        return TomlConfigProvider()

    def test_global_config_used_when_local_missing(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test that global config is used when local config is missing."""
        # Setup: local .ember dir exists but has no config.toml
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        # Setup: global config with custom settings
        global_config_dir = tmp_path / "global_config" / "ember"
        global_config_dir.mkdir(parents=True)
        global_config = global_config_dir / "config.toml"
        global_config.write_text(
            """
[search]
topk = 42

[display]
theme = "monokai"
"""
        )

        # Patch to use our temp global config path
        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Should use global config values
        assert result.search.topk == 42
        assert result.display.theme == "monokai"

    def test_local_config_overrides_global(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test that local config values override global config values."""
        # Setup: local config
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[search]
topk = 100
"""
        )

        # Setup: global config with different values
        global_config_dir = tmp_path / "global_config" / "ember"
        global_config_dir.mkdir(parents=True)
        global_config = global_config_dir / "config.toml"
        global_config.write_text(
            """
[search]
topk = 42
rerank = true

[display]
theme = "monokai"
"""
        )

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Local value should override global
        assert result.search.topk == 100
        # Global values not in local should be used
        assert result.search.rerank is True
        assert result.display.theme == "monokai"

    def test_defaults_used_when_both_configs_missing(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test that defaults are used when both configs are missing."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        # Global config doesn't exist
        global_config = tmp_path / "nonexistent" / "config.toml"

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Should return defaults
        default = EmberConfig.default()
        assert result.search.topk == default.search.topk
        assert result.index.model == default.index.model

    def test_partial_local_config_merges_with_global(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test that partial local config merges with global config."""
        # Setup: local config with only index section
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[index]
model = "jina-code-v2"
"""
        )

        # Setup: global config with search and display sections
        global_config_dir = tmp_path / "global_config" / "ember"
        global_config_dir.mkdir(parents=True)
        global_config = global_config_dir / "config.toml"
        global_config.write_text(
            """
[index]
model = "minilm"

[search]
topk = 50

[display]
theme = "github-dark"
syntax_highlighting = false
"""
        )

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Local index overrides global
        assert result.index.model == "jina-code-v2"
        # Global search used
        assert result.search.topk == 50
        # Global display used
        assert result.display.theme == "github-dark"
        assert result.display.syntax_highlighting is False

    def test_invalid_global_config_falls_back_to_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that invalid global config is ignored gracefully."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        # Setup: invalid global config
        global_config_dir = tmp_path / "global_config" / "ember"
        global_config_dir.mkdir(parents=True)
        global_config = global_config_dir / "config.toml"
        global_config.write_text("[invalid toml")

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Should return defaults
        default = EmberConfig.default()
        assert result == default
        # Should log warning about global config
        assert "Failed to parse global config" in caplog.text

    def test_array_fields_merge_correctly(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test that array fields from local completely replace global (no append)."""
        # Setup: local config with include patterns
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[index]
include = ["**/*.py"]
"""
        )

        # Setup: global config with different include patterns
        global_config_dir = tmp_path / "global_config" / "ember"
        global_config_dir.mkdir(parents=True)
        global_config = global_config_dir / "config.toml"
        global_config.write_text(
            """
[index]
include = ["**/*.rs", "**/*.go"]
ignore = [".git/", "target/"]
"""
        )

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Local include should completely replace global (not merge)
        assert result.index.include == ["**/*.py"]
        # Global ignore should be used (not in local)
        assert result.index.ignore == [".git/", "target/"]
