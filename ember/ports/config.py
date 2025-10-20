"""Configuration provider port.

Defines the interface for loading and accessing application configuration.
"""

from pathlib import Path
from typing import Protocol

from ember.domain.config import EmberConfig


class ConfigProvider(Protocol):
    """Protocol for loading and providing configuration."""

    def load(self, ember_dir: Path) -> EmberConfig:
        """Load configuration from the ember directory.

        Args:
            ember_dir: Path to .ember directory containing config.toml

        Returns:
            EmberConfig instance with loaded or default values

        Note:
            Implementations should gracefully fall back to defaults
            if config file is missing or invalid.
        """
        ...
