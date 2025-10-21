# Test Suite Fixes - Code Examples

## Issue 1: Test Isolation with os.chdir()

### Current Problem
File: `tests/integration/test_auto_sync.py` (appears in ALL test functions)

```python
def test_auto_sync_on_stale_index(auto_sync_repo: Path) -> None:
    """Test that find auto-syncs when index is stale."""
    import os
    from click.testing import CliRunner
    from ember.entrypoints.cli import find

    # Modify file to make index stale
    test_file = auto_sync_repo / "test.py"
    test_file.write_text("def foo(): pass\ndef bar(): pass\n")
    subprocess.run([...], cwd=auto_sync_repo, check=True, capture_output=True)
    
    # PROBLEM: Manual cwd handling
    cwd = os.getcwd()  # Line 67
    os.chdir(auto_sync_repo)  # Line 88 - Global state mutation!
    try:
        runner = CliRunner()
        result = runner.invoke(find, ["function"], obj={}, catch_exceptions=False)
    finally:
        os.chdir(cwd)  # Line 95 - What if try block crashes before this?
```

**Risks:**
- If `runner.invoke()` raises an exception → `os.chdir(cwd)` never runs
- Working directory stays corrupted
- All subsequent tests run in wrong directory
- Tests cannot run in parallel

---

### Fix: Use pytest.monkeypatch

```python
@pytest.fixture
def auto_sync_chdir(monkeypatch, auto_sync_repo):
    """Fixture to safely change to auto_sync_repo."""
    monkeypatch.chdir(auto_sync_repo)
    return auto_sync_repo


def test_auto_sync_on_stale_index(auto_sync_chdir: Path) -> None:
    """Test that find auto-syncs when index is stale."""
    from click.testing import CliRunner
    from ember.entrypoints.cli import find

    # No os.chdir needed - monkeypatch handles it
    # monkeypatch automatically restores even if test fails
    
    # Modify file to make index stale
    test_file = auto_sync_chdir / "test.py"
    test_file.write_text("def foo(): pass\ndef bar(): pass\n")
    subprocess.run(["git", "add", "."], cwd=auto_sync_chdir, timeout=5, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add bar"], cwd=auto_sync_chdir, timeout=5, capture_output=True)

    # Run find - should auto-sync
    runner = CliRunner()
    result = runner.invoke(find, ["function"], obj={}, catch_exceptions=False)

    assert result.exit_code == 0
    assert "bar" in result.stdout
```

**Benefits:**
- ✓ Automatic cleanup even on exception
- ✓ Tests can run in parallel
- ✓ No manual try/finally needed
- ✓ Cleaner code

---

## Issue 2: Missing Subprocess Timeouts

### Current Problem
```python
# test_auto_sync.py, line 16-39
subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
subprocess.run(
    ["git", "config", "user.email", "test@test.com"],
    cwd=repo,
    check=True,
    capture_output=True,
)
# If git hangs → test hangs → CI times out at 10+ minutes
```

**Found 47 instances across tests** (lines to fix are marked with comments)

---

### Fix: Add timeout to ALL subprocess calls

**Global find and replace pattern:**
```bash
# Find all subprocess.run() calls
grep -n "subprocess.run" tests/ -r --include="*.py"

# Add timeout=5 to each
# OLD: subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
# NEW: subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, timeout=5)
```

**Affected files (count of calls):**
- `tests/integration/test_indexing_usecase.py`: 6 calls
- `tests/integration/test_auto_sync.py`: 15 calls  
- `tests/integration/test_git_adapter.py`: 12 calls
- `tests/performance/test_performance.py`: 8 calls
- `tests/integration/test_init.py`: 6 calls

**Example fix:**
```python
# BEFORE
subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)

# AFTER
subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, timeout=5)
```

---

## Issue 3: Error Paths Not Tested

### Missing: File Read Errors in IndexingUseCase

**Create new file: `tests/unit/test_indexing_errors.py`**

```python
"""Tests for error handling in IndexingUseCase."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from ember.core.indexing.index_usecase import IndexingUseCase, IndexRequest


def test_indexing_handles_file_read_error():
    """Test IndexingUseCase gracefully handles file read errors."""
    # Setup mocks
    vcs = Mock()
    fs = Mock()
    chunk_usecase = Mock()
    embedder = Mock()
    chunk_repo = Mock()
    vector_repo = Mock()
    file_repo = Mock()
    meta_repo = Mock()
    
    # Configure returns
    vcs.get_worktree_tree_sha.return_value = "abc123"
    vcs.list_tracked_files.return_value = ["file1.py", "file2.py"]
    
    # Simulate file system error
    fs.read.side_effect = PermissionError("Permission denied")
    
    # Create use case
    usecase = IndexingUseCase(
        vcs=vcs, fs=fs, chunk_usecase=chunk_usecase,
        embedder=embedder, chunk_repo=chunk_repo,
        vector_repo=vector_repo, file_repo=file_repo,
        meta_repo=meta_repo, project_id="test"
    )
    
    # Execute
    repo_root = Path("/fake/repo")
    request = IndexRequest(repo_root=repo_root, force_reindex=True)
    response = usecase.execute(request)
    
    # VERIFY: Should handle error gracefully
    assert response.success is False
    assert "Permission denied" in response.error
    # Index should not be corrupted
    assert response.chunks_created == 0


def test_indexing_handles_embedder_failure():
    """Test IndexingUseCase handles embedder batch failures."""
    vcs = Mock()
    fs = Mock()
    chunk_usecase = Mock()
    embedder = Mock()
    chunk_repo = Mock()
    vector_repo = Mock()
    file_repo = Mock()
    meta_repo = Mock()
    
    vcs.get_worktree_tree_sha.return_value = "abc123"
    vcs.list_tracked_files.return_value = ["file1.py"]
    
    # File reads OK
    fs.read.return_value = b"def foo(): pass"
    
    # Chunking works
    chunk_data = Mock()
    chunk_data.content = "def foo(): pass"
    chunk_data.start_line = 1
    chunk_data.end_line = 1
    chunk_data.symbol = "foo"
    chunk_data.lang = "py"
    
    chunk_response = Mock()
    chunk_response.success = True
    chunk_response.chunks = [chunk_data]
    chunk_usecase.execute.return_value = chunk_response
    
    # Embedder fails
    embedder.embed_texts.side_effect = RuntimeError("Model download failed")
    embedder.fingerprint.return_value = "fp123"
    
    usecase = IndexingUseCase(
        vcs=vcs, fs=fs, chunk_usecase=chunk_usecase,
        embedder=embedder, chunk_repo=chunk_repo,
        vector_repo=vector_repo, file_repo=file_repo,
        meta_repo=meta_repo, project_id="test"
    )
    
    request = IndexRequest(repo_root=Path("/fake/repo"), force_reindex=True)
    response = usecase.execute(request)
    
    # Should handle embedder error
    assert response.success is False
    assert "Model download failed" in response.error


def test_indexing_handles_partial_failure():
    """Test IndexingUseCase recovers from partial failures."""
    # File 1 succeeds, File 2 fails
    vcs = Mock()
    fs = Mock()
    
    vcs.get_worktree_tree_sha.return_value = "abc123"
    vcs.list_tracked_files.return_value = ["ok.py", "bad.py"]
    
    # First read OK, second fails
    fs.read.side_effect = [
        b"def good(): pass",
        PermissionError("No permission")
    ]
    
    # ... rest of setup ...
    
    # VERIFY: Should index first file successfully, skip second
    # (Implementation detail: how should it behave?)
```

---

### Missing: Search Error Paths

**Create new file: `tests/unit/test_search_errors.py`**

```python
"""Tests for error handling in SearchUseCase."""

import pytest
from unittest.mock import Mock

from ember.core.retrieval.search_usecase import SearchUseCase
from ember.domain.entities import Query


def test_search_handles_query_embedding_failure():
    """Test SearchUseCase handles embedder failures."""
    text_search = Mock()
    vector_search = Mock()
    chunk_repo = Mock()
    embedder = Mock()
    
    # Embedder fails
    embedder.embed_texts.side_effect = RuntimeError("Network error")
    
    use_case = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )
    
    query = Query(text="find me", topk=10)
    
    # Should raise or return error gracefully
    with pytest.raises(RuntimeError, match="Network error"):
        use_case.search(query)


def test_search_handles_empty_repository():
    """Test SearchUseCase with no chunks in database."""
    text_search = Mock()
    vector_search = Mock()
    chunk_repo = Mock()
    embedder = Mock()
    
    # All searches return empty
    text_search.query.return_value = []
    vector_search.query.return_value = []
    embedder.embed_texts.return_value = [[0.1, 0.2, ...]]
    
    use_case = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )
    
    query = Query(text="find me", topk=10)
    results = use_case.search(query)
    
    # Should return empty list gracefully
    assert results == []


def test_search_combined_filters_edge_case():
    """Test SearchUseCase with both path and language filters."""
    # This scenario currently untested
    text_search = Mock()
    vector_search = Mock()
    chunk_repo = Mock()
    embedder = Mock()
    
    # Setup test data...
    # (Would need realistic chunks)
    
    use_case = SearchUseCase(
        text_search=text_search,
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        embedder=embedder,
    )
    
    # Both filters active
    query = Query(
        text="function",
        topk=10,
        path_filter="src/**/*.py",
        lang_filter="python"
    )
    
    results = use_case.search(query)
    
    # All results should match BOTH filters
    for r in results:
        assert r.chunk.lang == "python"
        assert "src" in str(r.chunk.path)
```

---

## Issue 4: Fixture Duplication

### Current Problem: Multiple git_repo Fixtures

**Found in:**
- `tests/integration/test_indexing_usecase.py:27-75`
- `tests/integration/test_auto_sync.py:9-61`
- `tests/integration/test_git_adapter.py` (uses tmp_path)

Each has slightly different setup.

---

### Fix: Extract to conftest.py

**Update `tests/conftest.py`:**

```python
"""Pytest configuration and shared fixtures."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from ember.domain.entities import Chunk


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def git_repo_simple(tmp_path: Path) -> Path:
    """Create a minimal git repo with 2 Python files."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root, check=True, capture_output=True, timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root, check=True, capture_output=True, timeout=5,
    )

    # Create test files
    (repo_root / "math.py").write_text("""def add(a, b):
    '''Add two numbers.'''
    return a + b

def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b
""")
    (repo_root / "utils.py").write_text("""def greet(name):
    '''Greet someone.'''
    return f"Hello, {name}!"
""")

    # Commit
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_root, check=True, capture_output=True, timeout=5,
    )

    return repo_root


@pytest.fixture
def git_repo_complex(tmp_path: Path) -> Path:
    """Create a complex git repo with multiple files and directories."""
    repo_root = tmp_path / "complex_repo"
    repo_root.mkdir()

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root, check=True, capture_output=True, timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root, check=True, capture_output=True, timeout=5,
    )

    # Create directory structure
    (repo_root / "src").mkdir()
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "lib.py").write_text("""
class Calculator:
    def add(self, a, b):
        return a + b
    
    def multiply(self, a, b):
        return a * b
""")
    (repo_root / "tests" / "test_lib.py").write_text("""
def test_add():
    assert True

def test_multiply():
    assert True
""")

    # Commit
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_root, check=True, capture_output=True, timeout=5,
    )

    return repo_root


# Existing fixtures...
@pytest.fixture
def sample_chunk() -> Chunk:
    """Create a sample chunk for testing."""
    return Chunk(...)  # existing implementation


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """Create multiple sample chunks for testing."""
    # existing implementation
    ...
```

---

### Usage in Tests

**Before (test_indexing_usecase.py):**
```python
@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a git repository with test files."""
    # Duplicate setup code (40+ lines)
    ...

def test_full_index(indexing_usecase: IndexingUseCase, git_repo: Path, db_path: Path) -> None:
    request = IndexRequest(repo_root=git_repo, force_reindex=True)
    ...
```

**After:**
```python
def test_full_index(
    indexing_usecase: IndexingUseCase, 
    git_repo_simple: Path,  # Use conftest fixture
    db_path: Path
) -> None:
    request = IndexRequest(repo_root=git_repo_simple, force_reindex=True)
    ...
```

---

## Summary of Fixes

| Issue | File | Changes | Time |
|-------|------|---------|------|
| os.chdir isolation | test_auto_sync.py | Use monkeypatch fixture (5 functions) | 10min |
| Subprocess timeout | All test files | Add timeout=5 (47 calls) | 15min |
| Error paths | New files (2) | 20-30 error tests | 2hrs |
| Fixture extraction | conftest.py + tests | Move 4+ fixture defs | 30min |
| **TOTAL** | | | **3hrs** |

**Expected improvement:** 44% → 55-60% coverage, fix all isolation issues
