"""Pytest configuration and shared fixtures."""

import gc
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock, patch

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
    content = 'def test_function():\n    return "hello"'
    return Chunk(
        id="test_chunk_123",
        project_id="test_project",
        path=Path("src/example.py"),
        lang="py",
        symbol="test_function",
        start_line=10,
        end_line=20,
        content=content,
        content_hash=Chunk.compute_content_hash(content),
        file_hash=Chunk.compute_content_hash("file content"),  # Valid blake3 hash
        tree_sha="a" * 40,  # Valid git SHA
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
        content = f"def function_{i}():\n    pass"
        chunk = Chunk(
            id=f"chunk_{i}",
            project_id="test_project",
            path=Path(f"src/file_{i}.py"),
            lang="py",
            symbol=f"function_{i}",
            start_line=start_line,
            end_line=end_line,
            content=content,
            content_hash=Chunk.compute_content_hash(content),
            file_hash=Chunk.compute_content_hash(f"file_{i}_content"),  # Valid blake3 hash
            tree_sha="b" * 40,  # Valid git SHA
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


# ============================================================================
# Mock Embedder Fixtures
# ============================================================================
# These fixtures provide standardized mock embedders for tests that don't
# need real embeddings. Using these fixtures ensures consistent behavior
# and reduces code duplication across test files.


@pytest.fixture
def mock_embedder() -> Mock:
    """Create a standard mock embedder for tests.

    Provides a mock that implements the Embedder protocol with:
    - name: "mock-embedder"
    - dim: 384
    - fingerprint(): "mock-embedder:384"
    - embed_texts(): Returns deterministic embeddings based on text hash

    The embeddings are deterministic - same text always produces same embedding.
    This makes tests reproducible while still producing distinct embeddings.

    Returns:
        Mock embedder with standard configuration.

    Example:
        def test_something(mock_embedder):
            service = ChunkStorageService(chunk_repo, vector_repo, mock_embedder)
            # mock_embedder.embed_texts will return deterministic vectors
    """
    embedder = Mock()
    embedder.name = "mock-embedder"
    embedder.dim = 384
    embedder.fingerprint.return_value = "mock-embedder:384"

    def embed_texts_impl(texts: list[str]) -> list[list[float]]:
        """Generate deterministic embeddings based on text content."""
        embeddings = []
        for text in texts:
            # Use hash to generate deterministic values between 0 and 1
            text_hash = hash(text) & 0xFFFFFFFF  # Ensure positive
            embedding = [(text_hash * (i + 1) % 1000) / 1000.0 for i in range(384)]
            embeddings.append(embedding)
        return embeddings

    embedder.embed_texts.side_effect = embed_texts_impl
    return embedder


@pytest.fixture
def mock_embedder_factory() -> Callable[..., Mock]:
    """Factory fixture for creating customized mock embedders.

    Use this when you need to customize the mock embedder's behavior,
    such as changing dimension, fingerprint, or making embed_texts fail.

    Returns:
        Factory function that creates configured mock embedders.

    Example:
        def test_custom_embedder(mock_embedder_factory):
            # Create embedder with custom dimension
            embedder = mock_embedder_factory(dim=768, name="custom-model")

            # Create embedder that fails
            failing_embedder = mock_embedder_factory()
            failing_embedder.embed_texts.side_effect = RuntimeError("OOM")
    """

    def _create_embedder(
        name: str = "mock-embedder",
        dim: int = 384,
        fingerprint: str | None = None,
    ) -> Mock:
        embedder = Mock()
        embedder.name = name
        embedder.dim = dim
        embedder.fingerprint.return_value = fingerprint or f"{name}:{dim}"

        def embed_texts_impl(texts: list[str]) -> list[list[float]]:
            embeddings = []
            for text in texts:
                text_hash = hash(text) & 0xFFFFFFFF
                embedding = [(text_hash * (i + 1) % 1000) / 1000.0 for i in range(dim)]
                embeddings.append(embedding)
            return embeddings

        embedder.embed_texts.side_effect = embed_texts_impl
        return embedder

    return _create_embedder


# ============================================================================
# Chunk Factory Fixture
# ============================================================================


@pytest.fixture
def chunk_factory() -> Callable[..., Chunk]:
    """Factory fixture for creating test chunks with customizable values.

    Creates Chunk entities with sensible defaults that can be overridden.
    Handles content_hash and file_hash computation automatically.

    Returns:
        Factory function that creates Chunk instances.

    Example:
        def test_something(chunk_factory):
            # Create with defaults
            chunk1 = chunk_factory()

            # Create with custom values
            chunk2 = chunk_factory(
                path="src/utils.py",
                symbol="helper_func",
                content="def helper(): return 42",
                start_line=10,
                end_line=15,
            )

            # Create multiple unique chunks
            chunks = [
                chunk_factory(chunk_id=f"chunk_{i}", start_line=i*10+1)
                for i in range(5)
            ]
    """
    _counter = [0]  # Mutable container for unique IDs

    def _create_chunk(
        chunk_id: str | None = None,
        project_id: str = "test_project",
        path: str | Path = "test.py",
        lang: str = "py",
        symbol: str = "test_func",
        start_line: int = 1,
        end_line: int | None = None,
        content: str = "def test_func(): pass",
        tree_sha: str | None = None,
        rev: str = "worktree",
    ) -> Chunk:
        # Generate unique ID if not provided
        if chunk_id is None:
            _counter[0] += 1
            chunk_id = f"test_chunk_{_counter[0]}"

        # Default end_line to start_line if not provided
        if end_line is None:
            end_line = start_line

        # Default tree_sha to valid 40-char hex
        if tree_sha is None:
            tree_sha = "a" * 40

        # Compute hashes
        content_hash = Chunk.compute_content_hash(content)
        file_hash = Chunk.compute_content_hash(f"file_content_{path}")

        return Chunk(
            id=chunk_id,
            project_id=project_id,
            path=Path(path) if isinstance(path, str) else path,
            lang=lang,
            symbol=symbol,
            start_line=start_line,
            end_line=end_line,
            content=content,
            content_hash=content_hash,
            file_hash=file_hash,
            tree_sha=tree_sha,
            rev=rev,
        )

    return _create_chunk
