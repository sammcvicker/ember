"""Init use case for initializing a new ember index.

This use case handles the creation of a new .ember/ directory with all
necessary files: config.toml, index.db, and state.json.
"""

from dataclasses import dataclass
from pathlib import Path

from ember.ports.database import DatabaseInitializer
from ember.shared.config_io import create_default_config_file
from ember.shared.state_io import create_initial_state


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
        ember_dir: Path to created .ember/ directory
        config_path: Path to created config.toml
        db_path: Path to created index.db
        state_path: Path to created state.json
        was_reinitialized: True if existing .ember/ was replaced
    """

    ember_dir: Path
    config_path: Path
    db_path: Path
    state_path: Path
    was_reinitialized: bool


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

    def execute(self, request: InitRequest) -> InitResponse:
        """Execute the init operation.

        Creates .ember/ directory with:
        - config.toml (default configuration)
        - index.db (empty SQLite database with schema)
        - state.json (initial state tracking)

        Args:
            request: Init request with repo root and options

        Returns:
            InitResponse with paths to created files

        Raises:
            FileExistsError: If .ember/ exists and force=False
            IOError: If file creation fails
        """
        ember_dir = request.repo_root / ".ember"
        config_path = ember_dir / "config.toml"
        db_path = ember_dir / "index.db"
        state_path = ember_dir / "state.json"

        # Check if .ember/ already exists
        was_reinitialized = False
        if ember_dir.exists():
            if not request.force:
                raise FileExistsError(f"Directory {ember_dir} already exists")
            was_reinitialized = True

        # Create .ember/ directory
        ember_dir.mkdir(parents=True, exist_ok=True)

        # Create config.toml with defaults
        create_default_config_file(config_path, model=request.model)

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
        )
