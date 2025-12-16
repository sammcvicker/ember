"""Pytest configuration and shared fixtures."""

import gc
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ember.adapters.sqlite.schema import init_database
from ember.domain.entities import Chunk

# ============================================================================
# GPU Mocking for Test Determinism
# ============================================================================
# Mock GPU detection to ensure tests behave consistently across machines.
# Without this, tests may behave differently on machines with/without GPUs
# because the init command prompts when GPU VRAM is limited.


@pytest.fixture(autouse=True)
def mock_gpu_detection():
    """Mock GPU detection to return None for consistent test behavior.

    This ensures tests don't prompt for model selection based on GPU VRAM,
    making integration tests deterministic across different hardware.
    """
    with patch("ember.core.hardware.detect_gpu_resources", return_value=None):
        yield

# ============================================================================
# Git Repository Helpers
# ============================================================================
# These helpers consolidate git setup code to avoid duplication across tests.
# Use these functions in fixtures to create consistent test repositories.


def init_git_repo(
    path: Path,
    user_name: str = "Test User",
    user_email: str = "test@example.com",
) -> None:
    """Initialize a git repository with user configuration.

    This is the single source of truth for git repository initialization.
    Use this helper in fixtures instead of inline subprocess calls.

    Args:
        path: Directory to initialize as a git repository.
        user_name: Git user.name configuration value.
        user_email: Git user.email configuration value.

    Raises:
        subprocess.CalledProcessError: If git commands fail.
    """
    subprocess.run(
        ["git", "init"],
        cwd=path,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.name", user_name],
        cwd=path,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.email", user_email],
        cwd=path,
        check=True,
        capture_output=True,
        timeout=5,
    )


def git_add_and_commit(
    path: Path,
    message: str = "Initial commit",
    add_all: bool = True,
) -> None:
    """Stage files and create a git commit.

    Args:
        path: Git repository root directory.
        message: Commit message.
        add_all: If True, stages all files with 'git add .'.

    Raises:
        subprocess.CalledProcessError: If git commands fail.
    """
    if add_all:
        subprocess.run(
            ["git", "add", "."],
            cwd=path,
            check=True,
            capture_output=True,
            timeout=5,
        )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path,
        check=True,
        capture_output=True,
        timeout=5,
    )


def create_test_files(path: Path, files: dict[str, str]) -> None:
    """Create multiple files in a directory.

    Args:
        path: Base directory for file creation.
        files: Mapping of relative file paths to file contents.
               Parent directories are created automatically.

    Example:
        create_test_files(repo, {
            "main.py": "def main(): pass",
            "src/utils.py": "def helper(): pass",
        })
    """
    for file_path, content in files.items():
        full_path = path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)


def create_git_repo(
    path: Path,
    files: dict[str, str] | None = None,
    commit_message: str = "Initial commit",
    user_name: str = "Test User",
    user_email: str = "test@example.com",
) -> Path:
    """Create a complete git repository with optional files.

    This is a convenience function that combines init_git_repo(),
    create_test_files(), and git_add_and_commit().

    Args:
        path: Directory for the repository (created if doesn't exist).
        files: Optional mapping of file paths to contents.
        commit_message: Message for the initial commit.
        user_name: Git user.name configuration.
        user_email: Git user.email configuration.

    Returns:
        Path to the repository root.
    """
    path.mkdir(parents=True, exist_ok=True)
    init_git_repo(path, user_name=user_name, user_email=user_email)

    if files:
        create_test_files(path, files)
        git_add_and_commit(path, message=commit_message)

    return path


@pytest.fixture(autouse=True)
def cleanup_database_connections():
    """Automatically clean up database connections after each test.

    This fixture ensures that any unclosed SQLite database connections
    are properly garbage collected after each test, preventing
    ResourceWarning messages about unclosed database connections.

    The fixture is autouse=True so it runs automatically for every test.
    It runs gc.collect() twice to ensure finalizers are called.
    """
    yield
    # Force garbage collection twice to ensure finalizers run
    # First pass marks objects for collection, second pass runs finalizers
    gc.collect()
    gc.collect()


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for tests.

    Yields:
        Path to temporary directory (cleaned up after test).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunk() -> Chunk:
    """Create a sample chunk for testing.

    Returns:
        A Chunk instance with test data.
    """
    return Chunk(
        id="test_chunk_123",
        project_id="test_project",
        path=Path("src/example.py"),
        lang="py",
        symbol="test_function",
        start_line=10,
        end_line=20,
        content='def test_function():\n    return "hello"',
        content_hash=Chunk.compute_content_hash('def test_function():\n    return "hello"'),
        file_hash="abc123",
        tree_sha="def456",
        rev="HEAD",
    )


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """Create multiple sample chunks for testing.

    Returns:
        List of Chunk instances.
    """
    chunks = []
    for i in range(5):
        # Start lines at 1 (1-indexed) to satisfy validation
        start_line = (i * 10) + 1
        end_line = start_line + 10
        chunk = Chunk(
            id=f"chunk_{i}",
            project_id="test_project",
            path=Path(f"src/file_{i}.py"),
            lang="py",
            symbol=f"function_{i}",
            start_line=start_line,
            end_line=end_line,
            content=f"def function_{i}():\n    pass",
            content_hash=Chunk.compute_content_hash(f"def function_{i}():\n    pass"),
            file_hash=f"hash_{i}",
            tree_sha="tree_sha_test",
            rev="HEAD",
        )
        chunks.append(chunk)
    return chunks


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a standard git repository with test files.

    Creates a git repository with:
    - Two Python files (math.py, utils.py)
    - Proper git configuration
    - Initial commit

    Returns:
        Path to the git repository root.
    """
    return create_git_repo(
        tmp_path / "test_repo",
        files={
            "math.py": """def add(a, b):
    '''Add two numbers.'''
    return a + b


def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b
""",
            "utils.py": """def greet(name):
    '''Greet someone.'''
    return f"Hello, {name}!"
""",
        },
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized.

    Returns:
        Path to the initialized test database.

    Note:
        Database connection cleanup is handled by the autouse
        cleanup_database_connections fixture.
    """
    db = tmp_path / "test.db"
    init_database(db)
    return db


@pytest.fixture
def realistic_repo(tmp_path: Path) -> Path:
    """Create a realistic git repository with diverse files for testing.

    Creates a repository with:
    - 10+ files across multiple languages (Python, JavaScript, TypeScript, Markdown)
    - Realistic code patterns (classes, functions, docstrings, comments)
    - Nested directory structure
    - 100+ potential code chunks for testing indexing and search

    File content data is stored in tests/fixtures/realistic_repo_data.py to keep
    this configuration file manageable.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to the created repository root.
    """
    from tests.fixtures.realistic_repo_data import create_realistic_repo

    repo_path = tmp_path / "realistic_repo"
    repo_path.mkdir()

    # Initialize git repository using shared helper
    init_git_repo(repo_path)

    # Create all files using the helper from the data module
    create_realistic_repo(repo_path)

    # Commit all files using shared helper
    git_add_and_commit(repo_path, message="Initial commit with realistic test data")

    return repo_path
