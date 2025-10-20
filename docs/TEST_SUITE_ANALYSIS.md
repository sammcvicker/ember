# Ember Test Suite Analysis Report

## Executive Summary
- **Total Tests:** 122
- **Tests Passing:** 91 (when running standard suite)
- **Code Coverage:** 44% overall (key modules vary)
- **Test Duration:** ~1.5s (fast!)
- **Architecture:** Unit + Integration + Performance tests present

---

## 1. COVERAGE GAPS - Critical Issues

### 1.1 Core Use Cases - Incomplete Coverage

**IndexingUseCase (162 LOC, 25% coverage)**
- Missing coverage:
  - Lines 138-146: Path filter regex compilation & application
  - Lines 160-240: Error handling during file indexing
  - Lines 262-269: Language detection for various file types
  - Lines 290-327: Complex file-to-index logic with multiple branches
  - Lines 344-361: Deletion handling edge cases
  - Lines 382-465: Complex batch embedding logic
  - Lines 491-517: Chunk creation and ID computation
  - Lines 528-529, 541-559: Error recovery paths

**Untested scenarios:**
- ✗ File read errors (binary files, permission denied, encoding issues)
- ✗ Partial indexing failures (1 of 10 files fails)
- ✗ Embedder errors during batch operations
- ✗ Database transaction failures
- ✗ Path filter edge cases (special characters, unicode)
- ✗ Language detection for edge case extensions

---

**SearchUseCase (63 LOC, 38% coverage)**
- Missing coverage:
  - Lines 57-109: Complex hybrid search orchestration (embedding errors)
  - Lines 147-152: Chunk retrieval when chunks don't exist
  - Lines 170-182: Path/language filter combinations
  - Lines 196-199: Score computation edge cases
  - Lines 211-215: Preview generation with edge cases

**Untested scenarios:**
- ✗ Empty search results (no matches at all)
- ✗ Query embedding failures
- ✗ Combining multiple filters (path + language)
- ✗ RRF fusion with single ranker edge cases
- ✗ Very large result sets (>1000 chunks)
- ✗ Malformed queries causing FTS5 errors

---

**Repository Adapters (Significantly Undertested)**

*SQLiteChunkRepository (117 LOC, 14% coverage):*
- Lines 27-29: Initialization paths
- Lines 40-80: Basic CRUD operations not fully tested
- Lines 95-134: Content hash queries
- Lines 145-185: Path-based deletion operations  
- Lines 196-215: Batch operations
- Lines 230-247, 262-279, 292-308, 324-376: Complex query logic

Missing:
- ✗ Concurrent access patterns
- ✗ Database corruption recovery
- ✗ Large batch operations (1000+ chunks)
- ✗ Transaction rollback scenarios
- ✗ Constraint violation handling

*SQLiteVectorRepository (69 LOC, 20% coverage):*
- Missing vector search edge cases
- ✗ Cosine similarity accuracy verification
- ✗ Large embedding dimensions (1024D)
- ✗ Vector precision loss scenarios

*SQLiteFTS (27 LOC, 33% coverage):*
- Lines 31, 45, 58-98: Query execution paths
- Missing:
  - ✗ Special characters in queries
  - ✗ Very long queries (>1000 chars)
  - ✗ Unicode edge cases
  - ✗ FTS5 performance regressions

---

### 1.2 CLI / Integration Testing

**CLI Integration (0% coverage)**
- `/ember/entrypoints/cli.py`: 410 LOC, 0% coverage
- Reason: CLI tests use subprocess + CliRunner integration tests
- Problem: No unit tests for individual command logic

Missing:
- ✗ CLI error message formatting
- ✗ Invalid argument validation
- ✗ Exit code scenarios
- ✗ Output formatting edge cases
- ✗ Config loading failures in CLI context

---

### 1.3 Error Paths Not Tested

**No error scenario tests found for:**
- ✗ Git adapter errors (detached HEAD, shallow clone, submodules)
- ✗ File system errors (permission denied, path too long, disk full)
- ✗ Database errors (locked, corrupted, out of space)
- ✗ Embedding model errors (download failure, GPU OOM, invalid input)
- ✗ Config parsing errors (malformed TOML, missing required sections)
- ✗ Tree-sitter parsing errors (malformed code, unsupported language)

---

## 2. TEST QUALITY ISSUES

### 2.1 Test Isolation Problems

**auto_sync tests show pattern issues:**

File: `/tests/integration/test_auto_sync.py`

```python
# PROBLEM 1: os.chdir used multiple times
os.chdir(repo)  # Line 45
try:
    # ... test code ...
finally:
    os.chdir(cwd)  # Line 59

# This pattern repeated in EVERY TEST FUNCTION
# Issues:
# - Global state mutation (cwd)
# - If test crashes, cwd not restored
# - Tests can't run in parallel
# - Stack trace shows wrong working directory
```

**Risk:** If one test crashes before `os.chdir(cwd)`, all subsequent tests run in wrong directory!

**Better approach:**
```python
@pytest.fixture
def chdir_fixture(monkeypatch, auto_sync_repo):
    monkeypatch.chdir(auto_sync_repo)  # Auto-restores
    yield auto_sync_repo
```

---

**Filesystem pollution from subprocess:**

```python
# git operations not cleaned up properly
subprocess.run(["git", "add", "."], cwd=repo, ...)
subprocess.run(["git", "commit", ...], cwd=repo, ...)

# Problem: test_file modifications accumulate
# If test crashes, previous modifications remain
# Next test inherits dirty state
```

Count: 47 subprocess calls across tests - most have minimal cleanup

---

### 2.2 Fixture Reusability Issues

**Low reuse of fixtures:**

```
conftest.py provides:
- temp_dir (generic)
- sample_chunk (single chunk)
- sample_chunks (5 chunks)

But each test file creates its own:
- git_repo fixtures (test_indexing, test_auto_sync, test_git_adapter)
- db_path fixtures (test_search, test_indexing, test_init)
- search_usecase fixtures (test_search, test_auto_sync)
```

**Duplication count:**
- 4+ versions of git_repo fixture setup
- 3+ versions of database initialization
- 2+ versions of embedder initialization

**Maintenance burden:** When setup changes, must update 3-4 places

---

### 2.3 Slow Tests Not Properly Marked

**Test execution times show:**
```
0.09s test_get_worktree_tree_sha_with_unstaged_changes
0.08s test_get_file_content_at_head (setup only!)
0.07s test_diff_files_between_commits (setup only!)
```

**All marked as `@pytest.mark.slow` but:**
- Reason: git repo creation + subprocess calls
- Not true algorithmic slowness
- Could be optimized with fixtures

**Tests that SHOULD be marked slow but aren't:**
- `test_full_index` - Downloads embedding model
- `test_search_*` - Network embedding calls
- `test_incremental_sync_*` - Real git operations

---

### 2.4 Brittle Test Assertions

**Example from test_search_usecase.py:**
```python
# Line 137-138
assert results[0].chunk.symbol == "multiply"
assert "multiply" in results[0].chunk.content.lower()
```
**Brittle because:**
- Depends on exact RRF ranking
- Vector search non-deterministic (floating point)
- FTS5 relevance can change with query

**Should be:**
```python
result_symbols = {r.chunk.symbol for r in results}
assert "multiply" in result_symbols
```

---

**Example from test_auto_sync.py:**
```python
# Line 99
assert "Detected changes, syncing index" in result.stderr or "Synced" in result.stderr
```
**Brittle because:**
- Message format can change
- stderr vs stdout might change
- "or" condition masks real issues

---

### 2.5 Missing Timeout Handling

**Tests using subprocess without timeout:**
```python
subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
# If git hangs → entire test suite hangs!
```

**All 47 subprocess calls need timeout:**
```python
# Better:
subprocess.run(..., timeout=5)  # 5s max
```

---

## 3. TEST ORGANIZATION ISSUES

### 3.1 Unclear Test Categorization

**Current structure:**
```
tests/
  unit/
    test_chunk_usecase.py (268 LOC) - ✓ Pure unit
    test_line_chunker.py (169 LOC) - ✓ Pure unit  
    test_tree_sitter_chunker.py (522 LOC) - ✓ Pure unit
    test_config_provider.py (115 LOC) - ✓ Pure unit
    domain/test_entities.py (39 LOC) - ✓ Pure unit
  integration/
    test_indexing_usecase.py (369 LOC) - Mixed! Has subprocess
    test_search_usecase.py (319 LOC) - Mixed! Real embeddings
    test_auto_sync.py (220 LOC) - Mixed! CLI + subprocess
    test_git_adapter.py (240 LOC) - ✓ Real git (acceptable)
    test_init.py (172 LOC) - ✓ Acceptable
    test_jina_embedder.py (163 LOC) - Integration (downloads model)
  performance/
    test_performance.py (472 LOC) - Performance benchmarks
```

**Problems:**
- Some "integration" tests are actually E2E (CLI + Git + DB)
- No "slow" directory for grouped slow tests
- Performance tests mixed with functionality tests

---

### 3.2 Test Data Realism Issues

**Example - sample_chunks in test_search_usecase.py:**
```python
# Lines 32-69
chunks_data = [
    {
        "content": "def add(a, b):\n    return a + b",
        "symbol": "add",
        "lang": "python",
    },
    # ... only 4 chunks
]
```

**Problems:**
- Only 4 chunks (real repos have 100s-1000s)
- Perfect BM25/vector separation (unrealistic)
- No edge cases (empty functions, huge chunks, etc.)
- No duplicate/near-duplicate content

---

**Example - simple_git_repo setup:**
```python
# test_indexing_usecase.py, lines 49-73
test_file1.write_text("""def add(a, b):
    '''Add two numbers.'''
    return a + b

def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b
""")
```

**Too simple:**
- No nested functions/classes
- No complex imports
- No large files
- No binary files (should be skipped)
- No deeply nested directory structure

---

## 4. SPECIFIC COVERAGE GAPS BY USE CASE

### IndexingUseCase - Critical Gaps

**What's tested:**
- ✓ Basic full index
- ✓ Incremental sync (no changes)
- ✓ Incremental sync (modified files)
- ✓ Deleted files
- ✓ Multiple modifications

**What's NOT tested:**
- ✗ Mixed additions + modifications + deletions in one sync
- ✗ New files with same symbol as deleted files
- ✗ Very large files (>10MB)
- ✗ Files with syntax errors
- ✗ Files with mixed encodings
- ✗ Partial sync failure recovery
- ✗ Tree SHA comparison edge cases
- ✗ Model fingerprint mismatch (reindex trigger)
- ✗ Path filter with glob patterns
- ✗ Force reindex when model changes

---

### SearchUseCase - Critical Gaps

**What's tested:**
- ✓ Exact keyword match
- ✓ Semantic similarity
- ✓ Hybrid fusion
- ✓ Path filter
- ✓ Language filter
- ✓ Result ranking
- ✓ Preview generation
- ✓ Topk limit
- ✓ Empty query (errors correctly)
- ✓ No matches

**What's NOT tested:**
- ✗ Multiple filters combined (path + language)
- ✗ Very large topk (1000+)
- ✗ Query with special characters / SQL injection
- ✗ Query embeddings fail (network error)
- ✗ Database corrupted mid-search
- ✗ Vector search returns stale vectors
- ✗ Ties in RRF scores
- ✗ Chunk repository returns None for valid ID

---

### Repository Layers - Critical Gaps

**What's tested:**
- ✓ File repository (track, get, list)
- ✓ Basic chunk operations

**What's NOT tested:**
- ✗ Concurrent chunk operations
- ✗ Large batch insertions (1000+)
- ✗ Vector BLOB precision
- ✗ Chunk deduplication across tree SHAs
- ✗ Meta repository persistence
- ✗ SQLite journal handling
- ✗ FTS5 indexing correctness
- ✗ Deleted file cleanup in vector repo

---

## 5. TEST EXECUTION SPEED ANALYSIS

### Current Status
- **Total Time:** 1.5 seconds
- **Status:** FAST but with issues

### Breakdown
```
Fast (<0.01s):
  - Most unit tests (line chunker, tree-sitter, config)
  
Medium (0.01-0.1s):
  - Git operations (setup/teardown)
  - Database operations
  
Slow (0.1s+):
  - Embedding model operations (marked slow)
```

### Issue: Slow Tests Grouped Wrong
- Tests marked `@pytest.mark.slow` are skipped by default
- But `test_full_index`, `test_search_*` NOT marked
- These download embeddings (~60s on first run)

**Fix needed:** Mark embedding-dependent tests as slow

---

## 6. RECOMMENDATIONS - Priority Order

### CRITICAL (Affects Reliability)

1. **Fix test isolation in test_auto_sync.py**
   - Replace `os.chdir()` with `pytest monkeypatch.chdir()`
   - Prevents test pollution
   - Enables parallel execution

2. **Add timeout to all subprocess calls**
   - Prevents test suite hanging
   - Lines: 47 subprocess calls need timeout=5

3. **Add error path tests for use cases**
   - IndexingUseCase: File read errors, embedder failures
   - SearchUseCase: Empty results, malformed queries
   - Repositories: Transaction failures, corruption

### HIGH (Coverage & Reliability)

4. **Extract git_repo fixture to conftest**
   - Deduplicate 4+ versions
   - Create parametrized versions (empty, simple, complex)

5. **Add integration test for partial failures**
   - Index 10 files, fail on file 5
   - Verify: 4 files indexed, state saved, can retry

6. **Consolidate database fixtures**
   - Create reusable `initialized_db` fixture
   - Reduce duplication

7. **Test error paths in repositories**
   - Mock SQLite errors
   - Verify proper exception handling

### MEDIUM (Coverage)

8. **Add realistic test data**
   - 50-100 chunks (not 4)
   - Nested classes/functions
   - Large files
   - Various languages

9. **Test path filters with glob patterns**
   - `src/**/*.py`
   - `tests/*/test_*.py`
   - Edge cases: unicode, special chars

10. **Add search query edge cases**
    - Special characters: `@`, `#`, `$`
    - Quoted strings: `"def function"`
    - Regex-like patterns

### LOW (Code Quality)

11. **Move CLI tests to separate module**
    - Create tests/e2e/ for end-to-end tests
    - Keep integration/ for component tests

12. **Add performance regression tests**
    - Embed speed: <100ms per 100 chunks
    - Search time: <1s for 1000 chunks
    - Index time: <2s per 100 files

13. **Improve assertion messages**
    - Use descriptive messages
    - Include actual vs expected

---

## 7. IMPLEMENTATION GUIDE

### Week 1: Critical Fixes
```bash
# Fix test isolation
pytest tests/integration/test_auto_sync.py --fixtures
# Add monkeypatch.chdir usage

# Add timeout to subprocess
grep -r "subprocess.run" tests/ --include="*.py" -l
# Add timeout=5 to each

# Add error path tests
tests/unit/test_indexing_errors.py (new)
tests/unit/test_search_errors.py (new)
```

### Week 2: Consolidation
```bash
# Extract fixtures
tests/conftest.py (expand)
# - git_repo fixture with parameters
# - initialized_db fixture
# - sample_project fixture

# Reorganize
tests/e2e/ (new) for CLI tests
tests/integration/ (refactor) for component tests
```

### Week 3: Coverage Expansion
```bash
# Realistic data
tests/fixtures/sample_repos/ (new)
# - python_project/ (50 files, mixed patterns)
# - typescript_project/ (mixed functions/classes)
# - monorepo/ (nested structure)

# Edge case tests
tests/integration/test_edge_cases.py (new)
```

---

## Summary Table

| Category | Status | Priority | Impact |
|----------|--------|----------|--------|
| **Coverage** | 44% overall | HIGH | Missing error paths |
| **Isolation** | Issues in auto_sync | CRITICAL | Test pollution risk |
| **Speed** | 1.5s (good) | MEDIUM | Some tests marked wrong |
| **Organization** | Mixed categories | MEDIUM | Maintenance burden |
| **Fixtures** | Duplicated 4+ times | HIGH | DRY violation |
| **Error handling** | Mostly untested | CRITICAL | Reliability unknown |
| **Integration** | CLI not unit tested | MEDIUM | Black box testing |

