"""Domain value objects with validation.

Value objects that provide validation at construction time,
ensuring invalid states are unrepresentable.
"""

import fnmatch
import re
from dataclasses import dataclass
from datetime import UTC, datetime

# Supported language codes from file_preprocessor.py
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({
    "py", "ts", "js", "go", "rs", "java", "c", "cpp", "cs",
    "rb", "php", "swift", "sh", "vue", "svelte", "sql", "proto",
    "graphql", "txt",
})


@dataclass(frozen=True)
class PathFilter:
    """Validated glob pattern for path filtering.

    Ensures the glob pattern is syntactically valid at construction time.

    Attributes:
        pattern: The glob pattern string.

    Raises:
        ValueError: If pattern is empty or contains invalid glob syntax.
    """

    pattern: str

    def __post_init__(self) -> None:
        """Validate glob pattern syntax."""
        if not self.pattern:
            raise ValueError("PathFilter pattern cannot be empty")

        # Validate glob syntax by attempting to compile it
        # fnmatch.translate converts glob to regex - invalid patterns will fail
        try:
            fnmatch.translate(self.pattern)
        except Exception as e:
            raise ValueError(f"Invalid glob pattern '{self.pattern}': {e}") from e

        # Additional validation: check for obviously malformed patterns
        # Empty segments (e.g., "**//file.py") are suspicious
        if "//" in self.pattern and "://" not in self.pattern:
            raise ValueError(
                f"Invalid glob pattern '{self.pattern}': "
                "contains empty path segment (//)"
            )

    def matches(self, path: str) -> bool:
        """Check if a path matches this filter pattern.

        Args:
            path: The path to check.

        Returns:
            True if the path matches the pattern.
        """
        return fnmatch.fnmatch(path, self.pattern)

    def __str__(self) -> str:
        """Return the pattern string for use in queries."""
        return self.pattern


@dataclass(frozen=True)
class LanguageFilter:
    """Validated language code filter.

    Ensures the language code is one of the supported languages.

    Attributes:
        code: The language code (e.g., "py", "ts", "go").

    Raises:
        ValueError: If code is empty or not a supported language.
    """

    code: str

    def __post_init__(self) -> None:
        """Validate language code."""
        if not self.code:
            raise ValueError("LanguageFilter code cannot be empty")

        if self.code not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(
                f"Unknown language '{self.code}'. "
                f"Supported languages: {supported}"
            )

    def __str__(self) -> str:
        """Return the code string for use in queries."""
        return self.code


@dataclass(frozen=True)
class ISO8601Timestamp:
    """Validated and parsed ISO-8601 timestamp.

    Parses the timestamp once at construction, caching the datetime result.
    Handles both 'Z' suffix and explicit timezone offsets.

    Attributes:
        value: The parsed datetime object (always timezone-aware).
        raw: The original string representation.

    Raises:
        ValueError: If the string is not a valid ISO-8601 timestamp.
    """

    value: datetime
    raw: str

    # Regex for basic ISO-8601 datetime validation
    _PATTERN = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"  # Basic datetime
        r"(?:\.\d+)?"  # Optional fractional seconds
        r"(?:Z|[+-]\d{2}:\d{2})?$"  # Optional timezone
    )

    @classmethod
    def from_string(cls, timestamp_str: str) -> "ISO8601Timestamp":
        """Create an ISO8601Timestamp from a string.

        Args:
            timestamp_str: ISO-8601 formatted timestamp string.

        Returns:
            ISO8601Timestamp instance.

        Raises:
            ValueError: If the string is not a valid ISO-8601 timestamp.
        """
        if not timestamp_str:
            raise ValueError("Timestamp string cannot be empty")

        if not cls._PATTERN.match(timestamp_str):
            raise ValueError(
                f"Invalid ISO-8601 timestamp: '{timestamp_str}'. "
                "Expected format: YYYY-MM-DDTHH:MM:SS[.fff][Z|+HH:MM]"
            )

        # Parse the timestamp, handling 'Z' suffix
        parse_str = timestamp_str
        if parse_str.endswith("Z"):
            parse_str = parse_str[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(parse_str)
            # Ensure timezone-aware
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return cls(value=parsed, raw=timestamp_str)
        except ValueError as e:
            raise ValueError(
                f"Invalid ISO-8601 timestamp: '{timestamp_str}': {e}"
            ) from e

    @classmethod
    def now(cls) -> "ISO8601Timestamp":
        """Create a timestamp for the current UTC time.

        Returns:
            ISO8601Timestamp for now.
        """
        now = datetime.now(UTC)
        raw = now.isoformat()
        return cls(value=now, raw=raw)

    def is_older_than(self, seconds: int) -> bool:
        """Check if this timestamp is older than a given number of seconds.

        Args:
            seconds: Age threshold in seconds.

        Returns:
            True if the timestamp is more than `seconds` old.
        """
        now = datetime.now(UTC)
        age_seconds = (now - self.value).total_seconds()
        return age_seconds > seconds

    def __str__(self) -> str:
        """Return the raw timestamp string."""
        return self.raw
