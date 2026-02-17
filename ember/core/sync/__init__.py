"""Sync module for coordinating index synchronization.

Contains the SyncService for checking staleness and executing sync operations,
with proper error classification.
"""

from ember.core.sync.sync_service import (
    SyncService,
    classify_sync_error,
    get_targeted_sync_hint,
)

__all__ = ["SyncService", "classify_sync_error", "get_targeted_sync_hint"]
