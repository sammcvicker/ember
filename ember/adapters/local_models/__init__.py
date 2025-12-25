"""Local embedding model adapters.

Provides implementations of the Embedder protocol using local sentence-transformers
models with different size/performance tradeoffs.
"""

from ember.adapters.local_models.registry import (
    MODEL_PRESETS,
    SUPPORTED_MODELS,
    create_embedder,
    get_model_info,
    is_model_cached,
    list_available_models,
    resolve_model_name,
)

__all__ = [
    "MODEL_PRESETS",
    "SUPPORTED_MODELS",
    "create_embedder",
    "get_model_info",
    "is_model_cached",
    "list_available_models",
    "resolve_model_name",
]
