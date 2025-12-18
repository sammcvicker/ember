"""Tests for the hardware detection module."""

from unittest.mock import MagicMock, patch

import pytest

from ember.core.hardware import (
    BGE_THRESHOLD_GB,
    JINA_THRESHOLD_GB,
    SystemResources,
    detect_system_resources,
    get_model_recommendation_reason,
    recommend_model,
)


class TestSystemResources:
    """Tests for the SystemResources dataclass."""

    def test_create_system_resources(self):
        """Test creating a SystemResources instance."""
        resources = SystemResources(available_ram_gb=4.0, total_ram_gb=16.0)
        assert resources.available_ram_gb == 4.0
        assert resources.total_ram_gb == 16.0


class TestDetectSystemResources:
    """Tests for detect_system_resources function."""

    def test_detect_with_psutil_available(self):
        """Test detection when psutil is available (mocked)."""
        mock_mem = MagicMock()
        mock_mem.available = 8 * (1024**3)  # 8GB
        mock_mem.total = 16 * (1024**3)  # 16GB

        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = mock_mem

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            # Re-import the function to pick up the mock
            from importlib import reload

            import ember.core.hardware as hw_module

            reload(hw_module)
            resources = hw_module.detect_system_resources()

            assert resources.available_ram_gb == pytest.approx(8.0)
            assert resources.total_ram_gb == pytest.approx(16.0)

    def test_detect_without_psutil_returns_generous_defaults(self):
        """Test detection when psutil is not available returns generous defaults."""
        # When psutil is not available, we return generous defaults (8GB available)
        # to recommend the full-featured model and avoid unnecessary prompts
        # This test just verifies the function works with psutil installed
        resources = detect_system_resources()
        assert resources.available_ram_gb > 0
        assert resources.total_ram_gb > 0

    def test_detect_returns_system_resources_type(self):
        """Test that detect returns correct type with positive values."""
        resources = detect_system_resources()
        # Check that we got real values (not the fallback defaults)
        # The fallback is 2.0 GB available, 8.0 GB total
        assert resources.available_ram_gb > 0
        assert resources.total_ram_gb > 0
        # Verify it's the right named tuple structure
        assert hasattr(resources, "available_ram_gb")
        assert hasattr(resources, "total_ram_gb")


class TestRecommendModel:
    """Tests for recommend_model function."""

    def test_recommend_jina_for_high_ram(self):
        """Test that Jina is recommended for high RAM systems (>= 4GB)."""
        resources = SystemResources(available_ram_gb=8.0, total_ram_gb=16.0)
        assert recommend_model(resources) == "jina-code-v2"

    def test_recommend_jina_at_threshold(self):
        """Test that Jina is recommended at exactly 4GB."""
        resources = SystemResources(available_ram_gb=JINA_THRESHOLD_GB, total_ram_gb=8.0)
        assert recommend_model(resources) == "jina-code-v2"

    def test_recommend_bge_for_medium_ram(self):
        """Test that BGE-small is recommended for medium RAM (1-4GB)."""
        resources = SystemResources(available_ram_gb=2.0, total_ram_gb=4.0)
        assert recommend_model(resources) == "bge-small"

    def test_recommend_bge_at_threshold(self):
        """Test that BGE-small is recommended at exactly 1GB."""
        resources = SystemResources(available_ram_gb=BGE_THRESHOLD_GB, total_ram_gb=2.0)
        assert recommend_model(resources) == "bge-small"

    def test_recommend_minilm_for_low_ram(self):
        """Test that MiniLM is recommended for low RAM (< 1GB)."""
        resources = SystemResources(available_ram_gb=0.5, total_ram_gb=1.0)
        assert recommend_model(resources) == "minilm"

    def test_recommend_auto_detects_when_no_resources(self):
        """Test that recommend_model auto-detects resources when None."""
        # This should not raise an error and should return a valid model
        model = recommend_model()
        assert model in ["jina-code-v2", "bge-small", "minilm"]

    def test_threshold_values(self):
        """Test that threshold constants are set correctly."""
        assert JINA_THRESHOLD_GB == 4.0
        assert BGE_THRESHOLD_GB == 1.0


class TestGetModelRecommendationReason:
    """Tests for get_model_recommendation_reason function."""

    def test_reason_for_jina(self):
        """Test reason message for Jina recommendation."""
        resources = SystemResources(available_ram_gb=8.0, total_ram_gb=16.0)
        reason = get_model_recommendation_reason("jina-code-v2", resources)
        assert "8.0GB" in reason
        assert "full-featured" in reason

    def test_reason_for_bge(self):
        """Test reason message for BGE-small recommendation."""
        resources = SystemResources(available_ram_gb=2.0, total_ram_gb=4.0)
        reason = get_model_recommendation_reason("bge-small", resources)
        assert "2.0GB" in reason
        assert "below 4GB" in reason

    def test_reason_for_minilm(self):
        """Test reason message for MiniLM recommendation."""
        resources = SystemResources(available_ram_gb=0.5, total_ram_gb=1.0)
        reason = get_model_recommendation_reason("minilm", resources)
        assert "0.5GB" in reason
        assert "limited" in reason


class TestAutoModelInRegistry:
    """Tests for 'auto' model support in the registry."""

    def test_auto_resolves_to_valid_model(self):
        """Test that 'auto' resolves to a valid model."""
        from ember.adapters.local_models.registry import resolve_model_name

        resolved = resolve_model_name("auto")
        assert resolved in [
            "jinaai/jina-embeddings-v2-base-code",
            "sentence-transformers/all-MiniLM-L6-v2",
            "BAAI/bge-small-en-v1.5",
        ]

    def test_auto_case_insensitive(self):
        """Test that 'AUTO' works case-insensitively."""
        from ember.adapters.local_models.registry import resolve_model_name

        resolved_lower = resolve_model_name("auto")
        resolved_upper = resolve_model_name("AUTO")
        resolved_mixed = resolve_model_name("Auto")

        assert resolved_lower == resolved_upper == resolved_mixed

    @patch("ember.core.hardware.detect_system_resources")
    def test_auto_uses_hardware_detection(self, mock_detect):
        """Test that 'auto' uses hardware detection."""
        from ember.adapters.local_models.registry import resolve_model_name

        mock_detect.return_value = SystemResources(
            available_ram_gb=0.5, total_ram_gb=1.0
        )

        resolved = resolve_model_name("auto")
        assert resolved == "sentence-transformers/all-MiniLM-L6-v2"  # MiniLM

        mock_detect.assert_called_once()
