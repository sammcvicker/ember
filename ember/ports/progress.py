"""Progress reporting protocol for long-running operations.

Defines callback interface for reporting progress during indexing and other operations.
"""

from typing import Protocol


class ProgressCallback(Protocol):
    """Protocol for progress reporting callbacks.

    Implementations can use this to provide visual progress feedback during operations
    like indexing, without the core use cases depending on specific UI libraries.
    """

    def on_start(self, total: int, description: str) -> None:
        """Called when an operation starts.

        Args:
            total: Total number of items to process.
            description: Description of the operation.
        """
        ...

    def on_progress(self, current: int, item_description: str | None = None) -> None:
        """Called as progress is made.

        Args:
            current: Current item index (1-based).
            item_description: Optional description of current item being processed.
        """
        ...

    def on_complete(self) -> None:
        """Called when the operation completes."""
        ...
