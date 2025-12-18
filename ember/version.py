"""Version information for Ember.

This module provides a single source of truth for the package version,
reading from the installed package metadata (pyproject.toml).
"""

from importlib.metadata import version

__version__ = version("ember")
