"""Config domain models for ember.

Configuration is stored in .ember/config.toml and represents user preferences
for indexing, search, and redaction behavior. This module defines the domain
models that represent validated configuration state.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pygments.styles import get_all_styles

from ember.domain.value_objects import PathFilter

# Valid Pygments themes plus "ansi" for terminal-native colors
VALID_THEMES: frozenset[str] = frozenset(get_all_styles()) | {"ansi"}


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
                   line_stride > line_window, overlap_lines is negative,
                   or overlap_lines >= line_window.
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
        if self.line_stride > self.line_window:
            raise ValueError(
                f"line_stride ({self.line_stride}) cannot exceed "
                f"line_window ({self.line_window})"
            )
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

        # Validate glob patterns early to fail fast
        for pattern in self.include:
            try:
                PathFilter(pattern)
            except ValueError as e:
                raise ValueError(f"Invalid glob in include: {e}") from e

        for pattern in self.ignore:
            try:
                PathFilter(pattern)
            except ValueError as e:
                raise ValueError(f"Invalid glob in ignore: {e}") from e

    @staticmethod
    def from_partial(
        base: "IndexConfig", partial: dict
    ) -> "IndexConfig":
        """Create IndexConfig from base config with partial overrides.

        Args:
            base: Base config providing defaults
            partial: Dict with override values (only provided keys override)

        Returns:
            New IndexConfig with merged values (validated on creation)
        """
        return IndexConfig(
            model=partial.get("model", base.model),
            chunk=partial.get("chunk", base.chunk),
            line_window=partial.get("line_window", base.line_window),
            line_stride=partial.get("line_stride", base.line_stride),
            overlap_lines=partial.get("overlap_lines", base.overlap_lines),
            batch_size=partial.get("batch_size", base.batch_size),
            include=partial.get("include", base.include),
            ignore=partial.get("ignore", base.ignore),
        )


@dataclass(frozen=True)
class SearchConfig:
    """Configuration for search behavior.

    Attributes:
        topk: Default number of results to return
        rerank: Whether to enable cross-encoder reranking
        filters: Default filters to apply (key=value pairs)
        rrf_k: Reciprocal Rank Fusion constant (default 60). Higher values
               reduce influence of top-ranked items in fusion scoring.
        retrieval_pool_multiplier: Multiplier for retrieval pool size vs topk
               (default 5). Higher values = better fusion quality, slower retrieval.
        min_retrieval_pool: Minimum retrieval pool size (default 100).
               Ensures enough candidates for fusion even with small topk.

    Raises:
        ValueError: If topk, rrf_k, retrieval_pool_multiplier, or
                   min_retrieval_pool is not positive.
    """

    topk: int = 20
    rerank: bool = False
    filters: list[str] = field(default_factory=list)
    rrf_k: int = 60
    retrieval_pool_multiplier: int = 5
    min_retrieval_pool: int = 100

    def __post_init__(self) -> None:
        """Validate search config after initialization."""
        if self.topk <= 0:
            raise ValueError(f"topk must be positive, got {self.topk}")
        if self.rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {self.rrf_k}")
        if self.retrieval_pool_multiplier <= 0:
            raise ValueError(
                f"retrieval_pool_multiplier must be positive, "
                f"got {self.retrieval_pool_multiplier}"
            )
        if self.min_retrieval_pool <= 0:
            raise ValueError(
                f"min_retrieval_pool must be positive, got {self.min_retrieval_pool}"
            )

    @staticmethod
    def from_partial(base: "SearchConfig", partial: dict) -> "SearchConfig":
        """Create SearchConfig from base config with partial overrides.

        Args:
            base: Base config providing defaults
            partial: Dict with override values (only provided keys override)

        Returns:
            New SearchConfig with merged values (validated on creation)
        """
        return SearchConfig(
            topk=partial.get("topk", base.topk),
            rerank=partial.get("rerank", base.rerank),
            filters=partial.get("filters", base.filters),
            rrf_k=partial.get("rrf_k", base.rrf_k),
            retrieval_pool_multiplier=partial.get(
                "retrieval_pool_multiplier", base.retrieval_pool_multiplier
            ),
            min_retrieval_pool=partial.get(
                "min_retrieval_pool", base.min_retrieval_pool
            ),
        )


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

        # Validate regex patterns compile
        for pattern in self.patterns:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e

    @staticmethod
    def from_partial(base: "RedactionConfig", partial: dict) -> "RedactionConfig":
        """Create RedactionConfig from base config with partial overrides.

        Args:
            base: Base config providing defaults
            partial: Dict with override values (only provided keys override)

        Returns:
            New RedactionConfig with merged values (validated on creation)
        """
        return RedactionConfig(
            patterns=partial.get("patterns", base.patterns),
            max_file_mb=partial.get("max_file_mb", base.max_file_mb),
        )


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

    @staticmethod
    def from_partial(base: "ModelConfig", partial: dict) -> "ModelConfig":
        """Create ModelConfig from base config with partial overrides.

        Args:
            base: Base config providing defaults
            partial: Dict with override values (only provided keys override)

        Returns:
            New ModelConfig with merged values (validated on creation)
        """
        return ModelConfig(
            mode=partial.get("mode", base.mode),
            daemon_timeout=partial.get("daemon_timeout", base.daemon_timeout),
            daemon_startup_timeout=partial.get(
                "daemon_startup_timeout", base.daemon_startup_timeout
            ),
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

    Raises:
        ValueError: If theme is not a valid Pygments theme or "ansi".
    """

    syntax_highlighting: bool = True
    color_scheme: Literal["auto", "always", "never"] = "auto"
    theme: str = "ansi"

    def __post_init__(self) -> None:
        """Validate display config after initialization."""
        if self.theme not in VALID_THEMES:
            raise ValueError(
                f"Unknown theme '{self.theme}'. Valid themes: ansi, monokai, "
                f"github-dark, dracula, solarized-dark, etc."
            )

    @staticmethod
    def from_partial(base: "DisplayConfig", partial: dict) -> "DisplayConfig":
        """Create DisplayConfig from base config with partial overrides.

        Args:
            base: Base config providing defaults
            partial: Dict with override values (only provided keys override)

        Returns:
            New DisplayConfig with merged values
        """
        return DisplayConfig(
            syntax_highlighting=partial.get(
                "syntax_highlighting", base.syntax_highlighting
            ),
            color_scheme=partial.get("color_scheme", base.color_scheme),
            theme=partial.get("theme", base.theme),
        )


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

    @staticmethod
    def from_partial(
        base: "EmberConfig", data: dict
    ) -> "EmberConfig":
        """Create EmberConfig from base config with partial overrides.

        Merges partial config data onto a base config. Only keys present in
        the data dict override the base values. Validation is performed on
        the resulting config.

        Args:
            base: Base config providing defaults for missing values
            data: Dict with section keys (index, search, etc.) containing
                  partial override values

        Returns:
            New EmberConfig with merged values (validated on creation)

        Example:
            >>> base = EmberConfig.default()
            >>> override_data = {"index": {"model": "minilm"}, "search": {"topk": 50}}
            >>> merged = EmberConfig.from_partial(base, override_data)
        """
        return EmberConfig(
            index=IndexConfig.from_partial(base.index, data.get("index", {})),
            search=SearchConfig.from_partial(base.search, data.get("search", {})),
            redaction=RedactionConfig.from_partial(
                base.redaction, data.get("redaction", {})
            ),
            model=ModelConfig.from_partial(base.model, data.get("model", {})),
            display=DisplayConfig.from_partial(base.display, data.get("display", {})),
        )
