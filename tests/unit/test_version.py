"""Tests for ember.version module."""

import re

from ember.version import __version__


class TestVersion:
    """Tests for version constant."""

    def test_version_is_string(self) -> None:
        """Version should be a string."""
        assert isinstance(__version__, str)

    def test_version_matches_semver_pattern(self) -> None:
        """Version should follow semantic versioning pattern."""
        # Pattern: major.minor.patch with optional pre-release/build metadata
        semver_pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$"
        assert re.match(
            semver_pattern, __version__
        ), f"Version '{__version__}' does not match semver pattern"

    def test_version_not_empty(self) -> None:
        """Version should not be empty."""
        assert __version__
        assert len(__version__) > 0
