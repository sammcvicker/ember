"""Port interface for daemon management.

Defines protocols for managing daemon lifecycle.
"""

from typing import Protocol


class DaemonManager(Protocol):
    """Protocol for managing daemon lifecycle.

    This protocol defines the interface for managing a background daemon process
    that keeps models loaded in memory for fast operations.
    """

    def is_running(self) -> bool:
        """Check if daemon is running and healthy.

        Returns:
            True if daemon is running and responding to health checks
        """
        ...

    def ensure_running(self, wait: bool = True) -> bool:
        """Ensure daemon is running, starting if needed.

        This is the primary method for auto-starting the daemon when needed.

        Args:
            wait: Wait for daemon to be ready

        Returns:
            True if daemon is running (or successfully started)
        """
        ...

    def start(self, foreground: bool = False) -> bool:
        """Start the daemon.

        Args:
            foreground: Run in foreground (for debugging)

        Returns:
            True if started successfully

        Raises:
            RuntimeError: If start fails
        """
        ...

    def stop(self, timeout: int = 10) -> bool:
        """Stop the daemon gracefully.

        Args:
            timeout: Seconds to wait for graceful shutdown

        Returns:
            True if stopped successfully
        """
        ...
