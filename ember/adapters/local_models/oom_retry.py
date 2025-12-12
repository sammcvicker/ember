"""CUDA OOM retry logic for embedders.

Provides automatic batch size reduction when CUDA runs out of memory.
"""

import logging
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_cuda_oom_error(error: Exception) -> bool:
    """Check if an error is a CUDA out of memory error.

    Args:
        error: The exception to check

    Returns:
        True if this is a CUDA OOM error
    """
    error_msg = str(error).lower()
    return "cuda out of memory" in error_msg or "out of memory" in error_msg


def embed_with_oom_retry(
    encode_fn: Callable[[int], T],
    batch_size: int,
    min_batch_size: int = 1,
) -> T:
    """Execute embedding with automatic batch size reduction on CUDA OOM.

    When CUDA runs out of memory, this function:
    1. Clears the CUDA cache
    2. Halves the batch size
    3. Retries the operation
    4. Continues until success or batch_size reaches min_batch_size

    Args:
        encode_fn: Function that takes batch_size and returns embeddings
        batch_size: Initial batch size to try
        min_batch_size: Minimum batch size before giving up (default: 1)

    Returns:
        Result from encode_fn

    Raises:
        RuntimeError: If OOM occurs even at min_batch_size
    """
    current_batch_size = batch_size

    while True:
        try:
            return encode_fn(current_batch_size)
        except Exception as e:
            if not is_cuda_oom_error(e):
                # Not an OOM error, re-raise immediately
                raise

            # OOM error - try to recover
            if current_batch_size <= min_batch_size:
                # Already at minimum batch size, can't reduce further
                logger.error(
                    "CUDA out of memory at minimum batch size (%d). "
                    "Consider using a smaller model or switching to CPU.",
                    min_batch_size,
                )
                raise

            # Try to free GPU memory
            try:
                import torch

                torch.cuda.empty_cache()
            except (ImportError, RuntimeError):
                # torch not available or CUDA not initialized
                pass

            # Halve the batch size and retry
            new_batch_size = max(current_batch_size // 2, min_batch_size)
            logger.warning(
                "CUDA out of memory. Reducing batch size from %d to %d and retrying.",
                current_batch_size,
                new_batch_size,
            )
            current_batch_size = new_batch_size
