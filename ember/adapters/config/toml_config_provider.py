"""TOML-based configuration provider.

Loads configuration from .ember/config.toml with global config fallback.

Config loading priority (highest to lowest):
1. Local: .ember/config.toml (repo-specific)
2. Global: ~/.config/ember/config.toml (user defaults)
3. Built-in defaults
"""

import logging
from pathlib import Path

from ember.domain.config import EmberConfig
from ember.shared.config_io import (
    config_data_to_ember_config,
    get_global_config_path,
    load_config_data,
    merge_config_data,
)

logger = logging.getLogger(__name__)


class TomlConfigProvider:
    """Configuration provider that loads from TOML files.

    Implements config cascade:
    1. Load global config (~/.config/ember/config.toml) if present
    2. Load local config (.ember/config.toml) if present
    3. Local values override global values (section-level merge)
    4. Missing values fall back to built-in defaults

    Gracefully handles missing or invalid configs with warnings.
    """

    def load(self, ember_dir: Path) -> EmberConfig:
        """Load configuration with global fallback.

        Args:
            ember_dir: Path to .ember directory containing config.toml

        Returns:
            EmberConfig instance with merged global/local values or defaults
        """
        local_path = ember_dir / "config.toml"
        global_path = get_global_config_path()

        # Start with empty data (defaults will be applied by dataclasses)
        merged_data: dict = {}

        # Load global config if exists
        if global_path.exists():
            try:
                global_data = load_config_data(global_path)
                merged_data = global_data
                logger.debug("Loaded global config from %s", global_path)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(
                    "Failed to parse global config at %s: %s. Ignoring global config.",
                    global_path,
                    e,
                )

        # Load and merge local config if exists
        if local_path.exists():
            try:
                local_data = load_config_data(local_path)
                merged_data = merge_config_data(merged_data, local_data)
                logger.debug("Loaded local config from %s", local_path)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(
                    "Failed to parse config.toml: %s. Using global/default configuration.",
                    e,
                )

        # If no config was loaded, return defaults
        if not merged_data:
            return EmberConfig.default()

        # Convert merged data to EmberConfig
        try:
            return config_data_to_ember_config(merged_data)
        except (TypeError, ValueError) as e:
            logger.warning(
                "Invalid config values: %s. Using default configuration.",
                e,
            )
            return EmberConfig.default()
