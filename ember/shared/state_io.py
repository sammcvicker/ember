"""State file I/O utilities for reading and writing state.json.

This module handles serialization/deserialization of RepoState to/from JSON.
The state file tracks what has been indexed and enables incremental sync.
"""

import json
from datetime import UTC
from pathlib import Path

from ember.domain.entities import RepoState, SyncMode


def load_state(path: Path) -> RepoState:
    """Load repository state from state.json.

    Args:
        path: Path to state.json file

    Returns:
        Parsed RepoState instance

    Raises:
        FileNotFoundError: If state file doesn't exist
        ValueError: If state file is malformed
    """
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in state file: {e}") from e

    return RepoState(
        last_tree_sha=data["last_tree_sha"],
        last_sync_mode=data["last_sync_mode"],
        model_fingerprint=data["model_fingerprint"],
        version=data["version"],
        indexed_at=data["indexed_at"],
    )


def save_state(state: RepoState, path: Path) -> None:
    """Save repository state to state.json.

    Args:
        state: RepoState to save
        path: Destination path for state.json
    """
    # Convert SyncMode enum to string for JSON serialization
    sync_mode = state.last_sync_mode
    if isinstance(sync_mode, SyncMode):
        sync_mode = sync_mode.value

    data = {
        "last_tree_sha": state.last_tree_sha,
        "last_sync_mode": sync_mode,
        "model_fingerprint": state.model_fingerprint,
        "version": state.version,
        "indexed_at": state.indexed_at_str,
    }

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON with indentation for readability
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")  # Add trailing newline


def create_initial_state(path: Path, version: str = "0.1.0") -> None:
    """Create an initial state.json file for a new index.

    Args:
        path: Destination path for state.json
        version: Ember version string
    """
    from datetime import datetime

    state = RepoState(
        last_tree_sha="",
        last_sync_mode="none",
        model_fingerprint="",
        version=version,
        indexed_at=datetime.now(UTC).isoformat(),
    )

    save_state(state, path)
