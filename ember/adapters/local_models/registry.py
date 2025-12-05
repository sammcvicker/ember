"""Model registry for embedding model selection.

Maps user-friendly preset names and HuggingFace model IDs to embedder classes.
Provides a factory function to create the appropriate embedder based on config.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


class Embedder(Protocol):
    """Embedder protocol for type checking."""

    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def fingerprint(self) -> str: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def ensure_loaded(self) -> None: ...


# Preset names map to HuggingFace model IDs
# Users can use either the preset name or the full HF ID
MODEL_PRESETS: dict[str, str] = {
    # Default code-optimized model (161M params, 768 dims, ~1.6GB)
    "jina-code-v2": "jinaai/jina-embeddings-v2-base-code",
    "local-default-code-embed": "jinaai/jina-embeddings-v2-base-code",  # Legacy name
    # Lightweight option (22M params, 384 dims, ~100MB)
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
    "all-minilm-l6-v2": "sentence-transformers/all-MiniLM-L6-v2",
    # Small retrieval-optimized (33M params, 384 dims, ~130MB)
    "bge-small": "BAAI/bge-small-en-v1.5",
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
}

# Special model name for auto-selection based on hardware
AUTO_MODEL = "auto"

# Full HuggingFace model IDs that we support directly
SUPPORTED_MODELS: set[str] = {
    "jinaai/jina-embeddings-v2-base-code",
    "sentence-transformers/all-MiniLM-L6-v2",
    "BAAI/bge-small-en-v1.5",
}

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
    # Resolve to canonical model ID
    resolved = DEFAULT_MODEL if model_name is None else resolve_model_name(model_name)

    # Create the appropriate embedder
    if resolved == "jinaai/jina-embeddings-v2-base-code":
        from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder

        kwargs: dict = {"batch_size": batch_size}
        if device is not None:
            kwargs["device"] = device
        if max_seq_length is not None:
            kwargs["max_seq_length"] = max_seq_length
        return JinaCodeEmbedder(**kwargs)

    elif resolved == "sentence-transformers/all-MiniLM-L6-v2":
        from ember.adapters.local_models.minilm_embedder import MiniLMEmbedder

        kwargs = {"batch_size": batch_size}
        if device is not None:
            kwargs["device"] = device
        if max_seq_length is not None:
            kwargs["max_seq_length"] = max_seq_length
        return MiniLMEmbedder(**kwargs)

    elif resolved == "BAAI/bge-small-en-v1.5":
        from ember.adapters.local_models.bge_embedder import BGESmallEmbedder

        kwargs = {"batch_size": batch_size}
        if device is not None:
            kwargs["device"] = device
        if max_seq_length is not None:
            kwargs["max_seq_length"] = max_seq_length
        return BGESmallEmbedder(**kwargs)

    else:
        # This shouldn't happen if resolve_model_name works correctly
        raise ValueError(f"No embedder implementation for model: {resolved}")


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

    info = {
        "name": resolved,
        "preset": model_name if model_name.lower() in MODEL_PRESETS else None,
    }

    if resolved == "jinaai/jina-embeddings-v2-base-code":
        info.update({
            "dim": 768,
            "params": "161M",
            "memory": "~1.6GB",
            "max_seq_length": 8192,
            "description": "Code-optimized model with excellent code understanding",
        })
    elif resolved == "sentence-transformers/all-MiniLM-L6-v2":
        info.update({
            "dim": 384,
            "params": "22M",
            "memory": "~100MB",
            "max_seq_length": 256,
            "description": "Lightweight general-purpose model, very fast",
        })
    elif resolved == "BAAI/bge-small-en-v1.5":
        info.update({
            "dim": 384,
            "params": "33M",
            "memory": "~130MB",
            "max_seq_length": 512,
            "description": "Small retrieval-optimized model, good accuracy",
        })

    return info


def list_available_models() -> list[dict]:
    """List all available models with their info.

    Returns:
        List of model info dictionaries
    """
    # Use unique resolved model names
    seen = set()
    models = []

    for preset in sorted(MODEL_PRESETS.keys()):
        resolved = MODEL_PRESETS[preset]
        if resolved not in seen:
            seen.add(resolved)
            info = get_model_info(preset)
            # Find all presets for this model
            presets = [p for p, r in MODEL_PRESETS.items() if r == resolved]
            info["presets"] = presets
            models.append(info)

    return models
