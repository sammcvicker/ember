"""Tests for the model registry."""

from unittest.mock import MagicMock, patch

import pytest

from ember.adapters.local_models.registry import (
    DEFAULT_MODEL,
    MODEL_PRESETS,
    MODEL_REGISTRY,
    SUPPORTED_MODELS,
    ModelSpec,
    _build_embedder_kwargs,
    create_embedder,
    get_model_info,
    is_model_cached,
    list_available_models,
    resolve_model_name,
)


class TestBuildEmbedderKwargs:
    """Tests for _build_embedder_kwargs helper function."""

    def test_batch_size_always_included(self):
        """Test that batch_size is always in kwargs."""
        result = _build_embedder_kwargs(batch_size=32, device=None, max_seq_length=None)
        assert result == {"batch_size": 32}

    def test_device_included_when_not_none(self):
        """Test that device is included when provided."""
        result = _build_embedder_kwargs(batch_size=32, device="cuda", max_seq_length=None)
        assert result == {"batch_size": 32, "device": "cuda"}

    def test_max_seq_length_included_when_not_none(self):
        """Test that max_seq_length is included when provided."""
        result = _build_embedder_kwargs(batch_size=32, device=None, max_seq_length=512)
        assert result == {"batch_size": 32, "max_seq_length": 512}

    def test_all_params_included_when_provided(self):
        """Test that all params are included when provided."""
        result = _build_embedder_kwargs(batch_size=64, device="mps", max_seq_length=256)
        assert result == {"batch_size": 64, "device": "mps", "max_seq_length": 256}

    def test_device_cpu(self):
        """Test that device=cpu works correctly."""
        result = _build_embedder_kwargs(batch_size=32, device="cpu", max_seq_length=None)
        assert result == {"batch_size": 32, "device": "cpu"}


class TestResolveModelName:
    """Tests for resolve_model_name function."""

    def test_resolve_preset_jina_code_v2(self):
        """Test resolving jina-code-v2 preset."""
        assert resolve_model_name("jina-code-v2") == "jinaai/jina-embeddings-v2-base-code"

    def test_resolve_preset_minilm(self):
        """Test resolving minilm preset."""
        assert resolve_model_name("minilm") == "sentence-transformers/all-MiniLM-L6-v2"

    def test_resolve_preset_bge_small(self):
        """Test resolving bge-small preset."""
        assert resolve_model_name("bge-small") == "BAAI/bge-small-en-v1.5"

    def test_resolve_preset_case_insensitive(self):
        """Test that preset names are case-insensitive."""
        assert resolve_model_name("MINILM") == "sentence-transformers/all-MiniLM-L6-v2"
        assert resolve_model_name("MiniLM") == "sentence-transformers/all-MiniLM-L6-v2"
        assert resolve_model_name("BGE-SMALL") == "BAAI/bge-small-en-v1.5"

    def test_resolve_legacy_default_name(self):
        """Test resolving legacy 'local-default-code-embed' name."""
        assert (
            resolve_model_name("local-default-code-embed")
            == "jinaai/jina-embeddings-v2-base-code"
        )

    def test_resolve_full_huggingface_id(self):
        """Test resolving full HuggingFace model ID."""
        assert (
            resolve_model_name("jinaai/jina-embeddings-v2-base-code")
            == "jinaai/jina-embeddings-v2-base-code"
        )
        assert (
            resolve_model_name("sentence-transformers/all-MiniLM-L6-v2")
            == "sentence-transformers/all-MiniLM-L6-v2"
        )
        assert resolve_model_name("BAAI/bge-small-en-v1.5") == "BAAI/bge-small-en-v1.5"

    def test_resolve_unknown_model_raises_error(self):
        """Test that unknown model names raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            resolve_model_name("unknown-model")
        assert "Unknown embedding model" in str(exc_info.value)
        assert "unknown-model" in str(exc_info.value)

    def test_resolve_error_shows_valid_options(self):
        """Test that error message includes valid options."""
        with pytest.raises(ValueError) as exc_info:
            resolve_model_name("invalid")
        error_msg = str(exc_info.value)
        assert "jina-code-v2" in error_msg or "minilm" in error_msg

    def test_resolve_error_shows_auto_option(self):
        """Test that error message includes 'auto' as a valid option."""
        with pytest.raises(ValueError) as exc_info:
            resolve_model_name("invalid")
        error_msg = str(exc_info.value)
        assert "auto" in error_msg


class TestCreateEmbedder:
    """Tests for create_embedder function."""

    @patch("ember.adapters.local_models.jina_embedder.JinaCodeEmbedder")
    def test_create_default_embedder(self, mock_jina):
        """Test creating default embedder (Jina) when no model specified."""
        mock_instance = MagicMock()
        mock_jina.return_value = mock_instance

        result = create_embedder()

        mock_jina.assert_called_once()
        assert result == mock_instance

    @patch("ember.adapters.local_models.jina_embedder.JinaCodeEmbedder")
    def test_create_jina_embedder_by_preset(self, mock_jina):
        """Test creating Jina embedder using preset name."""
        mock_instance = MagicMock()
        mock_jina.return_value = mock_instance

        result = create_embedder(model_name="jina-code-v2")

        mock_jina.assert_called_once()
        assert result == mock_instance

    @patch("ember.adapters.local_models.minilm_embedder.MiniLMEmbedder")
    def test_create_minilm_embedder(self, mock_minilm):
        """Test creating MiniLM embedder."""
        mock_instance = MagicMock()
        mock_minilm.return_value = mock_instance

        result = create_embedder(model_name="minilm")

        mock_minilm.assert_called_once()
        assert result == mock_instance

    @patch("ember.adapters.local_models.bge_embedder.BGESmallEmbedder")
    def test_create_bge_embedder(self, mock_bge):
        """Test creating BGE-small embedder."""
        mock_instance = MagicMock()
        mock_bge.return_value = mock_instance

        result = create_embedder(model_name="bge-small")

        mock_bge.assert_called_once()
        assert result == mock_instance

    @patch("ember.adapters.local_models.minilm_embedder.MiniLMEmbedder")
    def test_create_embedder_passes_batch_size(self, mock_minilm):
        """Test that batch_size is passed to embedder."""
        mock_instance = MagicMock()
        mock_minilm.return_value = mock_instance

        create_embedder(model_name="minilm", batch_size=64)

        mock_minilm.assert_called_once()
        call_kwargs = mock_minilm.call_args[1]
        assert call_kwargs["batch_size"] == 64

    @patch("ember.adapters.local_models.minilm_embedder.MiniLMEmbedder")
    def test_create_embedder_passes_max_seq_length(self, mock_minilm):
        """Test that max_seq_length is passed to embedder."""
        mock_instance = MagicMock()
        mock_minilm.return_value = mock_instance

        create_embedder(model_name="minilm", max_seq_length=128)

        mock_minilm.assert_called_once()
        call_kwargs = mock_minilm.call_args[1]
        assert call_kwargs["max_seq_length"] == 128

    @patch("ember.adapters.local_models.minilm_embedder.MiniLMEmbedder")
    def test_create_embedder_passes_device(self, mock_minilm):
        """Test that device is passed to embedder."""
        mock_instance = MagicMock()
        mock_minilm.return_value = mock_instance

        create_embedder(model_name="minilm", device="cuda")

        mock_minilm.assert_called_once()
        call_kwargs = mock_minilm.call_args[1]
        assert call_kwargs["device"] == "cuda"

    def test_create_embedder_unknown_model_raises_error(self):
        """Test that unknown model names raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            create_embedder(model_name="unknown-model")
        assert "Unknown embedding model" in str(exc_info.value)


class TestGetModelInfo:
    """Tests for get_model_info function."""

    def test_get_jina_info(self):
        """Test getting info for Jina model."""
        info = get_model_info("jina-code-v2")
        assert info["name"] == "jinaai/jina-embeddings-v2-base-code"
        assert info["dim"] == 768
        assert info["params"] == "161M"
        assert info["preset"] == "jina-code-v2"

    def test_get_minilm_info(self):
        """Test getting info for MiniLM model."""
        info = get_model_info("minilm")
        assert info["name"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert info["dim"] == 384
        assert info["params"] == "22M"
        assert info["preset"] == "minilm"

    def test_get_bge_info(self):
        """Test getting info for BGE-small model."""
        info = get_model_info("bge-small")
        assert info["name"] == "BAAI/bge-small-en-v1.5"
        assert info["dim"] == 384
        assert info["params"] == "33M"
        assert info["preset"] == "bge-small"

    def test_get_info_by_huggingface_id(self):
        """Test getting info using full HuggingFace ID."""
        info = get_model_info("jinaai/jina-embeddings-v2-base-code")
        assert info["name"] == "jinaai/jina-embeddings-v2-base-code"
        assert info["dim"] == 768
        # Preset should be None when using full ID
        assert info["preset"] is None

    def test_get_info_unknown_model_raises_error(self):
        """Test that unknown model names raise ValueError."""
        with pytest.raises(ValueError):
            get_model_info("unknown-model")


class TestListAvailableModels:
    """Tests for list_available_models function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        result = list_available_models()
        assert isinstance(result, list)

    def test_contains_all_unique_models(self):
        """Test that list contains all unique models."""
        result = list_available_models()
        # Should have 3 unique models (Jina, MiniLM, BGE)
        assert len(result) == 3

    def test_each_model_has_required_fields(self):
        """Test that each model info has required fields."""
        result = list_available_models()
        for model in result:
            assert "name" in model
            assert "dim" in model
            assert "params" in model
            assert "memory" in model
            assert "presets" in model

    def test_presets_are_populated(self):
        """Test that presets list is populated for each model."""
        result = list_available_models()
        for model in result:
            assert len(model["presets"]) > 0


class TestModelPresets:
    """Tests for MODEL_PRESETS constant."""

    def test_all_presets_resolve_to_supported_models(self):
        """Test that all presets map to supported models."""
        for preset, resolved in MODEL_PRESETS.items():
            assert resolved in SUPPORTED_MODELS, f"Preset {preset} maps to unsupported model"


class TestDefaultModel:
    """Tests for DEFAULT_MODEL constant."""

    def test_default_is_jina(self):
        """Test that default model is Jina."""
        assert DEFAULT_MODEL == "jinaai/jina-embeddings-v2-base-code"

    def test_default_is_supported(self):
        """Test that default model is in supported models."""
        assert DEFAULT_MODEL in SUPPORTED_MODELS


class TestModelSpec:
    """Tests for ModelSpec dataclass."""

    def test_model_spec_is_frozen(self):
        """Test that ModelSpec instances are immutable."""
        from dataclasses import FrozenInstanceError

        spec = ModelSpec(
            id="test/model",
            presets=("test",),
            dim=128,
            params="1M",
            memory="~10MB",
            max_seq_length=256,
            description="Test model",
        )
        with pytest.raises(FrozenInstanceError):
            spec.dim = 256

    def test_model_spec_has_all_required_fields(self):
        """Test that ModelSpec has all expected fields."""
        spec = list(MODEL_REGISTRY.values())[0]
        assert hasattr(spec, "id")
        assert hasattr(spec, "presets")
        assert hasattr(spec, "dim")
        assert hasattr(spec, "params")
        assert hasattr(spec, "memory")
        assert hasattr(spec, "max_seq_length")
        assert hasattr(spec, "description")


class TestModelRegistry:
    """Tests for MODEL_REGISTRY as single source of truth."""

    def test_registry_contains_all_supported_models(self):
        """Test that SUPPORTED_MODELS is derived from MODEL_REGISTRY."""
        assert set(MODEL_REGISTRY.keys()) == SUPPORTED_MODELS

    def test_presets_derived_from_registry(self):
        """Test that MODEL_PRESETS is derived from MODEL_REGISTRY."""
        for model_id, spec in MODEL_REGISTRY.items():
            for preset in spec.presets:
                assert preset in MODEL_PRESETS
                assert MODEL_PRESETS[preset] == model_id

    def test_all_preset_names_in_registry(self):
        """Test that all preset names come from MODEL_REGISTRY specs."""
        all_presets_from_registry = set()
        for spec in MODEL_REGISTRY.values():
            all_presets_from_registry.update(spec.presets)
        assert set(MODEL_PRESETS.keys()) == all_presets_from_registry

    def test_get_model_info_uses_registry_data(self):
        """Test that get_model_info returns data from MODEL_REGISTRY."""
        for model_id, spec in MODEL_REGISTRY.items():
            info = get_model_info(model_id)
            assert info["name"] == spec.id
            assert info["dim"] == spec.dim
            assert info["params"] == spec.params
            assert info["memory"] == spec.memory
            assert info["max_seq_length"] == spec.max_seq_length
            assert info["description"] == spec.description

    def test_registry_model_ids_match_spec_ids(self):
        """Test that registry keys match their spec.id values."""
        for model_id, spec in MODEL_REGISTRY.items():
            assert model_id == spec.id

    def test_each_model_has_at_least_one_preset(self):
        """Test that each model in registry has at least one preset name."""
        for model_id, spec in MODEL_REGISTRY.items():
            assert len(spec.presets) > 0, f"Model {model_id} has no presets"

    def test_list_available_models_uses_registry(self):
        """Test that list_available_models returns all registry models."""
        models = list_available_models()
        assert len(models) == len(MODEL_REGISTRY)
        model_ids = {m["name"] for m in models}
        assert model_ids == set(MODEL_REGISTRY.keys())


class TestIsModelCached:
    """Tests for is_model_cached function (#378)."""

    def test_returns_true_when_model_loads_locally(self):
        """Test returns True when model loads with local_files_only."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_st.return_value = MagicMock()

            result = is_model_cached("minilm")

            assert result is True
            # Should be called with local_files_only=True
            call_kwargs = mock_st.call_args[1]
            assert call_kwargs["local_files_only"] is True

    def test_returns_false_when_oserror_raised(self):
        """Test returns False when OSError raised (model not cached)."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_st.side_effect = OSError("Model not found locally")

            result = is_model_cached("minilm")

            assert result is False

    def test_returns_false_when_valueerror_raised(self):
        """Test returns False when ValueError raised (model not cached)."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_st.side_effect = ValueError("Model files not found")

            result = is_model_cached("minilm")

            assert result is False

    def test_returns_false_when_import_fails(self):
        """Test returns False when sentence-transformers not installed."""
        # Remove the module from sys.modules to force re-import attempt
        import sys

        original_module = sys.modules.get("sentence_transformers")
        try:
            # Remove the module if it exists
            if "sentence_transformers" in sys.modules:
                del sys.modules["sentence_transformers"]

            # Mock the import to fail
            with patch.dict(sys.modules, {"sentence_transformers": None}):
                result = is_model_cached("minilm")
                assert result is False
        finally:
            # Restore the module
            if original_module is not None:
                sys.modules["sentence_transformers"] = original_module

    def test_uses_trust_remote_code_for_jina(self):
        """Test that trust_remote_code=True is set for Jina model."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_st.return_value = MagicMock()

            is_model_cached("jina-code-v2")

            call_kwargs = mock_st.call_args[1]
            assert call_kwargs["trust_remote_code"] is True

    def test_no_trust_remote_code_for_other_models(self):
        """Test that trust_remote_code is False for non-Jina models."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_st.return_value = MagicMock()

            is_model_cached("bge-small")

            call_kwargs = mock_st.call_args[1]
            assert call_kwargs["trust_remote_code"] is False

    def test_resolves_model_name(self):
        """Test that preset names are resolved to full model IDs."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_st.return_value = MagicMock()

            is_model_cached("minilm")

            # Should resolve "minilm" to full model ID
            call_args = mock_st.call_args[0]
            assert call_args[0] == "sentence-transformers/all-MiniLM-L6-v2"

    def test_returns_false_on_unexpected_exception(self):
        """Test returns False on unexpected errors (corrupted cache)."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_st.side_effect = RuntimeError("Corrupted cache")

            result = is_model_cached("minilm")

            assert result is False
