"""Tests for domain value objects."""

from datetime import UTC, datetime, timedelta

import pytest

from ember.domain.value_objects import (
    SUPPORTED_LANGUAGES,
    ISO8601Timestamp,
    LanguageFilter,
    PathFilter,
)


class TestPathFilter:
    """Tests for PathFilter value object."""

    def test_valid_simple_pattern(self) -> None:
        """Test that simple patterns are accepted."""
        pf = PathFilter("*.py")
        assert pf.pattern == "*.py"
        assert str(pf) == "*.py"

    def test_valid_glob_patterns(self) -> None:
        """Test various valid glob patterns."""
        valid_patterns = [
            "*.py",
            "**/*.py",
            "src/*.ts",
            "tests/test_*.py",
            "src/**/test*.py",
            "file.txt",
            "[abc].py",
            "foo?bar.py",
        ]
        for pattern in valid_patterns:
            pf = PathFilter(pattern)
            assert pf.pattern == pattern

    def test_empty_pattern_raises(self) -> None:
        """Test that empty pattern raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PathFilter("")

    def test_double_slash_raises(self) -> None:
        """Test that double slashes (empty path segment) raise ValueError."""
        with pytest.raises(ValueError, match="empty path segment"):
            PathFilter("src//file.py")

    def test_url_with_double_slash_allowed(self) -> None:
        """Test that URLs with :// are allowed."""
        # This is an edge case - shouldn't happen in practice but shouldn't fail
        pf = PathFilter("http://*.example.com")
        assert pf.pattern == "http://*.example.com"

    def test_matches_positive(self) -> None:
        """Test that matches() returns True for matching paths."""
        pf = PathFilter("*.py")
        assert pf.matches("test.py")
        assert pf.matches("module.py")

    def test_matches_negative(self) -> None:
        """Test that matches() returns False for non-matching paths."""
        pf = PathFilter("*.py")
        assert not pf.matches("test.ts")
        # Note: fnmatch's * matches everything including /
        # This differs from shell glob behavior

    def test_matches_specific_dir(self) -> None:
        """Test matching with directory prefix."""
        pf = PathFilter("src/*.py")
        assert pf.matches("src/test.py")
        assert not pf.matches("test.py")
        assert not pf.matches("other/test.py")


class TestLanguageFilter:
    """Tests for LanguageFilter value object."""

    def test_valid_language_codes(self) -> None:
        """Test that all supported languages are accepted."""
        for lang in SUPPORTED_LANGUAGES:
            lf = LanguageFilter(lang)
            assert lf.code == lang
            assert str(lf) == lang

    def test_empty_code_raises(self) -> None:
        """Test that empty code raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            LanguageFilter("")

    def test_unknown_language_raises(self) -> None:
        """Test that unknown language codes raise ValueError."""
        with pytest.raises(ValueError, match="Unknown language"):
            LanguageFilter("cobol")

    def test_error_message_includes_supported(self) -> None:
        """Test that error message lists supported languages."""
        with pytest.raises(ValueError, match="Supported languages:"):
            LanguageFilter("invalid")


class TestISO8601Timestamp:
    """Tests for ISO8601Timestamp value object."""

    def test_parse_with_z_suffix(self) -> None:
        """Test parsing timestamp with Z suffix."""
        ts = ISO8601Timestamp.from_string("2024-01-15T10:30:00Z")
        assert ts.value.year == 2024
        assert ts.value.month == 1
        assert ts.value.day == 15
        assert ts.value.hour == 10
        assert ts.value.minute == 30
        assert ts.raw == "2024-01-15T10:30:00Z"

    def test_parse_with_offset(self) -> None:
        """Test parsing timestamp with explicit offset."""
        ts = ISO8601Timestamp.from_string("2024-01-15T10:30:00+05:00")
        assert ts.value.hour == 10
        assert str(ts.value.tzinfo) == "UTC+05:00"

    def test_parse_with_fractional_seconds(self) -> None:
        """Test parsing timestamp with fractional seconds."""
        ts = ISO8601Timestamp.from_string("2024-01-15T10:30:00.123456Z")
        assert ts.value.microsecond == 123456

    def test_parse_no_timezone(self) -> None:
        """Test parsing timestamp without timezone (assumes UTC)."""
        ts = ISO8601Timestamp.from_string("2024-01-15T10:30:00")
        assert ts.value.tzinfo is not None  # Should be UTC

    def test_empty_string_raises(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ISO8601Timestamp.from_string("")

    def test_invalid_format_raises(self) -> None:
        """Test that invalid formats raise ValueError."""
        invalid_timestamps = [
            "not-a-timestamp",
            "2024-01-15",  # Date only
            "10:30:00",  # Time only
            "2024/01/15T10:30:00Z",  # Wrong date separator
            "2024-01-15 10:30:00",  # Space instead of T
        ]
        for ts_str in invalid_timestamps:
            with pytest.raises(ValueError, match="Invalid ISO-8601"):
                ISO8601Timestamp.from_string(ts_str)

    def test_now_creates_current_time(self) -> None:
        """Test that now() creates a timestamp close to current time."""
        before = datetime.now(UTC)
        ts = ISO8601Timestamp.now()
        after = datetime.now(UTC)

        assert before <= ts.value <= after

    def test_is_older_than_positive(self) -> None:
        """Test is_older_than returns True for old timestamps."""
        old_time = datetime.now(UTC) - timedelta(hours=2)
        ts = ISO8601Timestamp(value=old_time, raw=old_time.isoformat())

        # Should be older than 1 hour
        assert ts.is_older_than(3600)

    def test_is_older_than_negative(self) -> None:
        """Test is_older_than returns False for recent timestamps."""
        ts = ISO8601Timestamp.now()

        # Should not be older than 1 hour
        assert not ts.is_older_than(3600)

    def test_str_returns_raw(self) -> None:
        """Test that str() returns the original raw string."""
        raw = "2024-01-15T10:30:00Z"
        ts = ISO8601Timestamp.from_string(raw)
        assert str(ts) == raw


class TestSupportedLanguages:
    """Tests for SUPPORTED_LANGUAGES constant."""

    def test_includes_common_languages(self) -> None:
        """Test that common languages are included."""
        common = ["py", "ts", "js", "go", "rs", "java"]
        for lang in common:
            assert lang in SUPPORTED_LANGUAGES

    def test_is_frozen(self) -> None:
        """Test that SUPPORTED_LANGUAGES is immutable."""
        assert isinstance(SUPPORTED_LANGUAGES, frozenset)
