"""Unit tests for human-friendly time formatting utilities."""

from datetime import UTC, datetime

from ember.core.status.time_format import format_time_ago


class TestFormatTimeAgo:
    """Tests for format_time_ago function."""

    def test_just_now_for_seconds(self) -> None:
        """Test that recent timestamps show 'just now'."""
        now = datetime.now(UTC)
        # 5 seconds ago
        timestamp = now.timestamp() - 5
        assert format_time_ago(timestamp) == "just now"

    def test_just_now_for_under_minute(self) -> None:
        """Test that timestamps under 1 minute show 'just now'."""
        now = datetime.now(UTC)
        # 45 seconds ago
        timestamp = now.timestamp() - 45
        assert format_time_ago(timestamp) == "just now"

    def test_one_minute_ago(self) -> None:
        """Test that 1 minute shows singular form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - 60
        assert format_time_ago(timestamp) == "1 min ago"

    def test_minutes_ago(self) -> None:
        """Test that multiple minutes show plural form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - 300  # 5 minutes
        assert format_time_ago(timestamp) == "5 min ago"

    def test_one_hour_ago(self) -> None:
        """Test that 1 hour shows singular form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - 3600  # 1 hour
        assert format_time_ago(timestamp) == "1 hour ago"

    def test_hours_ago(self) -> None:
        """Test that multiple hours show plural form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - 7200  # 2 hours
        assert format_time_ago(timestamp) == "2 hours ago"

    def test_one_day_ago(self) -> None:
        """Test that 1 day shows singular form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - 86400  # 1 day
        assert format_time_ago(timestamp) == "1 day ago"

    def test_days_ago(self) -> None:
        """Test that multiple days show plural form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - 172800  # 2 days
        assert format_time_ago(timestamp) == "2 days ago"

    def test_one_week_ago(self) -> None:
        """Test that 7+ days switches to weeks."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - (7 * 86400)  # 7 days
        assert format_time_ago(timestamp) == "1 week ago"

    def test_weeks_ago(self) -> None:
        """Test that multiple weeks show plural form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - (14 * 86400)  # 14 days
        assert format_time_ago(timestamp) == "2 weeks ago"

    def test_one_month_ago(self) -> None:
        """Test that 30+ days switches to months."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - (30 * 86400)  # 30 days
        assert format_time_ago(timestamp) == "1 month ago"

    def test_months_ago(self) -> None:
        """Test that multiple months show plural form."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - (60 * 86400)  # 60 days
        assert format_time_ago(timestamp) == "2 months ago"

    def test_none_returns_none(self) -> None:
        """Test that None input returns None."""
        assert format_time_ago(None) is None

    def test_future_timestamp_shows_just_now(self) -> None:
        """Test that future timestamps (clock skew) show 'just now'."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() + 60  # 1 minute in future
        assert format_time_ago(timestamp) == "just now"
