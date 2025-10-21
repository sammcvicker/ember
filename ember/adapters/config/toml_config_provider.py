"""TOML-based configuration provider.

Loads configuration from .ember/config.toml with graceful fallback to defaults.
"""

from pathlib import Path

from ember.domain.config import EmberConfig
from ember.shared.config_io import load_config


class TomlConfigProvider:
    """Configuration provider that loads from TOML files.

    Implements graceful degradation:
    - If config.toml exists and is valid, load it
    - If config.toml is missing or invalid, fall back to defaults
    - Partial configs are supported (missing sections use defaults)
    """

    def load(self, ember_dir: Path) -> EmberConfig:
        """Load configuration from ember directory.

        Args:
            ember_dir: Path to .ember directory containing config.toml

        Returns:
            EmberConfig instance with loaded or default values
        """
        config_path = ember_dir / "config.toml"

        # If config file doesn't exist, return defaults
        if not config_path.exists():
            return EmberConfig.default()

        # Try to load config, fall back to defaults on error
        try:
            return load_config(config_path)
        except (FileNotFoundError, ValueError):
            # Log warning but don't fail - use defaults
            # In the future, we could use a logger here
            return EmberConfig.default()
