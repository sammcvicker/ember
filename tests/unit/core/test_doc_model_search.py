from pathlib import Path
from unittest.mock import Mock
import pytest
from ember.core.retrieval.search_usecase import SearchUseCase
from ember.domain.entities import Query, Chunk


@pytest.fixture
def mock_embedder() -> Mock:
    embedder = Mock()
    embedder.fingerprint.return_value = "code-model-fingerprint"
    embedder.embed_texts.return_value = [[0.1] * 768]
    return embedder


@pytest.fixture
def mock_doc_embedder() -> Mock:
    doc_embedder = Mock()
    doc_embedder.fingerprint.return_value = "doc-model-fingerprint"
    doc_embedder.embed_texts.return_value = [[0.2] * 768]
    return doc_embedder


@pytest.fixture
def mock_deps(mock_embedder, mock_doc_embedder) -> dict:
    text_search = Mock()
    text_search.query.return_value = []

    vector_search = Mock()
    vector_search.query.side_effect = lambda vector, topk, path_filter, model_fingerprint: (
        [("chunk-code-1", 0.9)] if model_fingerprint == "code-model-fingerprint" else [("chunk-doc-1", 0.85)]
    )

    chunk_repo = Mock()
    chunk_repo.get.side_effect = lambda cid: Chunk(
        id=cid,
        project_id="p1",
        path=Path("app.py" if "code" in cid else "README.md"),
        lang="py" if "code" in cid else "txt",
        symbol=None,
        start_line=1,
        end_line=10,
        content="test code" if "code" in cid else "test doc",
        content_hash="hash",
        file_hash="fhash",
        tree_sha="sha",
        rev="worktree",
    )

    meta_repo = Mock()
    meta_repo.get.side_effect = lambda key: "doc-model-fingerprint" if key == "doc_model_fingerprint" else None

    return {
        "text_search": text_search,
        "vector_search": vector_search,
        "chunk_repo": chunk_repo,
        "embedder": mock_embedder,
        "doc_embedder": mock_doc_embedder,
        "meta_repo": meta_repo,
    }


def test_search_queries_both_vector_spaces(mock_deps):
    """Verify SearchUseCase embeds twice and queries vector search twice for different models."""
    usecase = SearchUseCase(**mock_deps)

    query = Query(text="test query", topk=5)
    results = usecase.search(query)

    # Verify embedders called
    mock_deps["embedder"].embed_texts.assert_called_once_with(["test query"])
    mock_deps["doc_embedder"].embed_texts.assert_called_once_with(["test query"])

    # Verify vector search called twice with correct fingerprints
    assert mock_deps["vector_search"].query.call_count == 2
    mock_deps["vector_search"].query.assert_any_call(
        [0.1] * 768,
        topk=100,
        path_filter=None,
        model_fingerprint="code-model-fingerprint",
    )
    mock_deps["vector_search"].query.assert_any_call(
        [0.2] * 768,
        topk=100,
        path_filter=None,
        model_fingerprint="doc-model-fingerprint",
    )

    # Verify both code and doc chunks are returned in results
    chunk_ids = [r.chunk.id for r in results]
    assert "chunk-code-1" in chunk_ids
    assert "chunk-doc-1" in chunk_ids
