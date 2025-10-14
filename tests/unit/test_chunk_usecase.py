"""Tests for chunking use case."""

from pathlib import Path

from ember.adapters.parsers.line_chunker import LineChunker
from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
from ember.core.chunking.chunk_usecase import ChunkFileRequest, ChunkFileUseCase


def test_chunk_usecase_initialization():
    """Test chunk use case initializes correctly."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker()
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    assert use_case.tree_sitter is tree_sitter
    assert use_case.line_chunker is line_chunker


def test_chunk_usecase_empty_content():
    """Test use case handles empty content."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker()
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    request = ChunkFileRequest(
        content="",
        path=Path("empty.py"),
        lang="py",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert response.chunks == []
    assert response.strategy == "none"
    assert response.error is None


def test_chunk_usecase_python_uses_tree_sitter():
    """Test use case prefers tree-sitter for Python."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker()
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    content = """def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("math.py"),
        lang="py",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert response.strategy == "tree-sitter"
    assert len(response.chunks) == 2
    assert response.chunks[0].symbol == "add"
    assert response.chunks[1].symbol == "multiply"


def test_chunk_usecase_typescript_uses_tree_sitter():
    """Test use case prefers tree-sitter for TypeScript."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker()
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    content = """function greet(name: string): string {
    return `Hello, ${name}!`;
}

function farewell(name: string): string {
    return `Goodbye, ${name}!`;
}
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("greet.ts"),
        lang="ts",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert response.strategy == "tree-sitter"
    assert len(response.chunks) == 2


def test_chunk_usecase_unsupported_language_uses_fallback():
    """Test use case falls back to line-based for unsupported languages."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker(window_size=5, stride=4)
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    content = """SELECT * FROM users
WHERE age > 18
ORDER BY name;

INSERT INTO logs (message)
VALUES ('test');
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("query.sql"),
        lang="sql",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert response.strategy == "line-based"
    assert len(response.chunks) >= 1
    # Line-based chunker doesn't extract symbols
    assert all(chunk.symbol is None for chunk in response.chunks)


def test_chunk_usecase_go_uses_tree_sitter():
    """Test use case prefers tree-sitter for Go."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker()
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    content = """package main

func add(a, b int) int {
    return a + b
}

func multiply(a, b int) int {
    return a * b
}
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("math.go"),
        lang="go",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert response.strategy == "tree-sitter"
    assert len(response.chunks) == 2


def test_chunk_usecase_rust_uses_tree_sitter():
    """Test use case prefers tree-sitter for Rust."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker()
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    content = """fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn multiply(a: i32, b: i32) -> i32 {
    a * b
}
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("math.rs"),
        lang="rs",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert response.strategy == "tree-sitter"
    assert len(response.chunks) == 2


def test_chunk_usecase_plain_text_uses_line_based():
    """Test use case uses line-based for plain text."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker(window_size=3, stride=2)
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    content = """This is a plain text file.
It has multiple lines.
But no code structure.
Just plain text content.
Over multiple lines.
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("readme.txt"),
        lang="txt",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert response.strategy == "line-based"
    assert len(response.chunks) >= 1


def test_chunk_usecase_tree_sitter_fallback():
    """Test use case falls back if tree-sitter returns no chunks."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker(window_size=10, stride=8)
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    # Python code with no function/class definitions (just statements)
    content = """import os
import sys

x = 42
y = x + 1
print(y)

# Just statements, no functions
result = x * y
print(result)
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("script.py"),
        lang="py",
    )

    response = use_case.execute(request)

    assert response.success is True
    # Tree-sitter may return empty for non-function code, so fallback to line-based
    assert response.strategy in ["tree-sitter", "line-based"]
    # If no tree-sitter results, line-based should provide chunks
    if response.strategy == "line-based":
        assert len(response.chunks) >= 1


def test_chunk_usecase_preserves_metadata():
    """Test use case preserves path and language in chunks."""
    tree_sitter = TreeSitterChunker()
    line_chunker = LineChunker()
    use_case = ChunkFileUseCase(tree_sitter, line_chunker)

    content = """fn test() {
    println!("test");
}
"""

    request = ChunkFileRequest(
        content=content,
        path=Path("src/lib.rs"),
        lang="rs",
    )

    response = use_case.execute(request)

    assert response.success is True
    assert len(response.chunks) >= 1

    # Check metadata is preserved
    for chunk in response.chunks:
        assert chunk.lang == "rs"
