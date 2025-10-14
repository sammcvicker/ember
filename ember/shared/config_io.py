"""Configuration I/O utilities for reading and writing TOML config files.

This module handles serialization/deserialization of EmberConfig to/from TOML format.
"""

import tomllib  # Built-in Python 3.11+
from pathlib import Path
from typing import Any

import tomli_w

from ember.domain.config import EmberConfig, IndexConfig, RedactionConfig, SearchConfig


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
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in config file: {e}") from e

    # Parse sections with defaults
    index_data = data.get("index", {})
    search_data = data.get("search", {})
    redaction_data = data.get("redaction", {})

    return EmberConfig(
        index=IndexConfig(**index_data),
        search=SearchConfig(**search_data),
        redaction=RedactionConfig(**redaction_data),
    )


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
    }

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write TOML
    with path.open("wb") as f:
        tomli_w.dump(data, f)


def create_default_config_file(path: Path) -> None:
    """Create a default config.toml file with sensible defaults and comments.

    Args:
        path: Destination path for config.toml
    """
    # We use a template string to preserve comments and formatting
    template = """\
# Ember Configuration
# Created by: ember init
# Documentation: https://github.com/kamiwaza-ai/ember

[index]
# Embedding model to use for vectorization
model = "local-default-code-embed"

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
