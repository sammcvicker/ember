"""Human-friendly time formatting utilities."""

from datetime import UTC, datetime


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

    # Handle future timestamps (clock skew) gracefully
    if delta_seconds < 0:
        return "just now"

    # Less than 1 minute
    if delta_seconds < 60:
        return "just now"

    # Less than 1 hour
    minutes = int(delta_seconds // 60)
    if delta_seconds < 3600:
        if minutes == 1:
            return "1 min ago"
        return f"{minutes} min ago"

    # Less than 1 day
    hours = int(delta_seconds // 3600)
    if delta_seconds < 86400:
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"

    # Less than 1 week
    days = int(delta_seconds // 86400)
    if delta_seconds < 7 * 86400:
        if days == 1:
            return "1 day ago"
        return f"{days} days ago"

    # Less than 1 month (30 days)
    weeks = int(delta_seconds // (7 * 86400))
    if delta_seconds < 30 * 86400:
        if weeks == 1:
            return "1 week ago"
        return f"{weeks} weeks ago"

    # Months
    months = int(delta_seconds // (30 * 86400))
    if months == 1:
        return "1 month ago"
    return f"{months} months ago"
