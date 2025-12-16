"""CLI utility functions for command-line interface.

This module serves as a facade re-exporting utilities from focused modules:
- errors: EmberCliError and error factory functions
- path_utils: Path normalization utilities
- editor: Editor integration for opening files
- progress: Progress bar and callback utilities
- result_lookup: Cache/hash lookups
- result_display: Content display with formatting

For new code, prefer importing directly from the focused modules.
"""

# Re-export editor integration
from ember.core.editor import (
    EDITOR_PATTERNS,
    get_editor,
    get_editor_command,
    open_file_in_editor,
)

# Re-export error handling
from ember.core.errors import (
    EmberCliError,
    index_out_of_range_error,
    no_search_results_error,
    path_not_in_repo_error,
    repo_not_found_error,
)

# Re-export path utilities
from ember.core.path_utils import normalize_path_filter

# Re-export highlight_symbol for backward compatibility
from ember.core.presentation.colors import highlight_symbol

# Re-export progress utilities
from ember.core.progress import (
    RichProgressCallback,
    ensure_daemon_with_progress,
    progress_context,
)

# Re-export result display
from ember.core.result_display import (
    display_content_with_context,
    display_content_with_highlighting,
    format_result_header,
)

# Re-export result lookup
from ember.core.result_lookup import (
    load_cached_results,
    lookup_result_by_hash,
    lookup_result_from_cache,
    validate_result_index,
)

__all__ = [
    # Errors
    "EmberCliError",
    "repo_not_found_error",
    "no_search_results_error",
    "path_not_in_repo_error",
    "index_out_of_range_error",
    # Path utilities
    "normalize_path_filter",
    # Editor integration
    "get_editor",
    "get_editor_command",
    "open_file_in_editor",
    "EDITOR_PATTERNS",
    # Progress utilities
    "RichProgressCallback",
    "progress_context",
    "ensure_daemon_with_progress",
    # Result lookup and display
    "load_cached_results",
    "validate_result_index",
    "format_result_header",
    "lookup_result_from_cache",
    "lookup_result_by_hash",
    "display_content_with_context",
    "display_content_with_highlighting",
    # Colors (backward compatibility)
    "highlight_symbol",
]
