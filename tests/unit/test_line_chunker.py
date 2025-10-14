"""Tests for line-based chunker."""

from pathlib import Path

import pytest

from ember.adapters.parsers.line_chunker import LineChunker


def test_line_chunker_initialization():
    """Test line chunker initializes with correct defaults."""
    chunker = LineChunker()
    assert chunker.window_size == 120
    assert chunker.stride == 100


def test_line_chunker_custom_params():
    """Test line chunker with custom parameters."""
    chunker = LineChunker(window_size=50, stride=40)
    assert chunker.window_size == 50
    assert chunker.stride == 40


def test_line_chunker_invalid_params():
    """Test line chunker rejects invalid parameters."""
    with pytest.raises(ValueError, match="window_size must be positive"):
        LineChunker(window_size=0, stride=10)

    with pytest.raises(ValueError, match="stride must be positive"):
        LineChunker(window_size=10, stride=0)

    with pytest.raises(ValueError, match="stride cannot exceed window_size"):
        LineChunker(window_size=10, stride=20)


def test_line_chunker_supported_languages():
    """Test line chunker supports all languages (universal fallback)."""
    chunker = LineChunker()
    # Empty set means universal support
    assert chunker.supported_languages == set()


def test_line_chunker_empty_content():
    """Test line chunker returns empty list for empty content."""
    chunker = LineChunker()
    chunks = chunker.chunk_file("", Path("test.py"), "py")
    assert chunks == []

    chunks = chunker.chunk_file("   \n\n  ", Path("test.py"), "py")
    assert chunks == []


def test_line_chunker_small_file():
    """Test line chunker returns single chunk for small files."""
    chunker = LineChunker(window_size=120, stride=100)
    content = "\n".join([f"line {i}" for i in range(1, 51)])  # 50 lines

    chunks = chunker.chunk_file(content, Path("test.py"), "py")

    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 50
    assert chunks[0].content == content
    assert chunks[0].symbol is None
    assert chunks[0].lang == "py"


def test_line_chunker_exact_window_size():
    """Test line chunker with file exactly window size."""
    chunker = LineChunker(window_size=100, stride=80)
    content = "\n".join([f"line {i}" for i in range(1, 101)])  # 100 lines

    chunks = chunker.chunk_file(content, Path("test.py"), "py")

    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 100


def test_line_chunker_multiple_chunks():
    """Test line chunker creates multiple overlapping chunks."""
    chunker = LineChunker(window_size=10, stride=8)
    content = "\n".join([f"line {i}" for i in range(1, 26)])  # 25 lines

    chunks = chunker.chunk_file(content, Path("test.txt"), "txt")

    # Expected chunks:
    # Chunk 1: lines 1-10
    # Chunk 2: lines 9-18 (8 + 10)
    # Chunk 3: lines 17-25 (16 + 9, capped at 25)

    assert len(chunks) == 3

    # Check first chunk
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 10
    assert "line 1" in chunks[0].content
    assert "line 10" in chunks[0].content

    # Check second chunk (overlap with first)
    assert chunks[1].start_line == 9
    assert chunks[1].end_line == 18
    assert "line 9" in chunks[1].content
    assert "line 18" in chunks[1].content

    # Check third chunk (partial last window)
    assert chunks[2].start_line == 17
    assert chunks[2].end_line == 25
    assert "line 17" in chunks[2].content
    assert "line 25" in chunks[2].content


def test_line_chunker_no_overlap():
    """Test line chunker with stride equal to window_size (no overlap)."""
    chunker = LineChunker(window_size=10, stride=10)
    content = "\n".join([f"line {i}" for i in range(1, 31)])  # 30 lines

    chunks = chunker.chunk_file(content, Path("test.py"), "py")

    assert len(chunks) == 3

    # No overlap between chunks
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 10

    assert chunks[1].start_line == 11
    assert chunks[1].end_line == 20

    assert chunks[2].start_line == 21
    assert chunks[2].end_line == 30


def test_line_chunker_preserves_language():
    """Test line chunker preserves language identifier."""
    chunker = LineChunker()
    content = "def foo():\n    pass"

    chunks = chunker.chunk_file(content, Path("test.rs"), "rs")

    assert len(chunks) == 1
    assert chunks[0].lang == "rs"


def test_line_chunker_real_code_sample():
    """Test line chunker with real Python code."""
    chunker = LineChunker(window_size=5, stride=4)
    content = """def add(a, b):
    return a + b

def multiply(a, b):
    result = a * b
    return result

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b"""

    chunks = chunker.chunk_file(content, Path("math.py"), "py")

    # 11 lines total, window=5, stride=4
    # Chunk 1: 1-5
    # Chunk 2: 5-9
    # Chunk 3: 9-11
    assert len(chunks) == 3

    # Check first chunk contains first function
    assert "def add(a, b):" in chunks[0].content
    assert chunks[0].symbol is None  # Line chunker doesn't extract symbols
