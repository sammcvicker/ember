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
    _validate_model_name,
    get_global_config_path,
    load_config_data,
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

        Uses domain-level merging via EmberConfig.from_partial to ensure
        validation happens at each merge step.

        Args:
            ember_dir: Path to .ember directory containing config.toml

        Returns:
            EmberConfig instance with merged global/local values or defaults
        """
        local_path = ember_dir / "config.toml"
        global_path = get_global_config_path()

        # Start with built-in defaults
        config = EmberConfig.default()

        # Apply global config overrides if exists
        if global_path.exists():
            try:
                global_data = load_config_data(global_path)
                config = EmberConfig.from_partial(config, global_data)
                logger.debug("Loaded global config from %s", global_path)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(
                    "Failed to parse global config at %s: %s. Ignoring global config.",
                    global_path,
                    e,
                )

        # Apply local config overrides if exists
        if local_path.exists():
            try:
                local_data = load_config_data(local_path)
                config = EmberConfig.from_partial(config, local_data)
                logger.debug("Loaded local config from %s", local_path)
            except (FileNotFoundError, ValueError) as e:
                logger.warning(
                    "Failed to parse config.toml: %s. Using global/default configuration.",
                    e,
                )

        # Validate model name at config boundary (adapter layer)
        # Model validation involves the registry (adapter), so it stays here
        try:
            _validate_model_name(config.index.model)
        except ValueError as e:
            logger.warning(
                "Invalid model configuration: %s. Using default model.",
                e,
            )
            return EmberConfig.default()

        return config
