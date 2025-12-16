"""Tests for domain config classes validation."""

import pytest

from ember.domain.config import (
    DisplayConfig,
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
# DisplayConfig validation tests (no validation needed, just literal types)
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
