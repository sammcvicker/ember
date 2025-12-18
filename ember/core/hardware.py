"""Hardware detection utilities for auto-selecting embedding models.

This module detects system resources and recommends appropriate embedding models
based on available RAM. It's used during `ember init` to suggest a model and
to resolve `model = "auto"` in configuration.
"""

from dataclasses import dataclass

# Memory requirements for each model (in GB)
# These are approximate values based on model loading + inference overhead
MODEL_MEMORY_GB = {
    "jina-code-v2": 1.6,
    "bge-small": 0.13,
    "minilm": 0.1,
}

# Minimum available RAM thresholds for model selection (in GB)
# We add headroom above the model size for system stability
JINA_THRESHOLD_GB = 4.0  # Need 4GB+ for Jina (1.6GB model + overhead)
BGE_THRESHOLD_GB = 1.0  # Need 1GB+ for BGE-small (130MB model + overhead)
# Below 1GB: use MiniLM (100MB model)


@dataclass
class SystemResources:
    """System resource information for model selection."""

    available_ram_gb: float
    total_ram_gb: float


def detect_system_resources() -> SystemResources:
    """Detect available system resources.

    Returns:
        SystemResources with RAM information

    Note:
        Falls back to generous defaults if psutil is unavailable,
        which will recommend the full-featured Jina model.
    """
    try:
        import psutil

        mem = psutil.virtual_memory()
        return SystemResources(
            available_ram_gb=mem.available / (1024**3),
            total_ram_gb=mem.total / (1024**3),
        )
    except ImportError:
        # psutil not available - return generous defaults
        # Assume 8GB available to recommend full-featured model
        # This avoids prompting users when we can't detect hardware
        return SystemResources(
            available_ram_gb=8.0,
            total_ram_gb=16.0,
        )


def recommend_model(resources: SystemResources | None = None) -> str:
    """Recommend an embedding model based on system resources.

    Args:
        resources: System resources (auto-detected if None)

    Returns:
        Recommended model preset name
    """
    if resources is None:
        resources = detect_system_resources()

    available_gb = resources.available_ram_gb

    if available_gb >= JINA_THRESHOLD_GB:
        return "jina-code-v2"
    elif available_gb >= BGE_THRESHOLD_GB:
        return "bge-small"
    else:
        return "minilm"


def get_model_recommendation_reason(model: str, resources: SystemResources) -> str:
    """Get a human-readable reason for the model recommendation.

    Args:
        model: The recommended model preset name
        resources: The system resources used for the recommendation

    Returns:
        Human-readable explanation
    """
    available_gb = resources.available_ram_gb
    memory_str = f"{available_gb:.1f}GB"

    if model == "jina-code-v2":
        return f"Available RAM ({memory_str}) supports the full-featured model"
    elif model == "bge-small":
        return f"Available RAM ({memory_str}) is below 4GB; using compact model for better stability"
    else:  # minilm
        return f"Available RAM ({memory_str}) is limited; using lightweight model"
