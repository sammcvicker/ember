"""Config domain models for ember.

Configuration is stored in .ember/config.toml and represents user preferences
for indexing, search, and redaction behavior. This module defines the domain
models that represent validated configuration state.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class IndexConfig:
    """Configuration for indexing behavior.

    Attributes:
        model: Embedding model name (e.g., "local-default-code-embed")
        chunk: Chunking strategy - "symbol" for tree-sitter, "lines" for sliding window
        line_window: Lines per chunk when using line-based chunking
        line_stride: Stride between chunks when using line-based chunking
        overlap_lines: Overlap lines between chunks for context preservation
        batch_size: Batch size for embedding (default: 32). Lower values use less
                   GPU memory. Will be automatically reduced on CUDA OOM errors.
        include: Glob patterns for files to include (e.g., ["**/*.py"])
        ignore: Patterns for files/dirs to ignore (e.g., ["node_modules/"])

    Raises:
        ValueError: If line_window, line_stride are not positive,
                   overlap_lines is negative, or overlap_lines >= line_window.
    """

    model: str = "local-default-code-embed"
    chunk: Literal["symbol", "lines"] = "symbol"
    line_window: int = 120
    line_stride: int = 100
    overlap_lines: int = 15
    batch_size: int = 32
    include: list[str] = field(
        default_factory=lambda: [
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
    )
    ignore: list[str] = field(
        default_factory=lambda: [
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
    )

    def __post_init__(self) -> None:
        """Validate index config after initialization."""
        if self.line_window <= 0:
            raise ValueError(f"line_window must be positive, got {self.line_window}")
        if self.line_stride <= 0:
            raise ValueError(f"line_stride must be positive, got {self.line_stride}")
        if self.overlap_lines < 0:
            raise ValueError(
                f"overlap_lines cannot be negative, got {self.overlap_lines}"
            )
        if self.overlap_lines >= self.line_window:
            raise ValueError(
                f"overlap_lines ({self.overlap_lines}) must be less than "
                f"line_window ({self.line_window})"
            )
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")


@dataclass(frozen=True)
class SearchConfig:
    """Configuration for search behavior.

    Attributes:
        topk: Default number of results to return
        rerank: Whether to enable cross-encoder reranking
        filters: Default filters to apply (key=value pairs)

    Raises:
        ValueError: If topk is not positive.
    """

    topk: int = 20
    rerank: bool = False
    filters: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate search config after initialization."""
        if self.topk <= 0:
            raise ValueError(f"topk must be positive, got {self.topk}")


@dataclass(frozen=True)
class RedactionConfig:
    """Configuration for content redaction.

    Attributes:
        patterns: Regex patterns to redact before embedding (e.g., API keys)
        max_file_mb: Maximum file size to process (in megabytes)

    Raises:
        ValueError: If max_file_mb is not positive.
    """

    patterns: list[str] = field(
        default_factory=lambda: [
            r"(?i)api_key\s*[:=]\s*['\"]?[A-Za-z0-9-_]{16,}",
            r"(?i)secret\s*[:=]\s*['\"]?[A-Za-z0-9-_]{16,}",
            r"(?i)password\s*[:=]\s*['\"]?[A-Za-z0-9-_]{8,}",
        ]
    )
    max_file_mb: int = 5

    def __post_init__(self) -> None:
        """Validate redaction config after initialization."""
        if self.max_file_mb <= 0:
            raise ValueError(f"max_file_mb must be positive, got {self.max_file_mb}")


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for embedding model and daemon.

    Attributes:
        mode: Model loading mode - "daemon" (default) or "direct"
        daemon_timeout: Idle timeout for daemon in seconds (default: 900 = 15 min)
        daemon_startup_timeout: Max seconds to wait for daemon startup (default: 5)

    Raises:
        ValueError: If daemon_timeout or daemon_startup_timeout is not positive.
    """

    mode: Literal["daemon", "direct"] = "daemon"
    daemon_timeout: int = 900  # 15 minutes
    daemon_startup_timeout: int = 5

    def __post_init__(self) -> None:
        """Validate model config after initialization."""
        if self.daemon_timeout <= 0:
            raise ValueError(
                f"daemon_timeout must be positive, got {self.daemon_timeout}"
            )
        if self.daemon_startup_timeout <= 0:
            raise ValueError(
                f"daemon_startup_timeout must be positive, "
                f"got {self.daemon_startup_timeout}"
            )


@dataclass(frozen=True)
class DisplayConfig:
    """Configuration for output display and formatting.

    Attributes:
        syntax_highlighting: Enable syntax highlighting for code excerpts (default: True)
        color_scheme: Color output mode - "auto" (default), "always", or "never"
        theme: Syntax highlighting theme (default: "ansi" for terminal colors)
              Use "ansi" to respect terminal color scheme, or specific theme names
              like "monokai", "github-dark", etc. for fixed colors
    """

    syntax_highlighting: bool = True
    color_scheme: Literal["auto", "always", "never"] = "auto"
    theme: str = "ansi"


@dataclass(frozen=True)
class EmberConfig:
    """Complete ember configuration.

    This represents the entire configuration state for an ember index.
    Typically loaded from .ember/config.toml and used throughout the application.

    Attributes:
        index: Indexing configuration
        search: Search configuration
        redaction: Redaction configuration
        model: Model and daemon configuration
        display: Display and formatting configuration
    """

    index: IndexConfig = field(default_factory=IndexConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    redaction: RedactionConfig = field(default_factory=RedactionConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)

    @staticmethod
    def default() -> "EmberConfig":
        """Create a config with all default values."""
        return EmberConfig(
            index=IndexConfig(),
            search=SearchConfig(),
            redaction=RedactionConfig(),
            model=ModelConfig(),
            display=DisplayConfig(),
        )
