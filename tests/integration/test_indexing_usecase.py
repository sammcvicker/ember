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

# Note: git_repo and db_path fixtures are now in tests/conftest.py


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

    subprocess.run(
        ["git", "add", "math.py"], cwd=git_repo, check=True, capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "commit", "-m", "Modify math.py"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
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
    assert len(math_chunks_by_tree) == 1, (
        f"math.py has chunks from multiple tree SHAs: {math_chunks_by_tree}"
    )

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
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Modification {i + 1}"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            timeout=5,
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
        assert math_tree_sha_count == 1, (
            f"After modification {i + 1}, math.py has {math_tree_sha_count} tree SHAs"
        )

        # Verify math.py chunk count stays roughly the same (no accumulation)
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = 'math.py'")
        current_math_chunks = cursor.fetchone()[0]
        assert abs(current_math_chunks - initial_math_chunks) < 5, (
            f"math.py chunks grew from {initial_math_chunks} to {current_math_chunks}"
        )

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

    subprocess.run(["git", "add", "-u"], cwd=git_repo, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Delete utils.py"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
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


@pytest.mark.slow
def test_chunking_failure_preserves_existing_chunks(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path
) -> None:
    """Test that when chunking fails, existing chunks are preserved (no data loss).

    This is a regression test for issue #33: if chunking fails during re-indexing,
    the old chunks should be preserved rather than deleted.
    """
    # Initial sync - index math.py successfully
    request1 = IndexRequest(repo_root=git_repo, force_reindex=True)
    response1 = indexing_usecase.execute(request1)
    assert response1.success

    # Get initial math.py chunks
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = 'math.py'")
    initial_math_chunks = cursor.fetchone()[0]
    assert initial_math_chunks > 0, "Should have chunks for math.py"

    # Get the chunk IDs to verify they're the same later
    cursor.execute("SELECT id FROM chunks WHERE path = 'math.py' ORDER BY id")
    initial_chunk_ids = [row[0] for row in cursor.fetchall()]

    # Mock the chunk_usecase to fail
    from ember.core.chunking.chunk_usecase import ChunkFileResponse

    original_execute = indexing_usecase.chunk_usecase.execute

    def mock_chunk_execute(request):
        # Fail only for math.py, succeed for others
        if "math.py" in str(request.path):
            return ChunkFileResponse(
                chunks=[], strategy="tree-sitter", success=False, error="Simulated chunking failure"
            )
        return original_execute(request)

    indexing_usecase.chunk_usecase.execute = mock_chunk_execute

    # Try to re-index (force reindex to ensure it tries to process math.py)
    request2 = IndexRequest(repo_root=git_repo, force_reindex=True)
    response2 = indexing_usecase.execute(request2)

    # Should still succeed overall (just skips the failed file)
    assert response2.success

    # CRITICAL: Verify math.py chunks are STILL THERE (not deleted)
    cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = 'math.py'")
    final_math_chunks = cursor.fetchone()[0]
    assert final_math_chunks == initial_math_chunks, (
        f"Chunks should be preserved on failure, but went from {initial_math_chunks} to {final_math_chunks}"
    )

    # Verify the chunk IDs are the same (i.e., chunks weren't deleted and recreated)
    cursor.execute("SELECT id FROM chunks WHERE path = 'math.py' ORDER BY id")
    final_chunk_ids = [row[0] for row in cursor.fetchall()]
    assert final_chunk_ids == initial_chunk_ids, "Chunk IDs should be unchanged"

    conn.close()

    # Restore original method
    indexing_usecase.chunk_usecase.execute = original_execute


@pytest.mark.slow
def test_index_file_with_unreadable_file(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path
) -> None:
    """Test handling of permission denied errors.

    Verifies that IndexingUseCase handles files that can't be read
    due to permission errors. Documents current behavior.
    """
    import os
    import stat
    import subprocess

    # Create a file and add it to git first
    restricted_file = git_repo / "restricted.py"
    restricted_file.write_text("def secret(): pass\n")

    # Add to git and commit BEFORE removing permissions
    subprocess.run(
        ["git", "add", "restricted.py"], cwd=git_repo, check=True, capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "commit", "-m", "Add restricted file"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Now remove read permissions
    try:
        os.chmod(restricted_file, stat.S_IWRITE)  # Write-only, no read

        # Attempt to index - behavior depends on implementation
        request = IndexRequest(repo_root=git_repo, force_reindex=True)
        response = indexing_usecase.execute(request)

        # Current implementation may skip unreadable files or fail
        # This test documents the actual behavior without asserting specific outcome
        # Just verify it doesn't crash completely
        assert isinstance(response.success, bool)

    finally:
        # Restore permissions for cleanup
        try:
            os.chmod(restricted_file, stat.S_IREAD | stat.S_IWRITE)
        except:
            pass  # Best effort cleanup


@pytest.mark.slow
def test_index_file_with_invalid_utf8(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path
) -> None:
    """Test handling of encoding errors.

    Verifies that IndexingUseCase handles files with invalid UTF-8 encoding.
    Documents current behavior - system may handle encoding errors by skipping
    or using error-replacement strategies.
    """
    import subprocess

    # Create a file with invalid UTF-8 bytes
    binary_file = git_repo / "binary.py"
    # Write invalid UTF-8 sequence (0xFF is invalid in UTF-8)
    binary_file.write_bytes(b"def test():\n    x = \xff\xff\xff\n")

    # Add to git and commit
    subprocess.run(
        ["git", "add", "binary.py"], cwd=git_repo, check=True, capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "commit", "-m", "Add binary file"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Attempt to index
    request = IndexRequest(repo_root=git_repo, force_reindex=True)
    response = indexing_usecase.execute(request)

    # Should complete without crashing
    assert isinstance(response.success, bool)
    assert response.files_indexed >= 2  # At least math.py and utils.py

    # Current implementation may or may not index the binary file
    # This test just ensures no crash occurs
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = 'binary.py'")
    binary_chunks = cursor.fetchone()[0]
    # File may be indexed (with replacement chars) or skipped - both are valid
    assert binary_chunks >= 0
    conn.close()


@pytest.mark.slow
def test_index_file_with_embedder_failure(git_repo: Path, db_path: Path) -> None:
    """Test handling of embedder failures.

    Verifies that IndexingUseCase handles embedder failures (e.g., model errors,
    network issues) appropriately. Current implementation fails the entire index
    operation when embedding fails, which is documented here.
    """
    from unittest.mock import Mock

    # Create IndexingUseCase with a mock embedder that fails
    vcs = GitAdapter(git_repo)
    fs = LocalFileSystem()
    tree_sitter_chunker = TreeSitterChunker()
    line_chunker = LineChunker()
    chunk_usecase = ChunkFileUseCase(tree_sitter_chunker, line_chunker)

    # Mock embedder that raises an exception
    mock_embedder = Mock()
    mock_embedder.embed_texts.side_effect = RuntimeError("Model failed to load")
    mock_embedder.fingerprint.return_value = "mock-embedder-v1"

    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    file_repo = SQLiteFileRepository(db_path)
    meta_repo = SQLiteMetaRepository(db_path)
    project_id = "test_project"

    indexing_usecase = IndexingUseCase(
        vcs=vcs,
        fs=fs,
        chunk_usecase=chunk_usecase,
        embedder=mock_embedder,
        chunk_repo=chunk_repo,
        vector_repo=vector_repo,
        file_repo=file_repo,
        meta_repo=meta_repo,
        project_id=project_id,
    )

    # Attempt to index
    request = IndexRequest(repo_root=git_repo, force_reindex=True)
    response = indexing_usecase.execute(request)

    # Current implementation: embedder failure causes indexing to fail
    # This is acceptable behavior - documents that errors are reported
    assert response.success == False  # Embedder failure causes operation to fail
    assert response.error is not None  # Error message should be present
    assert len(response.error) > 0  # Error message should not be empty


@pytest.mark.slow
def test_realistic_repo_indexing(realistic_repo: Path, tmp_path: Path) -> None:
    """Test indexing a realistic repository with diverse file types and content.

    This test uses the realistic_repo fixture which contains:
    - 10 files across multiple languages (Python, JS, TS, Markdown)
    - Realistic code patterns (classes, functions, docstrings)
    - Nested directory structure
    - 100+ potential code chunks

    Verifies that the indexing system can handle diverse, realistic codebases.
    """
    # Set up database
    db_path = tmp_path / "realistic_test.db"
    init_database(db_path)

    # Create IndexingUseCase
    vcs = GitAdapter(realistic_repo)
    fs = LocalFileSystem()
    tree_sitter_chunker = TreeSitterChunker()
    line_chunker = LineChunker()
    chunk_usecase = ChunkFileUseCase(tree_sitter_chunker, line_chunker)
    embedder = JinaCodeEmbedder()
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    file_repo = SQLiteFileRepository(db_path)
    meta_repo = SQLiteMetaRepository(db_path)
    project_id = "realistic_test_project"

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

    # Index the repository
    request = IndexRequest(repo_root=realistic_repo, force_reindex=True)
    response = indexing_usecase.execute(request)

    # Verify successful indexing
    assert response.success, f"Indexing failed: {response.error}"
    # Note: 9 files indexed (README.md is not indexed as markdown is not a tracked language)
    assert response.files_indexed >= 8, f"Expected at least 8 files, got {response.files_indexed}"
    assert response.chunks_created >= 50, (
        f"Expected at least 50 chunks, got {response.chunks_created}"
    )
    assert response.vectors_stored == response.chunks_created

    # Verify chunks are in database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check total chunk count
    cursor.execute("SELECT COUNT(*) FROM chunks")
    chunk_count = cursor.fetchone()[0]
    assert chunk_count >= 50, f"Expected at least 50 chunks in DB, got {chunk_count}"

    # Check that we have chunks from different file types
    cursor.execute("SELECT DISTINCT path FROM chunks ORDER BY path")
    indexed_files = [row[0] for row in cursor.fetchall()]
    assert len(indexed_files) >= 8, f"Expected at least 8 files indexed, got {len(indexed_files)}"

    # Check for specific file types
    file_extensions = set(Path(f).suffix for f in indexed_files)
    assert ".py" in file_extensions, "Should have indexed Python files"
    # Note: .jsx and .ts may not be indexed if tree-sitter doesn't support them yet
    # or may be indexed with line chunker

    # Verify we have chunks from nested directories
    src_files = [f for f in indexed_files if f.startswith("src/")]
    assert len(src_files) >= 8, f"Expected at least 8 files from src/, got {len(src_files)}"

    # Check that chunks have proper metadata
    cursor.execute("""
        SELECT path, lang, symbol, start_line, end_line
        FROM chunks
        WHERE symbol IS NOT NULL AND symbol != ''
        LIMIT 10
    """)
    sample_chunks = cursor.fetchall()
    assert len(sample_chunks) > 0, "Should have chunks with symbols"

    # Verify chunks have content
    cursor.execute("SELECT content FROM chunks WHERE LENGTH(content) > 50 LIMIT 5")
    content_samples = cursor.fetchall()
    assert len(content_samples) >= 5, "Should have chunks with substantial content"

    conn.close()


@pytest.mark.slow
def test_model_fingerprint_change_warning(
    indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path, caplog
) -> None:
    """Test that changing the embedding model fingerprint triggers a warning.

    This is a regression test for issue #65: when the embedding model changes,
    users should be warned that existing vectors may be incompatible.
    """
    import logging

    # Enable logging capture
    caplog.set_level(logging.WARNING)

    # Initial index with original fingerprint
    request1 = IndexRequest(repo_root=git_repo, force_reindex=True)
    response1 = indexing_usecase.execute(request1)
    assert response1.success

    # Get the stored fingerprint
    meta_repo = SQLiteMetaRepository(db_path)
    original_fingerprint = meta_repo.get("model_fingerprint")
    assert original_fingerprint is not None, "Fingerprint should be stored after indexing"

    # Mock the embedder to return a different fingerprint
    original_fingerprint_fn = indexing_usecase.embedder.fingerprint
    new_fingerprint = "jina-embeddings-v3-code:xyz789"

    def mock_fingerprint():
        return new_fingerprint

    indexing_usecase.embedder.fingerprint = mock_fingerprint

    # Clear the log capture
    caplog.clear()

    # Run index again with the new fingerprint
    request2 = IndexRequest(repo_root=git_repo)
    response2 = indexing_usecase.execute(request2)

    # Should still succeed
    assert response2.success

    # Verify warning was logged
    warning_messages = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert any(original_fingerprint in msg for msg in warning_messages), (
        f"Expected warning about fingerprint change from {original_fingerprint}, got: {warning_messages}"
    )
    assert any(new_fingerprint in msg for msg in warning_messages), (
        f"Expected warning about new fingerprint {new_fingerprint}, got: {warning_messages}"
    )
    assert any("ember sync --force" in msg for msg in warning_messages), (
        "Warning should suggest running 'ember sync --force' to rebuild index"
    )

    # Restore original method
    indexing_usecase.embedder.fingerprint = original_fingerprint_fn
