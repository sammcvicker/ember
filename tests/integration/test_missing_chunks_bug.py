"""Regression test for issue #125: Missing chunks during search retrieval.

This test verifies that chunk IDs returned by search adapters match
what's actually stored in the database, preventing "missing chunks" warnings.
"""

import logging
from pathlib import Path

import pytest

from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
from ember.core.retrieval.search_usecase import SearchUseCase
from ember.domain.entities import Chunk, Query


@pytest.mark.slow
def test_fts_returns_stored_chunk_ids(db_path: Path) -> None:
    """Test that FTS adapter returns actual chunk_id from database.

    This test ensures that FTS search returns the chunk_id stored in
    the database rather than computing it on-the-fly, which could lead
    to mismatches if the computation logic changes or metadata differs.
    """
    chunk_repo = SQLiteChunkRepository(db_path)
    fts = SQLiteFTS(db_path)

    # Create a test chunk
    chunk_id = Chunk.compute_id("test", Path("test.py"), 1, 3)
    content = "def test_function(): pass"
    content_hash = Chunk.compute_content_hash(content)

    chunk = Chunk(
        id=chunk_id,
        project_id="test",
        path=Path("test.py"),
        start_line=1,
        end_line=3,
        content=content,
        symbol="test_function",
        lang="py",
        content_hash=content_hash,
        file_hash=content_hash,
        tree_sha="a" * 40,
        rev="worktree",
    )
    chunk_repo.add(chunk)

    # Search for the chunk using FTS
    results = fts.query("test_function", topk=10)

    # Verify FTS returned the correct chunk_id
    assert len(results) > 0
    returned_chunk_id, _score = results[0]
    assert returned_chunk_id == chunk_id, (
        f"FTS returned computed chunk_id {returned_chunk_id} "
        f"instead of stored chunk_id {chunk_id}"
    )

    # Verify we can retrieve the chunk using the returned ID
    retrieved_chunk = chunk_repo.get(returned_chunk_id)
    assert retrieved_chunk is not None
    assert retrieved_chunk.id == chunk_id


@pytest.mark.slow
def test_vector_search_returns_stored_chunk_ids(db_path: Path) -> None:
    """Test that vector search returns actual chunk_id from database.

    This test ensures that vector search returns the chunk_id stored in
    the database rather than computing it on-the-fly.
    """
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SqliteVecAdapter(db_path)

    # Create a test chunk
    chunk_id = Chunk.compute_id("test", Path("test.py"), 1, 3)
    content = "def test_function(): pass"
    content_hash = Chunk.compute_content_hash(content)

    chunk = Chunk(
        id=chunk_id,
        project_id="test",
        path=Path("test.py"),
        start_line=1,
        end_line=3,
        content=content,
        symbol="test_function",
        lang="py",
        content_hash=content_hash,
        file_hash=content_hash,
        tree_sha="b" * 40,
        rev="worktree",
    )
    chunk_repo.add(chunk)

    # Add embedding
    embedding = embedder.embed_texts([content])[0]
    vector_repo.add(chunk_id, embedding, embedder.fingerprint())

    # Search using vector search
    query_embedding = embedder.embed_texts(["test function"])[0]
    results = vector_search.query(query_embedding, topk=10)

    # Verify vector search returned the correct chunk_id
    assert len(results) > 0
    returned_chunk_id, _score = results[0]
    assert returned_chunk_id == chunk_id, (
        f"Vector search returned computed chunk_id {returned_chunk_id} "
        f"instead of stored chunk_id {chunk_id}"
    )

    # Verify we can retrieve the chunk using the returned ID
    retrieved_chunk = chunk_repo.get(returned_chunk_id)
    assert retrieved_chunk is not None
    assert retrieved_chunk.id == chunk_id


@pytest.mark.slow
def test_search_no_missing_chunks_warning(
    db_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that normal search operations don't produce missing chunks warnings.

    This is a regression test for issue #125. Search adapters should return
    chunk IDs that actually exist in the database, not computed IDs that might
    not match.
    """
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    fts = SQLiteFTS(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SqliteVecAdapter(db_path)

    # Create test chunks
    chunks_data = [
        ("test.py", 1, 3, "def test1(): pass", "test1"),
        ("test.py", 5, 7, "def test2(): pass", "test2"),
        ("utils.py", 1, 3, "def helper(): pass", "helper"),
    ]

    for path_str, start, end, content, symbol in chunks_data:
        chunk_id = Chunk.compute_id("test", Path(path_str), start, end)
        content_hash = Chunk.compute_content_hash(content)

        chunk = Chunk(
            id=chunk_id,
            project_id="test",
            path=Path(path_str),
            start_line=start,
            end_line=end,
            content=content,
            symbol=symbol,
            lang="py",
            content_hash=content_hash,
            file_hash=content_hash,
            tree_sha="c" * 40,
            rev="worktree",
        )
        chunk_repo.add(chunk)

        # Add embedding
        embedding = embedder.embed_texts([content])[0]
        vector_repo.add(chunk_id, embedding, embedder.fingerprint())

    # Create search use case
    search_usecase = SearchUseCase(
        text_search=fts,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )

    # Perform search
    with caplog.at_level(logging.WARNING):
        query = Query(text="def test", topk=10)
        results = search_usecase.search(query)

    # Should return results
    assert len(results) > 0

    # Should NOT have any missing chunks warnings
    missing_chunks_warnings = [
        record for record in caplog.records
        if "Missing" in record.message and "chunks" in record.message
    ]
    assert len(missing_chunks_warnings) == 0, (
        f"Found unexpected missing chunks warning: "
        f"{[r.message for r in missing_chunks_warnings]}"
    )
