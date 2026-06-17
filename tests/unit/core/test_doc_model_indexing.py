from pathlib import Path
from unittest.mock import Mock, call
import pytest
from ember.core.indexing.index_usecase import IndexingUseCase
from ember.domain.entities import Chunk
from ember.ports.chunkers import ChunkData
from ember.ports.embedders import Embedder
from ember.ports.progress import ProgressCallback
from ember.core.chunking.chunk_usecase import ChunkFileResponse


@pytest.fixture
def mock_embedder() -> Mock:
    embedder = Mock(spec=Embedder)
    embedder.fingerprint.return_value = "code-model-fingerprint"
    embedder.embed_texts.return_value = [[0.1] * 768]
    return embedder


@pytest.fixture
def mock_doc_embedder() -> Mock:
    doc_embedder = Mock(spec=Embedder)
    doc_embedder.fingerprint.return_value = "doc-model-fingerprint"
    doc_embedder.embed_texts.return_value = [[0.2] * 768]
    return doc_embedder


@pytest.fixture
def mock_deps(mock_embedder, mock_doc_embedder) -> dict:
    mock_chunk_usecase = Mock()
    mock_chunk_usecase.execute.return_value = ChunkFileResponse(
        success=True,
        strategy="tree-sitter",
        chunks=[
            ChunkData(
                start_line=1,
                end_line=5,
                content="test content",
                symbol=None,
                lang="py",
            )
        ]
    )

    return {
        "vcs": Mock(),
        "fs": Mock(),
        "chunk_usecase": mock_chunk_usecase,
        "embedder": mock_embedder,
        "doc_embedder": mock_doc_embedder,
        "chunk_repo": Mock(**{"find_by_content_hash.return_value": []}),
        "vector_repo": Mock(),
        "file_repo": Mock(),
        "meta_repo": Mock(),
        "project_id": "test_project",
    }


def test_indexing_routes_files_correctly(mock_deps):
    """Verify IndexingUseCase uses different embedders for code and doc files."""
    usecase = IndexingUseCase(**mock_deps)

    # Setup fs.read mocks
    mock_deps["fs"].read.side_effect = lambda path: b"test file content"

    # Index a python file
    py_path = Path("/repo/app.py")
    usecase._index_file(
        file_path=py_path,
        repo_root=Path("/repo"),
        tree_sha="tree1",
        sync_mode="worktree",
    )

    # Python file should use the main code embedder (called with chunk content)
    mock_deps["embedder"].embed_texts.assert_called_once_with(["test content"])
    mock_deps["doc_embedder"].embed_texts.assert_not_called()
    mock_deps["vector_repo"].add.assert_called_once()
    assert mock_deps["vector_repo"].add.call_args[1]["model_fingerprint"] == "code-model-fingerprint"

    # Reset mocks
    mock_deps["embedder"].reset_mock()
    mock_deps["doc_embedder"].reset_mock()
    mock_deps["vector_repo"].reset_mock()

    # Index a markdown file
    md_path = Path("/repo/README.md")
    usecase._index_file(
        file_path=md_path,
        repo_root=Path("/repo"),
        tree_sha="tree1",
        sync_mode="worktree",
    )

    # Markdown file should use the doc embedder (called with chunk content)
    mock_deps["doc_embedder"].embed_texts.assert_called_once_with(["test content"])
    mock_deps["embedder"].embed_texts.assert_not_called()
    mock_deps["vector_repo"].add.assert_called_once()
    assert mock_deps["vector_repo"].add.call_args[1]["model_fingerprint"] == "doc-model-fingerprint"
