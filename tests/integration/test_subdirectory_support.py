"""Integration tests for subdirectory support.

Tests that ember commands work correctly when run from subdirectories,
similar to how git works from anywhere within a repository.
"""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def test_repo_with_subdirs(tmp_path):
    """Create a test repository with nested subdirectories."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Create directory structure
    (repo / "src").mkdir()
    (repo / "src" / "utils").mkdir()
    (repo / "tests").mkdir()

    # Create some files
    (repo / "main.py").write_text("def main(): pass")
    (repo / "src" / "module.py").write_text("class Foo: pass")
    (repo / "src" / "utils" / "helpers.py").write_text("def helper(): pass")
    (repo / "tests" / "test_main.py").write_text("def test_main(): pass")

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True
    )

    return repo


def test_init_from_subdirectory_finds_git_root(test_repo_with_subdirs):
    """Test that 'ember init' from a subdirectory initializes at git root."""
    repo = test_repo_with_subdirs
    subdir = repo / "src" / "utils"

    # Run init from deep subdirectory
    from ember.core.config.init_usecase import InitRequest, InitUseCase

    # Simulate running from subdirectory by passing the subdir as start_path
    from ember.core.repo_utils import find_repo_root_for_init

    repo_root = find_repo_root_for_init(subdir)

    # Should find git root, not the subdirectory
    assert repo_root == repo

    # Now actually initialize
    use_case = InitUseCase(version="0.2.0")
    request = InitRequest(repo_root=repo_root, force=False)
    response = use_case.execute(request)

    # Verify .ember/ created at repo root
    assert response.ember_dir == repo / ".ember"
    assert (repo / ".ember").exists()
    assert (repo / ".ember" / "config.toml").exists()
    assert (repo / ".ember" / "index.db").exists()


def test_find_ember_root_from_subdirectory(test_repo_with_subdirs):
    """Test that ember root can be found from any subdirectory."""
    repo = test_repo_with_subdirs

    # Initialize ember at repo root
    from ember.core.config.init_usecase import InitRequest, InitUseCase

    use_case = InitUseCase(version="0.2.0")
    request = InitRequest(repo_root=repo, force=False)
    use_case.execute(request)

    # Test finding from various subdirectories
    from ember.core.repo_utils import find_repo_root

    # From repo root
    root, ember_dir = find_repo_root(repo)
    assert root == repo
    assert ember_dir == repo / ".ember"

    # From shallow subdirectory
    root, ember_dir = find_repo_root(repo / "src")
    assert root == repo
    assert ember_dir == repo / ".ember"

    # From deep subdirectory
    root, ember_dir = find_repo_root(repo / "src" / "utils")
    assert root == repo
    assert ember_dir == repo / ".ember"

    # From different branch of tree
    root, ember_dir = find_repo_root(repo / "tests")
    assert root == repo
    assert ember_dir == repo / ".ember"


def test_find_ember_root_fails_outside_repo(tmp_path):
    """Test that ember root search fails gracefully outside a repo."""
    from ember.core.repo_utils import find_repo_root

    with pytest.raises(RuntimeError, match="Not in an ember repository"):
        find_repo_root(tmp_path)


def test_path_scoped_search_from_subdirectory(test_repo_with_subdirs):
    """Test path-scoped search works correctly from subdirectories."""
    repo = test_repo_with_subdirs

    # Initialize and sync
    from ember.core.config.init_usecase import InitRequest, InitUseCase

    use_case = InitUseCase(version="0.2.0")
    request = InitRequest(repo_root=repo, force=False)
    use_case.execute(request)

    # Index the repository
    import blake3

    from ember.adapters.config.toml_config_provider import TomlConfigProvider
    from ember.adapters.fs.local import LocalFileSystem
    from ember.adapters.git_cmd.git_adapter import GitAdapter
    from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
    from ember.adapters.parsers.line_chunker import LineChunker
    from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
    from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
    from ember.adapters.sqlite.file_repository import SQLiteFileRepository
    from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
    from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
    from ember.core.chunking.chunk_usecase import ChunkFileUseCase
    from ember.core.indexing.index_usecase import IndexingUseCase, IndexRequest

    db_path = repo / ".ember" / "index.db"
    config_provider = TomlConfigProvider()
    config = config_provider.load(repo / ".ember")

    vcs = GitAdapter(repo)
    fs = LocalFileSystem()
    embedder = JinaCodeEmbedder()
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    file_repo = SQLiteFileRepository(db_path)
    meta_repo = SQLiteMetaRepository(db_path)

    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker(
        window_size=config.index.line_window,
        stride=config.index.line_stride,
    )
    chunk_usecase = ChunkFileUseCase(tree_sitter, line_chunker)
    project_id = blake3.blake3(str(repo).encode("utf-8")).hexdigest()

    indexing_usecase = IndexingUseCase(
        vcs=vcs,
        fs=fs,
        chunk_usecase=chunk_usecase,
        embedder=embedder,
        chunk_repo=chunk_repo,
        vector_repo=vector_repo,
        file_repo=file_repo,
        meta_repo=meta_repo,
        project_id=project_id,
    )

    index_request = IndexRequest(
        repo_root=repo,
        sync_mode="worktree",
        path_filters=[],
        force_reindex=False,
    )
    indexing_usecase.execute(index_request)

    # Now test path-scoped search
    # Simulate being in src/ directory and searching for "src/**"
    from ember.adapters.fts.sqlite_fts import SQLiteFTS
    from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
    from ember.core.retrieval.search_usecase import SearchUseCase
    from ember.domain.entities import Query

    text_search = SQLiteFTS(db_path)
    vector_search = SqliteVecAdapter(db_path)

    search_usecase = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )

    # Search only in src/ subtree
    query = Query(
        text="class",
        topk=10,
        path_filter="src/**",
        lang_filter=None,
        json_output=False,
    )
    results = search_usecase.search(query)

    # Should only find results in src/
    assert len(results) > 0
    for result in results:
        assert str(result.chunk.path).startswith("src/")


def test_find_git_root():
    """Test finding git root from various directories."""
    from ember.core.repo_utils import find_git_root

    # Should find the ember project's git root
    ember_root = find_git_root(Path(__file__).parent)
    assert ember_root is not None
    assert (ember_root / ".git").exists()

    # Should return None for non-git directory
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        result = find_git_root(Path(tmpdir))
        assert result is None


def test_find_ember_root():
    """Test finding ember root by walking up directories."""
    # Create a temporary directory structure
    import tempfile

    from ember.core.repo_utils import find_ember_root

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()
        (root / ".ember").mkdir()
        (root / "src" / "deep" / "nested").mkdir(parents=True)

        # Should find from root
        assert find_ember_root(root) == root

        # Should find from subdirectory
        assert find_ember_root(root / "src") == root

        # Should find from deep subdirectory
        assert find_ember_root(root / "src" / "deep" / "nested") == root

        # Should return None if not found
        outside = root.parent
        assert find_ember_root(outside) is None
