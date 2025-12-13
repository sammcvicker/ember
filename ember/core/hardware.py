"""Hardware detection utilities for auto-selecting embedding models.

This module detects system resources and recommends appropriate embedding models
based on available RAM and GPU VRAM. It's used during `ember init` to suggest a
model and to resolve `model = "auto"` in configuration.
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
class GPUResources:
    """GPU resource information for model selection."""

    device_name: str
    total_vram_gb: float
    free_vram_gb: float
    backend: str  # "cuda" or "mps"


@dataclass
class SystemResources:
    """System resource information for model selection."""

    available_ram_gb: float
    total_ram_gb: float
    gpu: GPUResources | None = None


def detect_gpu_resources() -> GPUResources | None:
    """Detect available GPU resources.

    Returns:
        GPUResources with VRAM information, or None if no GPU available.

    Note:
        Supports CUDA (NVIDIA) and MPS (Apple Silicon) backends.
        Returns None if torch is not installed or no GPU is detected.
    """
    try:
        import torch

        # Check for CUDA GPU first
        if torch.cuda.is_available():
            try:
                device_name = torch.cuda.get_device_name(0)
                total_memory = torch.cuda.get_device_properties(0).total_memory
                free_memory, _ = torch.cuda.mem_get_info()
                return GPUResources(
                    device_name=device_name,
                    total_vram_gb=total_memory / (1024**3),
                    free_vram_gb=free_memory / (1024**3),
                    backend="cuda",
                )
            except (RuntimeError, Exception):
                # CUDA error during detection - fall through to check MPS
                pass

        # Check for MPS (Apple Silicon)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # MPS uses unified memory - report system RAM as VRAM
            try:
                import psutil

                mem = psutil.virtual_memory()
                return GPUResources(
                    device_name="Apple Silicon (MPS)",
                    total_vram_gb=mem.total / (1024**3),
                    free_vram_gb=mem.available / (1024**3),
                    backend="mps",
                )
            except ImportError:
                # psutil not available, return approximate values
                return GPUResources(
                    device_name="Apple Silicon (MPS)",
                    total_vram_gb=8.0,  # Conservative default
                    free_vram_gb=4.0,
                    backend="mps",
                )

        # No GPU available
        return None

    except ImportError:
        # torch not installed
        return None


def detect_system_resources() -> SystemResources:
    """Detect available system resources including GPU.

    Returns:
        SystemResources with RAM and optional GPU information

    Note:
        Falls back to generous defaults if psutil is unavailable,
        which will recommend the full-featured Jina model.
    """
    gpu = detect_gpu_resources()

    try:
        import psutil

        mem = psutil.virtual_memory()
        return SystemResources(
            available_ram_gb=mem.available / (1024**3),
            total_ram_gb=mem.total / (1024**3),
            gpu=gpu,
        )
    except ImportError:
        # psutil not available - return generous defaults
        # Assume 8GB available to recommend full-featured model
        # This avoids prompting users when we can't detect hardware
        return SystemResources(
            available_ram_gb=8.0,
            total_ram_gb=16.0,
            gpu=gpu,
        )


def recommend_model(resources: SystemResources | None = None) -> str:
    """Recommend an embedding model based on system resources.

    Uses the minimum of available RAM and GPU VRAM (if GPU detected) to
    determine the appropriate model. This ensures the model fits in both
    system memory and GPU memory.

    Args:
        resources: System resources (auto-detected if None)

    Returns:
        Recommended model preset name
    """
    if resources is None:
        resources = detect_system_resources()

    available_gb = resources.available_ram_gb

    # If GPU is available, use the minimum of RAM and VRAM
    # This ensures we don't recommend a model that won't fit in GPU memory
    if resources.gpu is not None:
        available_gb = min(available_gb, resources.gpu.free_vram_gb)

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
    available_ram_gb = resources.available_ram_gb
    ram_str = f"{available_ram_gb:.1f}GB"

    # Check if VRAM is the limiting factor
    vram_limited = False
    if resources.gpu is not None:
        vram_gb = resources.gpu.free_vram_gb
        if vram_gb < available_ram_gb:
            vram_limited = True
            vram_str = f"{vram_gb:.1f}GB"

    if model == "jina-code-v2":
        return f"Available RAM ({ram_str}) supports the full-featured model"
    elif model == "bge-small":
        if vram_limited:
            return f"GPU VRAM ({vram_str}) is limited; using compact model for stability"
        return f"Available RAM ({ram_str}) is below 4GB; using compact model for better stability"
    else:  # minilm
        if vram_limited:
            return f"GPU VRAM ({vram_str}) is very limited; using lightweight model"
        return f"Available RAM ({ram_str}) is limited; using lightweight model"
