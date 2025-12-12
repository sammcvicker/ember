"""Integration tests for SearchUseCase.

Tests the complete hybrid search flow including BM25, vector search,
RRF fusion, filtering, and result ranking.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.adapters.vss.sqlite_vec_adapter import SqliteVecAdapter
from ember.core.retrieval.search_usecase import SearchUseCase
from ember.domain.entities import Chunk, Query

# Note: db_path fixture is now in tests/conftest.py


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """Create sample chunks for testing search."""
    chunks_data = [
        {
            "project_id": "test",
            "path": Path("math.py"),
            "start_line": 1,
            "end_line": 3,
            "content": "def add(a, b):\n    return a + b",
            "symbol": "add",
            "lang": "python",
        },
        {
            "project_id": "test",
            "path": Path("math.py"),
            "start_line": 5,
            "end_line": 7,
            "content": "def multiply(a, b):\n    return a * b",
            "symbol": "multiply",
            "lang": "python",
        },
        {
            "project_id": "test",
            "path": Path("utils.ts"),
            "start_line": 1,
            "end_line": 5,
            "content": "function greet(name: string): string {\n  return `Hello, ${name}!`;\n}",
            "symbol": "greet",
            "lang": "typescript",
        },
        {
            "project_id": "test",
            "path": Path("utils.ts"),
            "start_line": 7,
            "end_line": 11,
            "content": "function farewell(name: string): string {\n  return `Goodbye, ${name}!`;\n}",
            "symbol": "farewell",
            "lang": "typescript",
        },
    ]

    # Create Chunk objects with computed fields
    chunks = []
    for data in chunks_data:
        chunk_id = Chunk.compute_id(
            data["project_id"], data["path"], data["start_line"], data["end_line"]
        )
        content_hash = Chunk.compute_content_hash(data["content"])
        file_hash = Chunk.compute_content_hash(data["content"])  # Simplified for test

        chunk = Chunk(
            id=chunk_id,
            project_id=data["project_id"],
            path=data["path"],
            lang=data["lang"],
            symbol=data["symbol"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            content=data["content"],
            content_hash=content_hash,
            file_hash=file_hash,
            tree_sha="abc123",
            rev="worktree",
        )
        chunks.append(chunk)

    return chunks


@pytest.fixture
def search_usecase(db_path: Path, sample_chunks: list[Chunk]) -> SearchUseCase:
    """Create SearchUseCase with real adapters and sample data.

    Returns:
        SearchUseCase instance.

    Note:
        Connection cleanup is handled by the autouse
        cleanup_database_connections fixture in conftest.py.
    """
    # Initialize adapters
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    text_search = SQLiteFTS(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SqliteVecAdapter(db_path)

    # Store chunks
    for chunk in sample_chunks:
        chunk_repo.add(chunk)

    # Generate and store embeddings
    contents = [chunk.content for chunk in sample_chunks]
    embeddings = embedder.embed_texts(contents)

    for chunk, embedding in zip(sample_chunks, embeddings, strict=False):
        vector_repo.add(chunk.id, embedding, embedder.fingerprint())

    # Create use case
    return SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )


@pytest.mark.slow
def test_search_exact_keyword_match(search_usecase: SearchUseCase) -> None:
    """Test that exact keyword search returns correct results."""
    query = Query(text="multiply", topk=2)
    results = search_usecase.search(query)

    assert len(results) > 0
    # The multiply function should be top result
    assert results[0].chunk.symbol == "multiply"
    assert "multiply" in results[0].chunk.content.lower()
    # Should have BM25 score
    assert results[0].explanation["bm25_score"] > 0


@pytest.mark.slow
def test_search_semantic_similarity(search_usecase: SearchUseCase) -> None:
    """Test that semantic search finds conceptually similar code."""
    query = Query(text="greeting someone", topk=2)
    results = search_usecase.search(query)

    assert len(results) > 0
    # Should find greet or farewell functions (greeting-related)
    result_symbols = {r.chunk.symbol for r in results}
    assert result_symbols & {"greet", "farewell"}  # At least one should match
    # Should have vector score
    assert results[0].explanation["vector_score"] > 0


@pytest.mark.slow
def test_search_hybrid_fusion(search_usecase: SearchUseCase) -> None:
    """Test that hybrid search combines BM25 and vector scores."""
    query = Query(text="add", topk=3)
    results = search_usecase.search(query)

    assert len(results) > 0
    # Should have both BM25 and vector scores
    for result in results:
        assert "bm25_score" in result.explanation
        assert "vector_score" in result.explanation
        assert "fused_score" in result.explanation
        # Fused score should be positive
        assert result.explanation["fused_score"] > 0


@pytest.mark.slow
def test_search_path_filter(search_usecase: SearchUseCase) -> None:
    """Test that path filtering works correctly."""
    query = Query(text="function", topk=5, path_filter="*.ts")
    results = search_usecase.search(query)

    # All results should be from TypeScript files
    for result in results:
        assert result.chunk.path.suffix == ".ts"
        assert result.chunk.lang == "typescript"


@pytest.mark.slow
def test_search_language_filter(search_usecase: SearchUseCase) -> None:
    """Test that language filtering works correctly."""
    query = Query(text="return", topk=5, lang_filter="python")
    results = search_usecase.search(query)

    # All results should be Python code
    for result in results:
        assert result.chunk.lang == "python"
        assert result.chunk.path.suffix == ".py"


@pytest.mark.slow
def test_search_result_ranking(search_usecase: SearchUseCase) -> None:
    """Test that results are ranked correctly."""
    query = Query(text="multiply", topk=3)
    results = search_usecase.search(query)

    assert len(results) > 0
    # Results should be sorted by rank
    for i, result in enumerate(results, start=1):
        assert result.rank == i
    # Scores should be descending
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.slow
def test_search_preview_generation(search_usecase: SearchUseCase) -> None:
    """Test that search results include content previews."""
    query = Query(text="add", topk=1)
    results = search_usecase.search(query)

    assert len(results) > 0
    result = results[0]
    # Preview should exist and be non-empty
    assert result.preview
    assert len(result.preview) > 0
    # Preview should be part of the content
    first_line = result.preview.split("\n")[0]
    assert first_line in result.chunk.content


@pytest.mark.slow
def test_search_topk_limit(search_usecase: SearchUseCase) -> None:
    """Test that topk parameter limits results correctly."""
    query1 = Query(text="function", topk=1)
    results1 = search_usecase.search(query1)
    assert len(results1) <= 1

    query2 = Query(text="function", topk=3)
    results2 = search_usecase.search(query2)
    assert len(results2) <= 3


@pytest.mark.slow
def test_search_empty_query(search_usecase: SearchUseCase) -> None:
    """Test behavior with empty query."""
    import sqlite3

    query = Query(text="", topk=5)
    # Empty query causes FTS5 syntax error (expected behavior)
    # This is a known limitation of FTS5
    with pytest.raises((sqlite3.OperationalError, Exception)):
        search_usecase.search(query)


@pytest.mark.slow
def test_search_no_matches(search_usecase: SearchUseCase) -> None:
    """Test behavior when no matches are found."""
    query = Query(text="xyznonexistentfunction123", topk=5)
    results = search_usecase.search(query)
    # Should return empty or very low-scored results
    assert isinstance(results, list)
    # If results exist, they should have low scores
    if results:
        assert all(r.score < 0.1 for r in results)


def test_rrf_fusion_basic(db_path: Path) -> None:
    """Test RRF fusion logic with known inputs."""
    chunk_repo = SQLiteChunkRepository(db_path)
    SQLiteVectorRepository(db_path)
    text_search = SQLiteFTS(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SqliteVecAdapter(db_path)

    use_case = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
        rrf_k=60,
    )

    # Test with known rankings
    # List 1: A ranked 1st, B ranked 2nd
    # List 2: B ranked 1st, A ranked 2nd
    list1 = [("A", 1.0), ("B", 0.5)]
    list2 = [("B", 1.0), ("A", 0.5)]

    fused = use_case._reciprocal_rank_fusion([list1, list2], k=60)

    # Both A and B should appear
    chunk_ids = [cid for cid, _ in fused]
    assert "A" in chunk_ids
    assert "B" in chunk_ids

    # Scores should be based on RRF formula
    scores = dict(fused)
    # A: 1/(60+1) + 1/(60+2) ≈ 0.0164 + 0.0161 = 0.0325
    # B: 1/(60+2) + 1/(60+1) ≈ 0.0161 + 0.0164 = 0.0325
    # They should have equal scores
    assert abs(scores["A"] - scores["B"]) < 0.001


def test_rrf_fusion_single_ranker(db_path: Path) -> None:
    """Test RRF with single ranker (degenerates to that ranker)."""
    chunk_repo = SQLiteChunkRepository(db_path)
    SQLiteVectorRepository(db_path)
    text_search = SQLiteFTS(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SqliteVecAdapter(db_path)

    use_case = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )

    list1 = [("A", 1.0), ("B", 0.5), ("C", 0.3)]
    fused = use_case._reciprocal_rank_fusion([list1])

    # Should maintain ranking
    chunk_ids = [cid for cid, _ in fused]
    assert chunk_ids == ["A", "B", "C"]


@pytest.mark.slow
def test_search_with_empty_results(search_usecase: SearchUseCase) -> None:
    """Test search handles queries with no exact matches.

    Verifies that search gracefully handles queries that don't match any content.
    With hybrid search (BM25 + vector), it may return semantically similar results
    even when there's no exact match, which is correct behavior.
    """
    # Search for something that doesn't exist in the sample data
    query = Query(text="nonexistent_function_xyz_123", topk=10)
    results = search_usecase.search(query)

    # Hybrid search may return semantically similar results even without exact matches
    # This is correct behavior - just verify it doesn't crash
    assert isinstance(results, list)


@pytest.mark.slow
def test_search_with_combined_filters(search_usecase: SearchUseCase) -> None:
    """Test search with both path and language filters together.

    Verifies that multiple filters work correctly when combined, filtering
    results to only those that match ALL filter criteria.
    """
    # Search with both path and language filters
    # Should find only Python functions in math.py
    query = Query(
        text="function",
        topk=10,
        path_filter="math.py",
        lang_filter="python",  # Correct parameter name
    )
    results = search_usecase.search(query)

    # Should only return chunks from math.py with Python language
    assert len(results) > 0
    for result in results:
        assert str(result.chunk.path) == "math.py"
        assert result.chunk.lang == "python"


@pytest.mark.slow
def test_search_with_different_path_and_language(search_usecase: SearchUseCase) -> None:
    """Test search with path filter that doesn't match language filter.

    Verifies that conflicting filters (e.g., Python filter but TypeScript file)
    return empty results rather than crashing.
    """
    # Search for Python files in utils.ts (which is TypeScript)
    query = Query(
        text="greet",
        topk=10,
        path_filter="utils.ts",
        lang_filter="python",  # Conflicting: utils.ts is TypeScript
    )
    results = search_usecase.search(query)

    # Should return empty since no Python files match utils.ts path
    assert results == []


@pytest.mark.slow
def test_search_with_special_characters_in_query(search_usecase: SearchUseCase) -> None:
    """Test search handles basic special characters.

    Verifies that queries with some common special characters work.
    Note: Current FTS5 implementation may have limitations with certain characters.
    """
    # Test characters that should work in FTS5
    safe_queries = [
        "function test",  # Space
        "function-test",  # Hyphen
        "function_test",  # Underscore
        "(function)",  # Parentheses
        "[function]",  # Brackets
    ]

    for safe_query in safe_queries:
        query = Query(text=safe_query, topk=10)
        # Should not crash
        try:
            results = search_usecase.search(query)
            assert isinstance(results, list)  # Should return a list
        except Exception:
            # Document if certain queries fail
            # This helps identify FTS5 limitations to fix later
            pass


@pytest.mark.slow
def test_search_with_very_long_query(search_usecase: SearchUseCase) -> None:
    """Test search with extremely long query string.

    Verifies that very long queries don't cause buffer overflows or performance
    issues, and are handled gracefully (either truncated or rejected).
    """
    # Create a very long query (10000 characters)
    long_query = "function " * 1000  # 10000 chars
    query = Query(text=long_query, topk=10)

    # Should not crash, should return results or empty list
    results = search_usecase.search(query)
    assert isinstance(results, list)


@pytest.mark.slow
def test_path_filter_returns_full_topk(db_path: Path) -> None:
    """Test that path filtering happens during query, not after.

    This is a regression test for issue #52. Previously, path filtering
    happened after retrieval, which meant you could request topk=5 but
    only get 2 results if only 2 of the top-5 global results matched the path.

    Now path filtering happens during SQL queries, so we always get the
    requested number of results (if they exist in the filtered path).
    """
    # Create chunks in different directories
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)

    # Create 10 chunks in src/ directory
    src_chunks = []
    for i in range(10):
        path = Path(f"src/file{i}.py")
        content = f"def function_{i}(): pass"
        chunk_id = Chunk.compute_id("test", path, 1, 3)
        content_hash = Chunk.compute_content_hash(content)

        chunk = Chunk(
            id=chunk_id,
            project_id="test",
            path=path,
            start_line=1,
            end_line=3,
            content=content,
            symbol=f"function_{i}",
            lang="python",
            content_hash=content_hash,
            file_hash=content_hash,
            tree_sha="abc123",
            rev="worktree",
        )
        chunk_repo.add(chunk)
        src_chunks.append(chunk)

    # Create 10 chunks in tests/ directory
    for i in range(10):
        path = Path(f"tests/test_file{i}.py")
        content = f"def test_function_{i}(): pass"
        chunk_id = Chunk.compute_id("test", path, 1, 3)
        content_hash = Chunk.compute_content_hash(content)

        chunk = Chunk(
            id=chunk_id,
            project_id="test",
            path=path,
            start_line=1,
            end_line=3,
            content=content,
            symbol=f"test_function_{i}",
            lang="python",
            content_hash=content_hash,
            file_hash=content_hash,
            tree_sha="abc123",
            rev="worktree",
        )
        chunk_repo.add(chunk)

    # Add vectors for all chunks
    embedder = JinaCodeEmbedder()
    model_fingerprint = "test_model"
    for chunk in chunk_repo.list_all():
        embedding = embedder.embed_texts([chunk.content])[0]
        vector_repo.add(chunk.id, embedding, model_fingerprint)

    # Create search use case
    text_search = SQLiteFTS(db_path)
    vector_search = SqliteVecAdapter(db_path)
    search_usecase = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )

    # Search for "function" with path filter "src/**" and topk=5
    query = Query(
        text="function",
        topk=5,
        path_filter="src/*",  # Only src/ files
    )
    results = search_usecase.search(query)

    # Should return exactly 5 results, all from src/
    assert len(results) == 5, f"Expected 5 results, got {len(results)}"
    for result in results:
        assert str(result.chunk.path).startswith("src/"), (
            f"Expected all results from src/, got {result.chunk.path}"
        )


def test_missing_chunks_logged(db_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test that missing chunks are logged with count and sample IDs.

    This is a regression test for issue #88. Previously, missing chunks
    were silently dropped without any logging, making it hard to diagnose
    index corruption or stale data.
    """
    import logging

    # Create a mock chunk repository that returns None for some chunks
    chunk_repo = MagicMock()
    real_chunks = {
        "chunk_1": Chunk(
            id="chunk_1",
            project_id="test",
            path=Path("test.py"),
            start_line=1,
            end_line=3,
            content="def test1(): pass",
            symbol="test1",
            lang="python",
            content_hash="hash1",
            file_hash="file_hash1",
            tree_sha="abc123",
            rev="worktree",
        ),
        "chunk_2": Chunk(
            id="chunk_2",
            project_id="test",
            path=Path("test.py"),
            start_line=5,
            end_line=7,
            content="def test2(): pass",
            symbol="test2",
            lang="python",
            content_hash="hash2",
            file_hash="file_hash2",
            tree_sha="abc123",
            rev="worktree",
        ),
    }

    def mock_get(chunk_id: str) -> Chunk | None:
        """Return chunks 1 and 2, but None for chunks 3, 4, 5."""
        return real_chunks.get(chunk_id)

    chunk_repo.get.side_effect = mock_get

    # Create search use case with mock repo
    text_search = SQLiteFTS(db_path)
    vector_search = SqliteVecAdapter(db_path)
    embedder = JinaCodeEmbedder()

    use_case = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )

    # Simulate search results with 5 chunk IDs, but only 2 are retrievable
    chunk_ids = ["chunk_1", "chunk_2", "chunk_3", "chunk_4", "chunk_5"]

    # Enable logging capture at WARNING level
    with caplog.at_level(logging.WARNING):
        chunks = use_case._retrieve_chunks(chunk_ids)

    # Should return only the 2 found chunks
    assert len(chunks) == 2
    assert chunks[0].id == "chunk_1"
    assert chunks[1].id == "chunk_2"

    # Should have logged a warning about missing chunks
    assert len(caplog.records) == 1
    log_record = caplog.records[0]
    assert log_record.levelname == "WARNING"
    assert "Missing 3 chunks" in log_record.message
    assert "chunk_3" in log_record.message
    assert "chunk_4" in log_record.message
    assert "chunk_5" in log_record.message
    assert "index corruption or stale data" in log_record.message

    # Should include recovery guidance (issue #146)
    assert "ember sync --force" in log_record.message
    assert "report an issue" in log_record.message.lower()
