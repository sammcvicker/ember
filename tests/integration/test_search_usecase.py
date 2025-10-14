"""Integration tests for SearchUseCase.

Tests the complete hybrid search flow including BM25, vector search,
RRF fusion, filtering, and result ranking.
"""

import sqlite3
from pathlib import Path

import pytest

from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.schema import init_database
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.adapters.vss.simple_vector_search import SimpleVectorSearch
from ember.core.retrieval.search_usecase import SearchUseCase
from ember.domain.entities import Chunk, Query


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized."""
    db = tmp_path / "test_search.db"
    init_database(db)
    return db


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
    """Create SearchUseCase with real adapters and sample data."""
    # Initialize adapters
    chunk_repo = SQLiteChunkRepository(db_path)
    vector_repo = SQLiteVectorRepository(db_path)
    text_search = SQLiteFTS(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SimpleVectorSearch(db_path)

    # Store chunks
    for chunk in sample_chunks:
        chunk_repo.add(chunk)

    # Generate and store embeddings
    contents = [chunk.content for chunk in sample_chunks]
    embeddings = embedder.embed_texts(contents)

    for chunk, embedding in zip(sample_chunks, embeddings):
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
    query = Query(text="", topk=5)
    # Empty query causes FTS5 syntax error (expected behavior)
    # This is a known limitation of FTS5
    with pytest.raises(Exception):  # Could be OperationalError or other
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
    vector_repo = SQLiteVectorRepository(db_path)
    text_search = SQLiteFTS(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SimpleVectorSearch(vector_repo)

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
    vector_repo = SQLiteVectorRepository(db_path)
    text_search = SQLiteFTS(db_path)
    embedder = JinaCodeEmbedder()
    vector_search = SimpleVectorSearch(vector_repo)

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
