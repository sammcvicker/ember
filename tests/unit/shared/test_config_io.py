"""Tests for config I/O utilities."""

import pytest

from ember.shared.config_io import (
    _validate_model_name,
    config_data_to_ember_config,
)


class TestValidateModelName:
    """Tests for _validate_model_name function."""

    def test_valid_preset_name(self):
        """Test validation passes for valid preset names."""
        # Should not raise
        _validate_model_name("jina-code-v2")
        _validate_model_name("minilm")
        _validate_model_name("bge-small")

    def test_valid_hf_model_id(self):
        """Test validation passes for valid HuggingFace model IDs."""
        # Should not raise
        _validate_model_name("jinaai/jina-embeddings-v2-base-code")
        _validate_model_name("sentence-transformers/all-MiniLM-L6-v2")
        _validate_model_name("BAAI/bge-small-en-v1.5")

    def test_case_insensitive_presets(self):
        """Test that preset names are case insensitive."""
        # Should not raise
        _validate_model_name("MINILM")
        _validate_model_name("MiniLM")
        _validate_model_name("BGE-SMALL")

    def test_invalid_model_name_raises(self):
        """Test that invalid model names raise ValueError."""
        with pytest.raises(ValueError, match="Invalid model configuration"):
            _validate_model_name("unknown-model")

        with pytest.raises(ValueError, match="Invalid model configuration"):
            _validate_model_name("not-a-real-model")


class TestConfigDataToEmberConfig:
    """Tests for config_data_to_ember_config function."""

    def test_empty_data_returns_defaults(self):
        """Test that empty data dict returns config with defaults."""
        config = config_data_to_ember_config({})

        assert config.index.line_window == 120
        assert config.index.model == "local-default-code-embed"
        assert config.search.topk == 20

    def test_valid_model_name_in_config(self):
        """Test that valid model names are accepted."""
        data = {"index": {"model": "minilm"}}
        config = config_data_to_ember_config(data)

        assert config.index.model == "minilm"

    def test_invalid_model_name_raises(self):
        """Test that invalid model names raise ValueError."""
        data = {"index": {"model": "not-a-real-model"}}

        with pytest.raises(ValueError, match="Invalid model configuration"):
            config_data_to_ember_config(data)

    def test_custom_values_preserved(self):
        """Test that custom config values are preserved."""
        data = {
            "index": {
                "model": "bge-small",
                "line_window": 200,
            },
            "search": {
                "topk": 50,
            },
        }
        config = config_data_to_ember_config(data)

        assert config.index.model == "bge-small"
        assert config.index.line_window == 200
        assert config.search.topk == 50


class TestIndexConfigNoModelValidation:
    """Tests verifying IndexConfig no longer validates model names.

    This test class verifies the architecture fix: domain models should
    not import from adapters layer. Model validation now happens at the
    config boundary (config_io) instead of in the domain model.
    """

    def test_index_config_accepts_any_model_name(self):
        """Test that IndexConfig accepts any string as model name.

        The domain model no longer validates model names against the
        registry. Validation happens at the config loading boundary.
        """
        from ember.domain.config import IndexConfig

        # This should NOT raise, even with invalid model name
        config = IndexConfig(model="any-string-is-accepted")
        assert config.model == "any-string-is-accepted"

    def test_index_config_default_model_preserved(self):
        """Test that default model name is still preserved."""
        from ember.domain.config import IndexConfig

        config = IndexConfig()
        assert config.model == "local-default-code-embed"
