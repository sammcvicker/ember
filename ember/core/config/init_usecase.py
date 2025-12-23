"""Init use case for initializing a new ember index.

This use case handles the creation of a new .ember/ directory with all
necessary files: config.toml, index.db, and state.json.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from ember.core.use_case_errors import format_error_message, log_use_case_error
from ember.ports.database import DatabaseInitializer
from ember.shared.config_io import (
    create_global_config_file,
    create_minimal_project_config,
    get_global_config_path,
)
from ember.shared.state_io import create_initial_state

logger = logging.getLogger(__name__)


@dataclass
class InitRequest:
    """Request to initialize a new ember index.

    Attributes:
        repo_root: Absolute path to repository root (where .ember/ will be created)
        force: If True, reinitialize even if .ember/ already exists
        model: Embedding model preset to use (default: local-default-code-embed)
    """

    repo_root: Path
    force: bool = False
    model: str = "local-default-code-embed"


@dataclass
class InitResponse:
    """Response from init operation.

    Attributes:
        ember_dir: Path to created .ember/ directory (or None on failure).
        config_path: Path to created config.toml (or None on failure).
        db_path: Path to created index.db (or None on failure).
        state_path: Path to created state.json (or None on failure).
        was_reinitialized: True if existing .ember/ was replaced.
        global_config_created: True if global config was created (first run).
        global_config_path: Path to global config file (may or may not exist).
        success: Whether initialization succeeded.
        error: Error message if initialization failed.
        already_exists: True if failed because .ember/ already exists.
    """

    ember_dir: Path | None
    config_path: Path | None
    db_path: Path | None
    state_path: Path | None
    was_reinitialized: bool
    global_config_created: bool = False
    global_config_path: Path | None = None
    success: bool = True
    error: str | None = None
    already_exists: bool = False


class InitUseCase:
    """Use case for initializing a new ember index.

    This creates the .ember/ directory structure and all required files.
    It's the first command users run when setting up ember in a codebase.
    """

    def __init__(self, db_initializer: DatabaseInitializer, version: str = "0.1.0"):
        """Initialize the use case.

        Args:
            db_initializer: Database initializer for creating the index database.
            version: Ember version string (for state.json)
        """
        self._db_initializer = db_initializer
        self.version = version

    def _create_error_response(
        self, error: str, already_exists: bool = False
    ) -> InitResponse:
        """Create a standardized error response.

        Args:
            error: Error message.
            already_exists: True if error is because .ember/ already exists.

        Returns:
            InitResponse with success=False.
        """
        return InitResponse(
            ember_dir=None,
            config_path=None,
            db_path=None,
            state_path=None,
            was_reinitialized=False,
            global_config_created=False,
            global_config_path=None,
            success=False,
            error=error,
            already_exists=already_exists,
        )

    def execute(self, request: InitRequest) -> InitResponse:
        """Execute the init operation.

        Creates .ember/ directory with:
        - config.toml (minimal project configuration)
        - index.db (empty SQLite database with schema)
        - state.json (initial state tracking)

        On first run (no global config exists), also creates:
        - ~/.config/ember/config.toml (global config with hardware-specific defaults)

        Error handling contract:
            - KeyboardInterrupt/SystemExit are re-raised (user wants to exit)
            - All other exceptions are caught and converted to error responses
            - See ember.core.use_case_errors for the error handling pattern

        Args:
            request: Init request with repo root and options

        Returns:
            InitResponse with paths to created files, or error information.
        """
        ember_dir = request.repo_root / ".ember"
        config_path = ember_dir / "config.toml"
        db_path = ember_dir / "index.db"
        state_path = ember_dir / "state.json"
        global_config_path = get_global_config_path()

        try:
            # Check if .ember/ already exists
            was_reinitialized = False
            if ember_dir.exists():
                if not request.force:
                    return self._create_error_response(
                        f"Directory {ember_dir} already exists. "
                        "Use --force to reinitialize.",
                        already_exists=True,
                    )
                was_reinitialized = True

            # Create global config if it doesn't exist (first run)
            global_config_created = False
            if not global_config_path.exists():
                create_global_config_file(global_config_path, model=request.model)
                global_config_created = True

            # Create .ember/ directory
            ember_dir.mkdir(parents=True, exist_ok=True)

            # Create minimal project config (settings inherit from global)
            create_minimal_project_config(config_path)

            # Initialize database with schema
            self._db_initializer.init_database(db_path)

            # Create initial state.json
            create_initial_state(state_path, version=self.version)

            return InitResponse(
                ember_dir=ember_dir,
                config_path=config_path,
                db_path=db_path,
                state_path=state_path,
                was_reinitialized=was_reinitialized,
                global_config_created=global_config_created,
                global_config_path=global_config_path,
                success=True,
                error=None,
                already_exists=False,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            log_use_case_error(e, "initialization")
            return self._create_error_response(format_error_message(e, "initialization"))
