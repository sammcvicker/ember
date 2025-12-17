"""Unit tests for TomlConfigProvider adapter."""

from pathlib import Path
from unittest.mock import patch

import pytest

from ember.adapters.config.toml_config_provider import TomlConfigProvider
from ember.domain.config import EmberConfig


@pytest.fixture
def provider() -> TomlConfigProvider:
    """Create a TomlConfigProvider instance."""
    return TomlConfigProvider()


@pytest.fixture
def no_global_config(tmp_path: Path):
    """Mock global config path to ensure test isolation from user's actual config.

    Tests that assert default values must use this fixture to avoid reading
    the user's ~/.config/ember/config.toml which could override defaults.
    """
    nonexistent_global = tmp_path / "nonexistent_global" / "config.toml"
    with patch(
        "ember.adapters.config.toml_config_provider.get_global_config_path",
        return_value=nonexistent_global,
    ):
        yield nonexistent_global



class TestLoadValidConfig:
    """Tests for loading valid configurations."""

    def test_load_valid_config_returns_ember_config(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test that loading a valid config returns EmberConfig instance."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[search]
topk = 50
"""
        )

        result = provider.load(ember_dir)

        assert isinstance(result, EmberConfig)
        assert result.search.topk == 50

    def test_load_config_with_all_sections(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test loading a config with all sections specified."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[index]
model = "minilm"
chunk = "lines"
line_window = 200
line_stride = 150
overlap_lines = 20
include = ["**/*.rs"]
ignore = [".git/"]

[search]
topk = 100
rerank = true
filters = ["lang=python"]

[redaction]
patterns = ["secret"]
max_file_mb = 10

[model]
mode = "direct"
daemon_timeout = 1800
daemon_startup_timeout = 10

[display]
syntax_highlighting = false
color_scheme = "never"
theme = "monokai"
"""
        )

        result = provider.load(ember_dir)

        # Verify index section
        assert result.index.model == "minilm"
        assert result.index.chunk == "lines"
        assert result.index.line_window == 200
        assert result.index.line_stride == 150
        assert result.index.overlap_lines == 20
        assert result.index.include == ["**/*.rs"]
        assert result.index.ignore == [".git/"]

        # Verify search section
        assert result.search.topk == 100
        assert result.search.rerank is True
        assert result.search.filters == ["lang=python"]

        # Verify redaction section
        assert result.redaction.patterns == ["secret"]
        assert result.redaction.max_file_mb == 10

        # Verify model section
        assert result.model.mode == "direct"
        assert result.model.daemon_timeout == 1800
        assert result.model.daemon_startup_timeout == 10

        # Verify display section
        assert result.display.syntax_highlighting is False
        assert result.display.color_scheme == "never"
        assert result.display.theme == "monokai"


class TestLoadMissingConfig:
    """Tests for loading when config file is missing."""

    def test_load_missing_file_returns_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path, no_global_config: Path
    ) -> None:
        """Test that missing config file returns default configuration.

        Uses no_global_config fixture to isolate from user's actual global config.
        """
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        # config.toml does NOT exist

        result = provider.load(ember_dir)

        # Should return defaults
        assert isinstance(result, EmberConfig)
        default = EmberConfig.default()
        assert result.search.topk == default.search.topk
        assert result.index.model == default.index.model
        assert result.model.mode == default.model.mode

    def test_load_missing_directory_returns_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path, no_global_config: Path
    ) -> None:
        """Test that missing ember directory returns default configuration.

        Uses no_global_config fixture to isolate from user's actual global config.
        """
        ember_dir = tmp_path / ".ember"
        # Directory does NOT exist

        result = provider.load(ember_dir)

        # Should return defaults
        assert isinstance(result, EmberConfig)
        default = EmberConfig.default()
        assert result == default


class TestLoadInvalidConfig:
    """Tests for handling invalid configurations."""

    def test_load_invalid_toml_returns_defaults(
        self,
        provider: TomlConfigProvider,
        tmp_path: Path,
        no_global_config: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that invalid TOML syntax returns defaults with warning.

        Uses no_global_config fixture to isolate from user's actual global config.
        """
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[index
model = "broken"
"""
        )

        result = provider.load(ember_dir)

        # Should return defaults
        assert isinstance(result, EmberConfig)
        default = EmberConfig.default()
        assert result.index.model == default.index.model

        # Should log warning
        assert "Failed to parse config.toml" in caplog.text

    def test_load_config_with_unknown_keys_ignores_them(
        self,
        provider: TomlConfigProvider,
        tmp_path: Path,
        no_global_config: Path,
    ) -> None:
        """Test that unknown keys in config are gracefully ignored.

        Uses no_global_config fixture to isolate from user's actual global config.
        Unknown keys are simply ignored rather than causing errors - this allows
        configs to be forward-compatible with future versions.
        """
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[search]
topk = 42
unknown_future_key = "ignored"
"""
        )

        result = provider.load(ember_dir)

        # Should use the valid values, ignoring unknown keys
        assert result.search.topk == 42
        # Other sections should have defaults
        default = EmberConfig.default()
        assert result.index.model == default.index.model


class TestPartialConfig:
    """Tests for partial configurations (missing sections)."""

    def test_load_partial_config_uses_defaults_for_missing(
        self, provider: TomlConfigProvider, tmp_path: Path, no_global_config: Path
    ) -> None:
        """Test that partial config fills in missing sections with defaults.

        Uses no_global_config fixture to isolate from user's actual global config.
        """
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[search]
topk = 999
"""
        )

        result = provider.load(ember_dir)

        # Specified values should be used
        assert result.search.topk == 999

        # Missing sections should have defaults
        default = EmberConfig.default()
        assert result.index.model == default.index.model
        assert result.redaction.max_file_mb == default.redaction.max_file_mb
        assert result.model.mode == default.model.mode

    def test_load_empty_config_returns_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path, no_global_config: Path
    ) -> None:
        """Test that empty config file returns defaults.

        Uses no_global_config fixture to isolate from user's actual global config.
        """
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text("")

        result = provider.load(ember_dir)

        # Should return defaults (empty config = all defaults)
        default = EmberConfig.default()
        assert result == default


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_config_with_empty_arrays(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test config with empty arrays."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[index]
include = []
ignore = []

[search]
filters = []

[redaction]
patterns = []
"""
        )

        result = provider.load(ember_dir)

        assert result.index.include == []
        assert result.index.ignore == []
        assert result.search.filters == []
        assert result.redaction.patterns == []

    def test_load_config_with_unicode(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test config with unicode characters."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[display]
theme = "日本語テーマ"
"""
        )

        result = provider.load(ember_dir)

        assert result.display.theme == "日本語テーマ"

    def test_load_config_with_special_characters_in_patterns(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Test config with regex patterns containing special characters."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            r"""
[redaction]
patterns = ["api_key\\s*=\\s*['\"].*['\"]", "(?i)secret.*"]
"""
        )

        result = provider.load(ember_dir)

        assert len(result.redaction.patterns) == 2
        assert "api_key" in result.redaction.patterns[0]
