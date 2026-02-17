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
        """Test config with unicode characters in string fields."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        config_file = ember_dir / "config.toml"
        config_file.write_text(
            """
[index]
ignore = ["日本語ディレクトリ/", "中文文件夹/"]
"""
        )

        result = provider.load(ember_dir)

        assert "日本語ディレクトリ/" in result.index.ignore
        assert "中文文件夹/" in result.index.ignore

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


class TestGlobalLocalMerge:
    """Tests for global + local config merging behavior.

    The merge cascade is: defaults -> global overrides -> local overrides.
    Local config takes priority over global, which takes priority over defaults.
    """

    def test_global_config_overrides_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Global config values override built-in defaults."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        # No local config

        # Set up global config
        global_dir = tmp_path / "global_config" / "ember"
        global_dir.mkdir(parents=True)
        global_config = global_dir / "config.toml"
        global_config.write_text(
            """
[search]
topk = 75

[display]
theme = "monokai"
"""
        )

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        assert result.search.topk == 75
        assert result.display.theme == "monokai"
        # Other sections should use defaults
        assert result.index.line_window == 120

    def test_local_config_overrides_global(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Local config values take precedence over global config."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        # Local config overrides topk
        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[search]
topk = 200
"""
        )

        # Global config sets different topk and also rerank
        global_dir = tmp_path / "global_config" / "ember"
        global_dir.mkdir(parents=True)
        global_config = global_dir / "config.toml"
        global_config.write_text(
            """
[search]
topk = 75
rerank = true
"""
        )

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Local overrides global
        assert result.search.topk == 200
        # Global value preserved where local doesn't override
        assert result.search.rerank is True

    def test_merge_across_different_sections(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """Global and local configs can contribute different sections."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        # Local sets search section
        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[search]
topk = 50
"""
        )

        # Global sets display section
        global_dir = tmp_path / "global_config" / "ember"
        global_dir.mkdir(parents=True)
        global_config = global_dir / "config.toml"
        global_config.write_text(
            """
[display]
theme = "monokai"
syntax_highlighting = false
"""
        )

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=global_config,
        ):
            result = provider.load(ember_dir)

        # Local search settings
        assert result.search.topk == 50
        # Global display settings
        assert result.display.theme == "monokai"
        assert result.display.syntax_highlighting is False

    def test_invalid_global_config_falls_back_to_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid global config is ignored with a warning, defaults are used."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        # Valid local config
        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[search]
topk = 42
"""
        )

        # Invalid global config
        global_dir = tmp_path / "global_config" / "ember"
        global_dir.mkdir(parents=True)
        global_config = global_dir / "config.toml"
        global_config.write_text("this is [[ invalid toml")

        import logging

        with (
            patch(
                "ember.adapters.config.toml_config_provider.get_global_config_path",
                return_value=global_config,
            ),
            caplog.at_level(logging.WARNING),
        ):
            result = provider.load(ember_dir)

        # Local config should still apply
        assert result.search.topk == 42
        # Warning should be logged about global config
        assert "global config" in caplog.text.lower() or "Failed to parse global config" in caplog.text

    def test_invalid_local_config_falls_back_to_global(
        self, provider: TomlConfigProvider, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid local config is ignored, global config is still used."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        # Invalid local config
        local_config = ember_dir / "config.toml"
        local_config.write_text("this is [[ invalid toml")

        # Valid global config
        global_dir = tmp_path / "global_config" / "ember"
        global_dir.mkdir(parents=True)
        global_config = global_dir / "config.toml"
        global_config.write_text(
            """
[search]
topk = 99
"""
        )

        import logging

        with (
            patch(
                "ember.adapters.config.toml_config_provider.get_global_config_path",
                return_value=global_config,
            ),
            caplog.at_level(logging.WARNING),
        ):
            result = provider.load(ember_dir)

        # Global config should be used
        assert result.search.topk == 99
        # Warning about local config
        assert "config.toml" in caplog.text

    def test_both_configs_missing_returns_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path, no_global_config: Path
    ) -> None:
        """When both global and local configs are missing, defaults are returned."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        # No local config, no_global_config fixture handles global

        result = provider.load(ember_dir)

        default = EmberConfig.default()
        assert result == default

    def test_invalid_model_name_falls_back_to_defaults(
        self, provider: TomlConfigProvider, tmp_path: Path, no_global_config: Path
    ) -> None:
        """Invalid model name causes fallback to complete defaults."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[index]
model = "totally-nonexistent-model-xyz"

[search]
topk = 999
"""
        )

        with patch(
            "ember.adapters.config.toml_config_provider._validate_model_name",
            side_effect=ValueError("Unknown model"),
        ):
            result = provider.load(ember_dir)

        # Should fall back to complete defaults when model is invalid
        default = EmberConfig.default()
        assert result == default

    def test_global_config_not_loaded_when_not_exists(
        self, provider: TomlConfigProvider, tmp_path: Path
    ) -> None:
        """No global config is loaded when the file does not exist."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        local_config = ember_dir / "config.toml"
        local_config.write_text(
            """
[search]
topk = 30
"""
        )

        nonexistent_global = tmp_path / "nonexistent" / "config.toml"

        with patch(
            "ember.adapters.config.toml_config_provider.get_global_config_path",
            return_value=nonexistent_global,
        ):
            result = provider.load(ember_dir)

        assert result.search.topk == 30
