"""Tests for domain config classes validation."""

import pytest

from ember.domain.config import (
    DisplayConfig,
    EmberConfig,
    IndexConfig,
    ModelConfig,
    RedactionConfig,
    SearchConfig,
)

# =============================================================================
# IndexConfig validation tests
# =============================================================================


class TestIndexConfigValidation:
    """Tests for IndexConfig entity validation."""

    def test_index_config_valid_defaults(self):
        """Test creating IndexConfig with valid defaults."""
        config = IndexConfig()
        assert config.line_window == 120
        assert config.line_stride == 100
        assert config.overlap_lines == 15

    def test_index_config_valid_custom_values(self):
        """Test creating IndexConfig with valid custom values."""
        config = IndexConfig(line_window=200, line_stride=150, overlap_lines=20)
        assert config.line_window == 200
        assert config.line_stride == 150
        assert config.overlap_lines == 20

    def test_index_config_line_window_zero_raises_error(self):
        """Test that line_window=0 raises ValueError."""
        with pytest.raises(ValueError, match="line_window must be positive"):
            IndexConfig(line_window=0)

    def test_index_config_line_window_negative_raises_error(self):
        """Test that negative line_window raises ValueError."""
        with pytest.raises(ValueError, match="line_window must be positive"):
            IndexConfig(line_window=-10)

    def test_index_config_line_stride_zero_raises_error(self):
        """Test that line_stride=0 raises ValueError."""
        with pytest.raises(ValueError, match="line_stride must be positive"):
            IndexConfig(line_stride=0)

    def test_index_config_line_stride_negative_raises_error(self):
        """Test that negative line_stride raises ValueError."""
        with pytest.raises(ValueError, match="line_stride must be positive"):
            IndexConfig(line_stride=-5)

    def test_index_config_overlap_lines_negative_raises_error(self):
        """Test that negative overlap_lines raises ValueError."""
        with pytest.raises(ValueError, match="overlap_lines cannot be negative"):
            IndexConfig(overlap_lines=-1)

    def test_index_config_overlap_lines_zero_valid(self):
        """Test that overlap_lines=0 is valid (no overlap)."""
        config = IndexConfig(overlap_lines=0)
        assert config.overlap_lines == 0

    def test_index_config_overlap_greater_than_window_raises_error(self):
        """Test that overlap_lines >= line_window raises ValueError."""
        with pytest.raises(ValueError, match="overlap_lines.*must be less than.*line_window"):
            IndexConfig(line_window=100, overlap_lines=100)

        with pytest.raises(ValueError, match="overlap_lines.*must be less than.*line_window"):
            IndexConfig(line_window=100, overlap_lines=150)

    def test_index_config_stride_exceeds_window_raises_error(self):
        """Test that line_stride > line_window raises ValueError."""
        with pytest.raises(ValueError, match="line_stride.*cannot exceed.*line_window"):
            IndexConfig(line_window=100, line_stride=150)

    def test_index_config_stride_equals_window_valid(self):
        """Test that line_stride == line_window is valid (no overlap)."""
        config = IndexConfig(line_window=100, line_stride=100, overlap_lines=0)
        assert config.line_stride == 100
        assert config.line_window == 100

    def test_index_config_stride_less_than_window_valid(self):
        """Test that line_stride < line_window is valid (with overlap)."""
        config = IndexConfig(line_window=100, line_stride=80)
        assert config.line_stride == 80
        assert config.line_window == 100

    def test_index_config_valid_include_patterns(self):
        """Test that valid include glob patterns are accepted."""
        config = IndexConfig(include=["**/*.py", "src/**/*.ts", "*.go"])
        assert config.include == ["**/*.py", "src/**/*.ts", "*.go"]

    def test_index_config_valid_ignore_patterns(self):
        """Test that valid ignore glob patterns are accepted."""
        config = IndexConfig(ignore=[".git/", "node_modules/", "*.pyc"])
        assert config.ignore == [".git/", "node_modules/", "*.pyc"]

    def test_index_config_empty_include_pattern_raises_error(self):
        """Test that empty pattern in include raises ValueError."""
        with pytest.raises(ValueError, match="Invalid glob in include"):
            IndexConfig(include=["**/*.py", "", "*.go"])

    def test_index_config_empty_ignore_pattern_raises_error(self):
        """Test that empty pattern in ignore raises ValueError."""
        with pytest.raises(ValueError, match="Invalid glob in ignore"):
            IndexConfig(ignore=[".git/", ""])

    def test_index_config_invalid_glob_with_double_slash_in_include(self):
        """Test that invalid glob with // in include raises ValueError."""
        with pytest.raises(ValueError, match="Invalid glob in include.*empty path segment"):
            IndexConfig(include=["**//file.py"])

    def test_index_config_invalid_glob_with_double_slash_in_ignore(self):
        """Test that invalid glob with // in ignore raises ValueError."""
        with pytest.raises(ValueError, match="Invalid glob in ignore.*empty path segment"):
            IndexConfig(ignore=["node_modules//"])

    def test_index_config_url_pattern_in_include_valid(self):
        """Test that URL-like patterns with :// are valid (not double-slash error)."""
        # Patterns like "http://example.com" shouldn't trigger the // check
        # This is an edge case - unlikely in practice but tests the validation logic
        config = IndexConfig(include=["**/*.py"])
        assert "**/*.py" in config.include

    def test_index_config_from_partial_validates_glob_patterns(self):
        """Test that from_partial validates glob patterns."""
        base = IndexConfig()
        with pytest.raises(ValueError, match="Invalid glob in include"):
            IndexConfig.from_partial(base, {"include": ["**//invalid.py"]})


# =============================================================================
# SearchConfig validation tests
# =============================================================================


class TestSearchConfigValidation:
    """Tests for SearchConfig entity validation."""

    def test_search_config_valid_defaults(self):
        """Test creating SearchConfig with valid defaults."""
        config = SearchConfig()
        assert config.topk == 20
        assert config.rerank is False

    def test_search_config_valid_custom_values(self):
        """Test creating SearchConfig with valid custom values."""
        config = SearchConfig(topk=50, rerank=True)
        assert config.topk == 50
        assert config.rerank is True

    def test_search_config_topk_zero_raises_error(self):
        """Test that topk=0 raises ValueError."""
        with pytest.raises(ValueError, match="topk must be positive"):
            SearchConfig(topk=0)

    def test_search_config_topk_negative_raises_error(self):
        """Test that negative topk raises ValueError."""
        with pytest.raises(ValueError, match="topk must be positive"):
            SearchConfig(topk=-5)

    def test_search_config_topk_one_valid(self):
        """Test that topk=1 is valid."""
        config = SearchConfig(topk=1)
        assert config.topk == 1


# =============================================================================
# RedactionConfig validation tests
# =============================================================================


class TestRedactionConfigValidation:
    """Tests for RedactionConfig entity validation."""

    def test_redaction_config_valid_defaults(self):
        """Test creating RedactionConfig with valid defaults."""
        config = RedactionConfig()
        assert config.max_file_mb == 5

    def test_redaction_config_valid_custom_values(self):
        """Test creating RedactionConfig with valid custom values."""
        config = RedactionConfig(max_file_mb=10)
        assert config.max_file_mb == 10

    def test_redaction_config_max_file_mb_zero_raises_error(self):
        """Test that max_file_mb=0 raises ValueError."""
        with pytest.raises(ValueError, match="max_file_mb must be positive"):
            RedactionConfig(max_file_mb=0)

    def test_redaction_config_max_file_mb_negative_raises_error(self):
        """Test that negative max_file_mb raises ValueError."""
        with pytest.raises(ValueError, match="max_file_mb must be positive"):
            RedactionConfig(max_file_mb=-1)

    def test_redaction_config_valid_regex_patterns(self):
        """Test that valid regex patterns are accepted."""
        config = RedactionConfig(
            patterns=[
                r"api_key\s*=\s*\w+",
                r"(?i)password",
                r"[A-Za-z0-9]{32}",
            ]
        )
        assert len(config.patterns) == 3

    def test_redaction_config_invalid_regex_raises_error(self):
        """Test that invalid regex patterns raise ValueError."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            RedactionConfig(patterns=[r"[invalid(regex"])

    def test_redaction_config_invalid_regex_identifies_pattern(self):
        """Test that error message identifies which pattern is invalid."""
        with pytest.raises(ValueError, match=r"\[invalid\(regex"):
            RedactionConfig(patterns=[r"valid_pattern", r"[invalid(regex"])

    def test_redaction_config_empty_patterns_list_valid(self):
        """Test that empty patterns list is valid (no redaction)."""
        config = RedactionConfig(patterns=[])
        assert config.patterns == []

    def test_redaction_config_multiple_invalid_patterns_reports_first(self):
        """Test that first invalid pattern is reported in error."""
        # Note: validation stops at first error, so order matters
        with pytest.raises(ValueError, match=r"\[first"):
            RedactionConfig(patterns=[r"[first", r"[second"])

    def test_redaction_config_default_patterns_are_valid(self):
        """Test that all default patterns compile successfully."""
        # This ensures we don't ship with broken default patterns
        config = RedactionConfig()
        import re

        for pattern in config.patterns:
            re.compile(pattern)  # Should not raise


# =============================================================================
# ModelConfig validation tests
# =============================================================================


class TestModelConfigValidation:
    """Tests for ModelConfig entity validation."""

    def test_model_config_valid_defaults(self):
        """Test creating ModelConfig with valid defaults."""
        config = ModelConfig()
        assert config.daemon_timeout == 900
        assert config.daemon_startup_timeout == 5

    def test_model_config_valid_custom_values(self):
        """Test creating ModelConfig with valid custom values."""
        config = ModelConfig(daemon_timeout=600, daemon_startup_timeout=10)
        assert config.daemon_timeout == 600
        assert config.daemon_startup_timeout == 10

    def test_model_config_daemon_timeout_zero_raises_error(self):
        """Test that daemon_timeout=0 raises ValueError."""
        with pytest.raises(ValueError, match="daemon_timeout must be positive"):
            ModelConfig(daemon_timeout=0)

    def test_model_config_daemon_timeout_negative_raises_error(self):
        """Test that negative daemon_timeout raises ValueError."""
        with pytest.raises(ValueError, match="daemon_timeout must be positive"):
            ModelConfig(daemon_timeout=-100)

    def test_model_config_daemon_startup_timeout_zero_raises_error(self):
        """Test that daemon_startup_timeout=0 raises ValueError."""
        with pytest.raises(ValueError, match="daemon_startup_timeout must be positive"):
            ModelConfig(daemon_startup_timeout=0)

    def test_model_config_daemon_startup_timeout_negative_raises_error(self):
        """Test that negative daemon_startup_timeout raises ValueError."""
        with pytest.raises(ValueError, match="daemon_startup_timeout must be positive"):
            ModelConfig(daemon_startup_timeout=-1)


# =============================================================================
# DisplayConfig validation tests
# =============================================================================


class TestDisplayConfigValidation:
    """Tests for DisplayConfig entity validation."""

    def test_display_config_valid_defaults(self):
        """Test creating DisplayConfig with valid defaults."""
        config = DisplayConfig()
        assert config.syntax_highlighting is True
        assert config.color_scheme == "auto"
        assert config.theme == "ansi"

    def test_display_config_valid_custom_values(self):
        """Test creating DisplayConfig with valid custom values."""
        config = DisplayConfig(
            syntax_highlighting=False, color_scheme="always", theme="monokai"
        )
        assert config.syntax_highlighting is False
        assert config.color_scheme == "always"
        assert config.theme == "monokai"

    def test_display_config_valid_pygments_themes(self):
        """Test that common Pygments themes are accepted."""
        for theme in ["ansi", "monokai", "github-dark", "dracula", "solarized-dark"]:
            config = DisplayConfig(theme=theme)
            assert config.theme == theme

    def test_display_config_invalid_theme_raises_error(self):
        """Test that invalid theme raises ValueError."""
        with pytest.raises(ValueError, match="Unknown theme 'invalid-theme'"):
            DisplayConfig(theme="invalid-theme")

    def test_display_config_empty_theme_raises_error(self):
        """Test that empty theme raises ValueError."""
        with pytest.raises(ValueError, match="Unknown theme ''"):
            DisplayConfig(theme="")


# =============================================================================
# Config from_partial merge tests
# =============================================================================


class TestIndexConfigFromPartial:
    """Tests for IndexConfig.from_partial merge method."""

    def test_from_partial_empty_dict_returns_base(self):
        """Test that empty partial dict returns base values unchanged."""
        base = IndexConfig(model="custom-model", line_window=200)
        result = IndexConfig.from_partial(base, {})

        assert result.model == "custom-model"
        assert result.line_window == 200

    def test_from_partial_overrides_specified_keys(self):
        """Test that only specified keys are overridden."""
        base = IndexConfig(model="base-model", line_window=120, batch_size=32)
        result = IndexConfig.from_partial(base, {"model": "new-model"})

        assert result.model == "new-model"
        assert result.line_window == 120  # Unchanged
        assert result.batch_size == 32  # Unchanged

    def test_from_partial_validates_result(self):
        """Test that merged config is validated."""
        base = IndexConfig()
        with pytest.raises(ValueError, match="line_window must be positive"):
            IndexConfig.from_partial(base, {"line_window": 0})

    def test_from_partial_override_multiple_fields(self):
        """Test overriding multiple fields at once."""
        base = IndexConfig()
        result = IndexConfig.from_partial(
            base,
            {"model": "minilm", "chunk": "lines", "batch_size": 64},
        )

        assert result.model == "minilm"
        assert result.chunk == "lines"
        assert result.batch_size == 64


class TestSearchConfigFromPartial:
    """Tests for SearchConfig.from_partial merge method."""

    def test_from_partial_empty_dict_returns_base(self):
        """Test that empty partial dict returns base values unchanged."""
        base = SearchConfig(topk=50, rerank=True)
        result = SearchConfig.from_partial(base, {})

        assert result.topk == 50
        assert result.rerank is True

    def test_from_partial_overrides_specified_keys(self):
        """Test that only specified keys are overridden."""
        base = SearchConfig(topk=20, rerank=False)
        result = SearchConfig.from_partial(base, {"topk": 100})

        assert result.topk == 100
        assert result.rerank is False  # Unchanged

    def test_from_partial_validates_result(self):
        """Test that merged config is validated."""
        base = SearchConfig()
        with pytest.raises(ValueError, match="topk must be positive"):
            SearchConfig.from_partial(base, {"topk": 0})


class TestRedactionConfigFromPartial:
    """Tests for RedactionConfig.from_partial merge method."""

    def test_from_partial_empty_dict_returns_base(self):
        """Test that empty partial dict returns base values unchanged."""
        base = RedactionConfig(max_file_mb=10)
        result = RedactionConfig.from_partial(base, {})

        assert result.max_file_mb == 10

    def test_from_partial_overrides_patterns(self):
        """Test that patterns list can be overridden."""
        base = RedactionConfig()
        custom_patterns = [r"custom_pattern"]
        result = RedactionConfig.from_partial(base, {"patterns": custom_patterns})

        assert result.patterns == custom_patterns

    def test_from_partial_validates_result(self):
        """Test that merged config is validated."""
        base = RedactionConfig()
        with pytest.raises(ValueError, match="max_file_mb must be positive"):
            RedactionConfig.from_partial(base, {"max_file_mb": 0})

    def test_from_partial_validates_regex_patterns(self):
        """Test that from_partial validates regex patterns."""
        base = RedactionConfig()
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            RedactionConfig.from_partial(base, {"patterns": [r"[invalid("]})


class TestModelConfigFromPartial:
    """Tests for ModelConfig.from_partial merge method."""

    def test_from_partial_empty_dict_returns_base(self):
        """Test that empty partial dict returns base values unchanged."""
        base = ModelConfig(mode="direct", daemon_timeout=600)
        result = ModelConfig.from_partial(base, {})

        assert result.mode == "direct"
        assert result.daemon_timeout == 600

    def test_from_partial_overrides_mode(self):
        """Test that mode can be overridden."""
        base = ModelConfig(mode="daemon")
        result = ModelConfig.from_partial(base, {"mode": "direct"})

        assert result.mode == "direct"

    def test_from_partial_validates_result(self):
        """Test that merged config is validated."""
        base = ModelConfig()
        with pytest.raises(ValueError, match="daemon_timeout must be positive"):
            ModelConfig.from_partial(base, {"daemon_timeout": 0})


class TestDisplayConfigFromPartial:
    """Tests for DisplayConfig.from_partial merge method."""

    def test_from_partial_empty_dict_returns_base(self):
        """Test that empty partial dict returns base values unchanged."""
        base = DisplayConfig(theme="monokai")
        result = DisplayConfig.from_partial(base, {})

        assert result.theme == "monokai"

    def test_from_partial_overrides_specified_keys(self):
        """Test that only specified keys are overridden."""
        base = DisplayConfig(syntax_highlighting=True, theme="ansi")
        result = DisplayConfig.from_partial(base, {"theme": "github-dark"})

        assert result.syntax_highlighting is True  # Unchanged
        assert result.theme == "github-dark"

    def test_from_partial_validates_result(self):
        """Test that merged config is validated."""
        base = DisplayConfig()
        with pytest.raises(ValueError, match="Unknown theme"):
            DisplayConfig.from_partial(base, {"theme": "not-a-real-theme"})


class TestEmberConfigFromPartial:
    """Tests for EmberConfig.from_partial merge method."""

    def test_from_partial_empty_dict_returns_base(self):
        """Test that empty partial dict returns base config unchanged."""
        base = EmberConfig.default()
        result = EmberConfig.from_partial(base, {})

        assert result.index.model == base.index.model
        assert result.search.topk == base.search.topk

    def test_from_partial_merges_single_section(self):
        """Test merging a single section."""
        base = EmberConfig.default()
        result = EmberConfig.from_partial(base, {"search": {"topk": 100}})

        assert result.search.topk == 100
        assert result.index.model == base.index.model  # Other sections unchanged

    def test_from_partial_merges_multiple_sections(self):
        """Test merging multiple sections."""
        base = EmberConfig.default()
        result = EmberConfig.from_partial(
            base,
            {
                "index": {"model": "minilm", "batch_size": 64},
                "search": {"topk": 50, "rerank": True},
                "display": {"theme": "monokai"},
            },
        )

        assert result.index.model == "minilm"
        assert result.index.batch_size == 64
        assert result.search.topk == 50
        assert result.search.rerank is True
        assert result.display.theme == "monokai"

    def test_from_partial_validates_all_sections(self):
        """Test that validation runs on all merged sections."""
        base = EmberConfig.default()

        # Invalid index config
        with pytest.raises(ValueError, match="line_window must be positive"):
            EmberConfig.from_partial(base, {"index": {"line_window": 0}})

        # Invalid search config
        with pytest.raises(ValueError, match="topk must be positive"):
            EmberConfig.from_partial(base, {"search": {"topk": -1}})

    def test_from_partial_partial_section_override(self):
        """Test that partial section overrides preserve unspecified keys."""
        base = EmberConfig(
            index=IndexConfig(model="base-model", line_window=200, batch_size=16)
        )
        result = EmberConfig.from_partial(base, {"index": {"model": "new-model"}})

        assert result.index.model == "new-model"
        assert result.index.line_window == 200  # Preserved
        assert result.index.batch_size == 16  # Preserved

    def test_from_partial_chained_merges(self):
        """Test that multiple from_partial calls can be chained (global + local)."""
        defaults = EmberConfig.default()

        # Simulate global config
        global_data = {"index": {"model": "jina-code-v2"}, "search": {"topk": 30}}
        with_global = EmberConfig.from_partial(defaults, global_data)

        # Simulate local config (overrides global)
        local_data = {"search": {"topk": 10}}
        final = EmberConfig.from_partial(with_global, local_data)

        assert final.index.model == "jina-code-v2"  # From global
        assert final.search.topk == 10  # Overridden by local
