"""Presentation layer for CLI output formatting.

Components:
- ResultPresenter: Orchestrator for result display (main entry point)
- JsonResultFormatter: JSON serialization
- CompactPreviewRenderer: Compact previews without context
- ContextRenderer: Results with surrounding context lines
- ContextData, ContextLine: Shared context extraction utilities
"""

from ember.core.presentation.compact_renderer import CompactPreviewRenderer
from ember.core.presentation.context_renderer import ContextRenderer
from ember.core.presentation.context_utils import (
    ContextData,
    ContextLine,
    get_context_for_result,
)
from ember.core.presentation.json_formatter import JsonResultFormatter
from ember.core.presentation.result_presenter import ResultPresenter

__all__ = [
    "ResultPresenter",
    "JsonResultFormatter",
    "CompactPreviewRenderer",
    "ContextRenderer",
    "ContextData",
    "ContextLine",
    "get_context_for_result",
]
