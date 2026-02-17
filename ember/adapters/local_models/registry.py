"""Model registry for embedding model selection.

Maps user-friendly preset names and HuggingFace model IDs to embedder classes.
Provides a factory function to create the appropriate embedder based on config.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from ember.ports.embedders import Embedder

# Import try_to_load_from_cache at module level for easier mocking in tests
try:
    from huggingface_hub import try_to_load_from_cache
except ImportError:
    try_to_load_from_cache = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class ModelSpec:
    """Single source of truth for model metadata.

    All model information is defined here once and derived elsewhere.
    """

    id: str
    presets: tuple[str, ...]
    dim: int
    params: str
    memory: str
    max_seq_length: int
    description: str


# Single source of truth for all supported models
MODEL_REGISTRY: dict[str, ModelSpec] = {
    "jinaai/jina-embeddings-v2-base-code": ModelSpec(
        id="jinaai/jina-embeddings-v2-base-code",
        presets=("jina-code-v2", "local-default-code-embed"),
        dim=768,
        params="161M",
        memory="~1.6GB",
        max_seq_length=8192,
        description="Code-optimized model with excellent code understanding",
    ),
    "sentence-transformers/all-MiniLM-L6-v2": ModelSpec(
        id="sentence-transformers/all-MiniLM-L6-v2",
        presets=("minilm", "all-minilm-l6-v2"),
        dim=384,
        params="22M",
        memory="~100MB",
        max_seq_length=256,
        description="Lightweight general-purpose model, very fast",
    ),
    "BAAI/bge-small-en-v1.5": ModelSpec(
        id="BAAI/bge-small-en-v1.5",
        presets=("bge-small", "bge-small-en-v1.5"),
        dim=384,
        params="33M",
        memory="~130MB",
        max_seq_length=512,
        description="Small retrieval-optimized model, good accuracy",
    ),
}

# Derived from MODEL_REGISTRY - preset names map to HuggingFace model IDs
MODEL_PRESETS: dict[str, str] = {
    preset: spec.id for spec in MODEL_REGISTRY.values() for preset in spec.presets
}

# Special model name for auto-selection based on hardware
AUTO_MODEL = "auto"

# Derived from MODEL_REGISTRY - full HuggingFace model IDs that we support
SUPPORTED_MODELS: set[str] = set(MODEL_REGISTRY.keys())

# Default model when none specified
DEFAULT_MODEL = "jinaai/jina-embeddings-v2-base-code"


def resolve_model_name(model_name: str) -> str:
    """Resolve a model name to its canonical HuggingFace ID.

    Args:
        model_name: User-provided model name (preset, HF ID, or "auto")

    Returns:
        Canonical HuggingFace model ID

    Raises:
        ValueError: If model name is not recognized
    """
    # Normalize case for preset lookup
    normalized = model_name.lower()

    # Handle "auto" - detect hardware and pick best model
    if normalized == AUTO_MODEL:
        from ember.core.hardware import recommend_model

        recommended = recommend_model()
        return MODEL_PRESETS[recommended]

    # Check if it's a preset
    if normalized in MODEL_PRESETS:
        return MODEL_PRESETS[normalized]

    # Check if it's a supported full model ID (case-sensitive)
    if model_name in SUPPORTED_MODELS:
        return model_name

    # Not recognized
    valid_options = sorted(set(MODEL_PRESETS.keys()) | SUPPORTED_MODELS | {AUTO_MODEL})
    raise ValueError(
        f"Unknown embedding model: '{model_name}'. "
        f"Valid options are: {', '.join(valid_options)}"
    )


def _build_embedder_kwargs(
    batch_size: int,
    device: str | None,
    max_seq_length: int | None,
) -> dict:
    """Build kwargs dict for embedder constructor.

    Only includes optional parameters when they are not None.

    Args:
        batch_size: Batch size for encoding (always included)
        device: Device to run on (included if not None)
        max_seq_length: Maximum sequence length (included if not None)

    Returns:
        Dictionary of kwargs to pass to embedder constructor
    """
    kwargs: dict = {"batch_size": batch_size}
    if device is not None:
        kwargs["device"] = device
    if max_seq_length is not None:
        kwargs["max_seq_length"] = max_seq_length
    return kwargs


def _get_embedder_class(model_id: str) -> type:
    """Get the embedder class for a model ID.

    Uses late imports to avoid loading all embedder dependencies upfront.

    Args:
        model_id: Canonical HuggingFace model ID

    Returns:
        Embedder class (not instance)

    Raises:
        ValueError: If no embedder implementation exists for the model
    """
    if model_id == "jinaai/jina-embeddings-v2-base-code":
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        return JinaCodeEmbedder

    if model_id == "sentence-transformers/all-MiniLM-L6-v2":
        from ember.adapters.local_models.minilm_embedder import MiniLMEmbedder

        return MiniLMEmbedder

    if model_id == "BAAI/bge-small-en-v1.5":
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        return BGESmallEmbedder

    raise ValueError(f"No embedder implementation for model: {model_id}")


def create_embedder(
    model_name: str | None = None,
    max_seq_length: int | None = None,
    batch_size: int = 32,
    device: str | None = None,
) -> Embedder:
    """Create an embedder instance based on model name.

    Args:
        model_name: Model preset name or HuggingFace ID (default: jina-code-v2)
        max_seq_length: Maximum sequence length (default: model-specific)
        batch_size: Batch size for encoding
        device: Device to run on ('cpu', 'cuda', 'mps', or None for auto)

    Returns:
        Embedder instance implementing the Embedder protocol

    Raises:
        ValueError: If model name is not recognized
    """
    resolved = DEFAULT_MODEL if model_name is None else resolve_model_name(model_name)
    embedder_class = _get_embedder_class(resolved)
    kwargs = _build_embedder_kwargs(batch_size, device, max_seq_length)
    return embedder_class(**kwargs)


def get_model_info(model_name: str) -> dict:
    """Get information about a model.

    Args:
        model_name: Model preset name or HuggingFace ID

    Returns:
        Dictionary with model information

    Raises:
        ValueError: If model name is not recognized
    """
    resolved = resolve_model_name(model_name)
    spec = MODEL_REGISTRY[resolved]

    return {
        "name": resolved,
        "preset": model_name if model_name.lower() in MODEL_PRESETS else None,
        "dim": spec.dim,
        "params": spec.params,
        "memory": spec.memory,
        "max_seq_length": spec.max_seq_length,
        "description": spec.description,
    }


def list_available_models() -> list[dict]:
    """List all available models with their info.

    Returns:
        List of model info dictionaries
    """
    models = []
    for spec in MODEL_REGISTRY.values():
        models.append({
            "name": spec.id,
            "preset": spec.presets[0] if spec.presets else None,
            "dim": spec.dim,
            "params": spec.params,
            "memory": spec.memory,
            "max_seq_length": spec.max_seq_length,
            "description": spec.description,
            "presets": list(spec.presets),
        })
    return models


def _get_hf_cache_dir() -> Path:
    """Get the HuggingFace cache directory.

    Respects the HF_HOME and HUGGINGFACE_HUB_CACHE environment variables.

    Returns:
        Path to the HuggingFace hub cache directory.
    """
    # Check environment variables in order of precedence
    if "HUGGINGFACE_HUB_CACHE" in os.environ:
        return Path(os.environ["HUGGINGFACE_HUB_CACHE"])
    if "HF_HOME" in os.environ:
        return Path(os.environ["HF_HOME"]) / "hub"
    # Default location
    return Path.home() / ".cache" / "huggingface" / "hub"


def _check_cache_directory(model_id: str) -> bool:
    """Check if model is cached by inspecting cache directory structure.

    This is a fallback when huggingface_hub is not available or fails.
    HuggingFace stores models in a specific directory structure:
    ~/.cache/huggingface/hub/models--{org}--{model}/snapshots/{hash}/

    Args:
        model_id: Full HuggingFace model ID (e.g., "sentence-transformers/all-MiniLM-L6-v2")

    Returns:
        True if model appears to be cached (has snapshot directories with content).
    """
    cache_dir = _get_hf_cache_dir()

    # Convert model ID to cache directory name (slashes become double dashes)
    model_dir_name = f"models--{model_id.replace('/', '--')}"
    model_path = cache_dir / model_dir_name

    if not model_path.exists():
        return False

    # Check for snapshots directory with at least one snapshot
    snapshots_dir = model_path / "snapshots"
    if not snapshots_dir.exists():
        return False

    # Check if there's at least one snapshot directory
    try:
        return any(snapshots_dir.iterdir())
    except (OSError, PermissionError):
        return False


def is_model_cached(model_name: str) -> bool:
    """Check if a model is cached locally without loading it.

    Uses huggingface_hub's try_to_load_from_cache for fast cache inspection.
    Falls back to direct directory inspection if huggingface_hub is unavailable.

    This function is designed to be fast (<100ms) and never loads the model
    into memory, avoiding OOM issues on systems with limited memory.

    Args:
        model_name: Model preset name or HuggingFace ID

    Returns:
        True if model is cached locally, False if download would be needed.
    """
    resolved = resolve_model_name(model_name)

    # Primary method: use huggingface_hub cache inspection
    # This is fast and doesn't load the model
    if try_to_load_from_cache is not None:
        try:
            # Check for config.json - if this is cached, the model was downloaded
            # Returns file path (str) if cached, None or _CACHED_NO_EXIST otherwise
            result = try_to_load_from_cache(resolved, "config.json")
            return isinstance(result, str)
        except Exception:
            # Any error - fall back to directory check
            pass

    # Fallback: check cache directory structure directly
    # This works even if huggingface_hub is not available
    return _check_cache_directory(resolved)
