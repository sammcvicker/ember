"""Configuration I/O utilities for reading and writing TOML config files.

This module handles serialization/deserialization of EmberConfig to/from TOML format.
"""

import os
import platform
import tomllib  # Built-in Python 3.11+
from pathlib import Path
from typing import Any

import tomli_w

from ember.domain.config import (
    DisplayConfig,
    EmberConfig,
    IndexConfig,
    ModelConfig,
    RedactionConfig,
    SearchConfig,
)


def get_global_config_path() -> Path:
    """Get the path to the global config file.

    The location is platform-dependent:
    - Linux/macOS: $XDG_CONFIG_HOME/ember/config.toml or ~/.config/ember/config.toml
    - Windows: %APPDATA%/ember/config.toml

    Returns:
        Path to the global config file (may not exist)
    """
    if platform.system() == "Windows":
        # Windows: use %APPDATA%
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "ember" / "config.toml"
        # Fallback to home directory
        return Path.home() / ".config" / "ember" / "config.toml"
    else:
        # Unix-like: respect XDG_CONFIG_HOME
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg_config:
            return Path(xdg_config) / "ember" / "config.toml"
        return Path.home() / ".config" / "ember" / "config.toml"


def load_config_data(path: Path) -> dict[str, Any]:
    """Load raw TOML data from a config file.

    Args:
        path: Path to config.toml file

    Returns:
        Dictionary with parsed TOML data

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is malformed
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in config file: {e}") from e


def merge_config_data(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge two config dictionaries, with override values taking precedence.

    Performs a shallow merge at the section level - if a section exists in override,
    its values completely replace the base section's values.

    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary (takes precedence)

    Returns:
        Merged configuration dictionary
    """
    result: dict[str, Any] = {}

    # Get all section names from both configs
    all_sections = set(base.keys()) | set(override.keys())

    for section in all_sections:
        base_section = base.get(section, {})
        override_section = override.get(section, {})

        if isinstance(base_section, dict) and isinstance(override_section, dict):
            # Merge section dictionaries - override values win
            merged_section = {**base_section, **override_section}
            result[section] = merged_section
        elif section in override:
            # Non-dict value from override wins
            result[section] = override_section
        else:
            # Use base value
            result[section] = base_section

    return result


def config_data_to_ember_config(data: dict[str, Any]) -> EmberConfig:
    """Convert raw config data dictionary to EmberConfig.

    Args:
        data: Dictionary with config sections

    Returns:
        EmberConfig instance
    """
    index_data = data.get("index", {})
    search_data = data.get("search", {})
    redaction_data = data.get("redaction", {})
    model_data = data.get("model", {})
    display_data = data.get("display", {})

    return EmberConfig(
        index=IndexConfig(**index_data),
        search=SearchConfig(**search_data),
        redaction=RedactionConfig(**redaction_data),
        model=ModelConfig(**model_data),
        display=DisplayConfig(**display_data),
    )


def load_config(path: Path) -> EmberConfig:
    """Load configuration from a TOML file.

    Args:
        path: Path to config.toml file

    Returns:
        Parsed EmberConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is malformed
    """
    data = load_config_data(path)
    return config_data_to_ember_config(data)


def save_config(config: EmberConfig, path: Path) -> None:
    """Save configuration to a TOML file.

    Args:
        config: EmberConfig to save
        path: Destination path for config.toml
    """
    # Convert dataclasses to dicts
    data: dict[str, Any] = {
        "index": {
            "model": config.index.model,
            "chunk": config.index.chunk,
            "line_window": config.index.line_window,
            "line_stride": config.index.line_stride,
            "overlap_lines": config.index.overlap_lines,
            "include": config.index.include,
            "ignore": config.index.ignore,
        },
        "search": {
            "topk": config.search.topk,
            "rerank": config.search.rerank,
            "filters": config.search.filters,
        },
        "redaction": {
            "patterns": config.redaction.patterns,
            "max_file_mb": config.redaction.max_file_mb,
        },
        "model": {
            "mode": config.model.mode,
            "daemon_timeout": config.model.daemon_timeout,
            "daemon_startup_timeout": config.model.daemon_startup_timeout,
        },
        "display": {
            "syntax_highlighting": config.display.syntax_highlighting,
            "color_scheme": config.display.color_scheme,
            "theme": config.display.theme,
        },
    }

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write TOML
    with path.open("wb") as f:
        tomli_w.dump(data, f)


def create_default_config_file(path: Path, model: str = "local-default-code-embed") -> None:
    """Create a default config.toml file with sensible defaults and comments.

    Args:
        path: Destination path for config.toml
        model: Embedding model preset to use (default: local-default-code-embed)
    """
    # We use a template string to preserve comments and formatting
    template = f"""\
# Ember Configuration
# Created by: ember init
# Documentation: https://github.com/kamiwaza-ai/ember

[index]
# Embedding model to use for vectorization
# Options: jina-code-v2 (best quality, ~1.6GB), bge-small (balanced, ~130MB),
#          minilm (lightweight, ~100MB), auto (detect hardware)
model = "{model}"

# Chunking strategy: "symbol" (tree-sitter) or "lines" (sliding window)
chunk = "symbol"

# Lines per chunk when using line-based chunking
line_window = 120

# Stride between chunks (line-based chunking)
line_stride = 100

# Overlap lines between chunks for context preservation
overlap_lines = 15

# File patterns to include (glob syntax)
include = [
    "**/*.py",
    "**/*.ts",
    "**/*.tsx",
    "**/*.js",
    "**/*.jsx",
    "**/*.go",
    "**/*.rs",
    "**/*.java",
    "**/*.cpp",
    "**/*.c",
    "**/*.h",
    "**/*.hpp",
]

# Patterns to ignore (respects .gitignore and .emberignore too)
ignore = [
    ".git/",
    "node_modules/",
    "dist/",
    "build/",
    "__pycache__/",
    ".venv/",
    "venv/",
    "*.pyc",
    ".DS_Store",
]

[search]
# Default number of results to return
topk = 20

# Enable cross-encoder reranking (more accurate but slower)
rerank = false

# Default filters to apply (key=value format)
filters = []

[redaction]
# Regex patterns to redact before embedding (prevents secrets in embeddings)
patterns = [
    "(?i)api_key\\\\s*[:=]\\\\s*['\\\"]?[A-Za-z0-9-_]{16,}",
    "(?i)secret\\\\s*[:=]\\\\s*['\\\"]?[A-Za-z0-9-_]{16,}",
    "(?i)password\\\\s*[:=]\\\\s*['\\\"]?[A-Za-z0-9-_]{8,}",
]

# Maximum file size to process (MB)
max_file_mb = 5
"""

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write template
    with path.open("w", encoding="utf-8") as f:
        f.write(template)
