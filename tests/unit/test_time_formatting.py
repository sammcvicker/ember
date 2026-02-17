"""Unit tests for human-friendly time formatting utilities."""

from datetime import UTC, datetime

import pytest

from ember.core.status.time_format import format_time_ago


class TestFormatTimeAgo:
    """Tests for format_time_ago function."""

    @pytest.mark.parametrize(
        "seconds_ago, expected",
        [
            pytest.param(5, "just now", id="5-seconds"),
            pytest.param(45, "just now", id="45-seconds"),
            pytest.param(60, "1 min ago", id="1-minute"),
            pytest.param(300, "5 min ago", id="5-minutes"),
            pytest.param(3600, "1 hour ago", id="1-hour"),
            pytest.param(7200, "2 hours ago", id="2-hours"),
            pytest.param(86400, "1 day ago", id="1-day"),
            pytest.param(172800, "2 days ago", id="2-days"),
            pytest.param(7 * 86400, "1 week ago", id="1-week"),
            pytest.param(14 * 86400, "2 weeks ago", id="2-weeks"),
            pytest.param(30 * 86400, "1 month ago", id="1-month"),
            pytest.param(60 * 86400, "2 months ago", id="2-months"),
        ],
    )
    def test_format_time_ago(self, seconds_ago: int, expected: str) -> None:
        """Test time formatting for various durations."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() - seconds_ago
        assert format_time_ago(timestamp) == expected

    def test_none_returns_none(self) -> None:
        """Test that None input returns None."""
        assert format_time_ago(None) is None

    def test_future_timestamp_shows_just_now(self) -> None:
        """Test that future timestamps (clock skew) show 'just now'."""
        now = datetime.now(UTC)
        timestamp = now.timestamp() + 60  # 1 minute in future
        assert format_time_ago(timestamp) == "just now"
