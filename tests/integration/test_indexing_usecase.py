"""Integration tests for IndexingUseCase.

Tests the complete indexing flow including git integration, chunking,
embedding, and incremental sync with proper cleanup of old chunks.
"""

import sqlite3
from pathlib import Path

import pytest

from ember.adapters.fs.local import LocalFileSystem
from ember.adapters.git_cmd.git_adapter import GitAdapter
from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
from ember.adapters.parsers.line_chunker import LineChunker
from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.file_repository import SQLiteFileRepository
from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
from ember.adapters.sqlite.schema import init_database
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.core.chunking.chunk_usecase import ChunkFileUseCase
from ember.core.indexing.index_usecase import IndexingUseCase, IndexRequest


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a git repository with test files."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    # Create test files
    test_file1 = repo_root / "math.py"
    test_file1.write_text("""def add(a, b):
    '''Add two numbers.'''
    return a + b


def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b
""")

    test_file2 = repo_root / "utils.py"
    test_file2.write_text("""def greet(name):
    '''Greet someone.'''
    return f"Hello, {name}!"
""")

    # Commit files
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    return repo_root


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized."""
    db = tmp_path / "test_index.db"
    init_database(db)
    return db


@pytest.fixture
def indexing_usecase(git_repo: Path, db_path: Path) -> IndexingUseCase:
    """Create IndexingUseCase with real adapters."""
    vcs = GitAdapter(git_repo)
    fs = LocalFileSystem()
    tree_sitter_chunker = TreeSitterChunker()
    line_chunker = LineChunker()
    chunk_usecase = ChunkFileUseCase(tree_sitter_chunker, line_chunker)
    embedder = JinaCodeEmbedder()
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    file_repo = SQLiteFileRepository(db_path)
    meta_repo = SQLiteMetaRepository(db_path)
    project_id = "test_project"

    return IndexingUseCase(
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


@pytest.mark.slow
def test_full_index(indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path) -> None:
    """Test full indexing of a repository."""
    request = IndexRequest(repo_root=git_repo, force_reindex=True)
    response = indexing_usecase.execute(request)

    assert response.success
    assert response.files_indexed == 2  # math.py and utils.py
    assert response.chunks_created > 0
    assert response.vectors_stored > 0
    assert not response.is_incremental

    # Verify chunks are in database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chunks")
    chunk_count = cursor.fetchone()[0]
    assert chunk_count == response.chunks_created
    conn.close()


@pytest.mark.slow
def test_incremental_sync_no_changes(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path
) -> None:
    """Test incremental sync when no files have changed."""
    # First sync
    request1 = IndexRequest(repo_root=git_repo, force_reindex=True)
    response1 = indexing_usecase.execute(request1)
    assert response1.success
    initial_chunks = response1.chunks_created

    # Second sync (no changes)
    request2 = IndexRequest(repo_root=git_repo)
    response2 = indexing_usecase.execute(request2)

    assert response2.success
    assert response2.files_indexed == 0  # No files changed
    assert response2.chunks_created == 0
    # Note: is_incremental is False when there are no files to index
    # This is correct behavior from _get_files_to_index returning ([], False)

    # Total chunks should remain the same
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chunks")
    final_chunks = cursor.fetchone()[0]
    assert final_chunks == initial_chunks
    conn.close()


@pytest.mark.slow
def test_incremental_sync_modified_file_no_duplicates(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path
) -> None:
    """Test that modifying a file doesn't create duplicate chunks.

    This is a regression test for issue #13: when a file is modified
    (even just line number changes), old chunks should be deleted
    before adding new chunks, preventing duplicate accumulation.
    """
    # First sync
    request1 = IndexRequest(repo_root=git_repo, force_reindex=True)
    response1 = indexing_usecase.execute(request1)
    assert response1.success
    initial_chunks = response1.chunks_created

    # Get initial tree SHA
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT tree_sha FROM chunks")
    tree_shas_before = [row[0] for row in cursor.fetchall()]
    assert len(tree_shas_before) == 1  # Only one tree SHA
    initial_tree_sha = tree_shas_before[0]

    # Modify math.py (add blank lines to shift line numbers)
    math_file = git_repo / "math.py"
    original_content = math_file.read_text()
    modified_content = "\n\n" + original_content  # Add blank lines at start
    math_file.write_text(modified_content)

    # Commit the change
    import subprocess
    subprocess.run(["git", "add", "math.py"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Modify math.py"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    # Second sync (incremental)
    request2 = IndexRequest(repo_root=git_repo)
    response2 = indexing_usecase.execute(request2)

    assert response2.success
    assert response2.files_indexed == 1  # Only math.py changed
    assert response2.is_incremental

    # CRITICAL: Verify no duplicate chunks exist
    cursor.execute("SELECT COUNT(*) FROM chunks")
    final_chunk_count = cursor.fetchone()[0]

    # We should have approximately the same number of chunks
    # (old math.py chunks deleted, new math.py chunks added)
    # Allow for small variation due to chunking differences
    assert abs(final_chunk_count - initial_chunks) < 5

    # After incremental sync, we expect TWO tree SHAs:
    # - Old tree SHA for utils.py (unchanged file)
    # - New tree SHA for math.py (modified file)
    # This is CORRECT behavior - unchanged files keep their tree SHA
    cursor.execute("SELECT DISTINCT tree_sha FROM chunks")
    tree_shas_after = [row[0] for row in cursor.fetchall()]
    assert len(tree_shas_after) == 2, f"Expected 2 tree SHAs, found: {tree_shas_after}"

    # CRITICAL: Verify math.py chunks ONLY have the new tree SHA (no duplicates!)
    cursor.execute(
        """
        SELECT tree_sha, COUNT(*)
        FROM chunks
        WHERE path = 'math.py'
        GROUP BY tree_sha
        """
    )
    math_chunks_by_tree = cursor.fetchall()
    assert len(math_chunks_by_tree) == 1, f"math.py has chunks from multiple tree SHAs: {math_chunks_by_tree}"

    # The math.py tree SHA should be different from the initial tree SHA
    math_tree_sha = math_chunks_by_tree[0][0]
    assert math_tree_sha != initial_tree_sha

    # CRITICAL: Verify utils.py still has the OLD tree SHA (it wasn't modified)
    cursor.execute(
        """
        SELECT tree_sha, COUNT(*)
        FROM chunks
        WHERE path = 'utils.py'
        GROUP BY tree_sha
        """
    )
    utils_chunks_by_tree = cursor.fetchall()
    assert len(utils_chunks_by_tree) == 1, "utils.py should only have one tree SHA"
    assert utils_chunks_by_tree[0][0] == initial_tree_sha, "utils.py should keep old tree SHA"

    conn.close()


@pytest.mark.slow
def test_incremental_sync_multiple_modifications_no_accumulation(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path
) -> None:
    """Test that multiple modifications of the SAME file don't cause chunk accumulation.

    This tests the scenario where a single file is modified multiple times,
    ensuring that old chunks from that file are properly cleaned up each time.
    """
    # Initial sync
    request = IndexRequest(repo_root=git_repo, force_reindex=True)
    response = indexing_usecase.execute(request)
    initial_chunks = response.chunks_created

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get initial math.py chunk count
    cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = 'math.py'")
    initial_math_chunks = cursor.fetchone()[0]

    # Modify math.py multiple times
    math_file = git_repo / "math.py"
    for i in range(3):
        # Add more blank lines each time
        content = math_file.read_text()
        math_file.write_text("\n" + content)

        # Commit
        import subprocess
        subprocess.run(
            ["git", "add", "math.py"],
            cwd=git_repo,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Modification {i+1}"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )

        # Sync
        request = IndexRequest(repo_root=git_repo)
        indexing_usecase.execute(request)

        # CRITICAL: Verify math.py has only ONE tree SHA (no duplicates from old syncs)
        cursor.execute("""
            SELECT COUNT(DISTINCT tree_sha)
            FROM chunks
            WHERE path = 'math.py'
        """)
        math_tree_sha_count = cursor.fetchone()[0]
        assert math_tree_sha_count == 1, f"After modification {i+1}, math.py has {math_tree_sha_count} tree SHAs"

        # Verify math.py chunk count stays roughly the same (no accumulation)
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = 'math.py'")
        current_math_chunks = cursor.fetchone()[0]
        assert abs(current_math_chunks - initial_math_chunks) < 5, \
            f"math.py chunks grew from {initial_math_chunks} to {current_math_chunks}"

    # Final verification: total chunks should be roughly the same
    cursor.execute("SELECT COUNT(*) FROM chunks")
    final_chunks = cursor.fetchone()[0]
    assert abs(final_chunks - initial_chunks) < 10

    conn.close()


@pytest.mark.slow
def test_incremental_sync_deleted_file(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path
) -> None:
    """Test that deleted files have their chunks removed."""
    # Initial sync
    request1 = IndexRequest(repo_root=git_repo, force_reindex=True)
    response1 = indexing_usecase.execute(request1)
    assert response1.success

    # Delete utils.py
    utils_file = git_repo / "utils.py"
    utils_file.unlink()

    # Commit deletion
    import subprocess
    subprocess.run(["git", "add", "-u"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Delete utils.py"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    # Incremental sync
    request2 = IndexRequest(repo_root=git_repo)
    response2 = indexing_usecase.execute(request2)

    assert response2.success
    assert response2.chunks_deleted > 0

    # Verify utils.py chunks are gone
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = 'utils.py'")
    utils_chunks = cursor.fetchone()[0]
    assert utils_chunks == 0
    conn.close()
