"""Human-friendly time formatting utilities."""

from datetime import UTC, datetime

# Each entry: (upper_threshold, divisor, singular_label, plural_label)
# Ordered from smallest to largest time unit.
# To add a new unit (e.g., "year"), append an entry at the end.
_TIME_UNITS: list[tuple[float, float, str, str]] = [
    (3_600, 60, "1 min ago", "{n} min ago"),
    (86_400, 3_600, "1 hour ago", "{n} hours ago"),
    (7 * 86_400, 86_400, "1 day ago", "{n} days ago"),
    (30 * 86_400, 7 * 86_400, "1 week ago", "{n} weeks ago"),
]

_FINAL_DIVISOR: float = 30 * 86_400
_FINAL_SINGULAR: str = "1 month ago"
_FINAL_PLURAL: str = "{n} months ago"


def _format_unit(value: int, singular: str, plural: str) -> str:
    """Return the singular label if value == 1, otherwise the plural with {n} replaced."""
    if value == 1:
        return singular
    return plural.format(n=value)


def format_time_ago(timestamp: float | None) -> str | None:
    """Format a Unix timestamp as a human-friendly relative time string.

    Examples:
        >>> format_time_ago(time.time() - 5)
        'just now'
        >>> format_time_ago(time.time() - 300)
        '5 min ago'
        >>> format_time_ago(time.time() - 7200)
        '2 hours ago'

    Args:
        timestamp: Unix timestamp (seconds since epoch) or None.

    Returns:
        Human-friendly string like "5 min ago" or None if timestamp is None.
    """
    if timestamp is None:
        return None

    now = datetime.now(UTC)
    then = datetime.fromtimestamp(timestamp, tz=UTC)
    delta_seconds = (now - then).total_seconds()

    # Handle future timestamps (clock skew) or very recent
    if delta_seconds < 60:
        return "just now"

    for upper_threshold, divisor, singular, plural in _TIME_UNITS:
        if delta_seconds < upper_threshold:
            value = int(delta_seconds // divisor)
            return _format_unit(value, singular, plural)

    # Largest unit (months) has no upper bound
    value = int(delta_seconds // _FINAL_DIVISOR)
    return _format_unit(value, _FINAL_SINGULAR, _FINAL_PLURAL)
