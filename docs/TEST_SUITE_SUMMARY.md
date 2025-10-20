# Test Suite Analysis - Executive Summary

## Quick Facts

- **122 total tests** (91 passing in standard run)
- **44% overall coverage** (varies: 100% for some modules, 14% for repositories)
- **1.5 seconds runtime** (fast, but some slow tests not marked)
- **Test categories:** Unit (mostly good), Integration (mixed quality), Performance (good)

---

## Critical Issues (Fix First)

### 1. Test Isolation Breaking

**File:** `tests/integration/test_auto_sync.py`

**Problem:** Uses `os.chdir()` without cleanup, causing:
- Global state mutation
- Test order dependency
- Cannot run in parallel
- If test crashes, working directory corrupted

**Fix:** Replace with `pytest.monkeypatch.chdir()`

---

### 2. Subprocess Calls Without Timeout

**Location:** 47 subprocess calls across all tests

**Problem:** If git/cmd hangs, entire test suite hangs indefinitely

**Fix:** Add `timeout=5` to all subprocess.run() calls

---

### 3. Core Use Case Logic Untested

| Use Case | Coverage | Gap |
|----------|----------|-----|
| **IndexingUseCase** | 25% | No error scenarios (file read failures, partial indexing) |
| **SearchUseCase** | 38% | No combined filters, malformed queries |
| **Repositories** | 14-20% | No concurrent access, batch operations, DB errors |

**Fix:** Add error path tests for critical failures

---

## Coverage Gaps by Priority

### MISSING - Error Paths
- ✗ File read errors (binary, permissions, encoding)
- ✗ Embedder failures (network, out of memory)
- ✗ Database errors (locked, corrupted, full)
- ✗ Partial indexing failures (recover gracefully)

### MISSING - Edge Cases
- ✗ Very large files (>10MB)
- ✗ Files with syntax errors
- ✗ Special characters in queries/paths
- ✗ Unicode content
- ✗ Combined search filters (path + language)

### MISSING - Complex Scenarios
- ✗ Mixed additions + modifications + deletions
- ✗ Duplicate/near-duplicate content
- ✗ Nested classes/functions (complex chunking)
- ✗ Performance regressions

---

## Test Quality Issues

### 1. Fixture Duplication
- 4+ versions of `git_repo` fixture
- 3+ versions of `db_path` fixture  
- 2+ versions of `embedder` initialization

**Impact:** When setup changes, must update multiple places

**Fix:** Extract to shared `conftest.py`

---

### 2. Test Data Too Simple
- Only 4 sample chunks (real repos have 100s)
- Only 2 test files (no complex structure)
- Perfect separation (unrealistic)

**Impact:** Tests don't reflect real-world complexity

**Fix:** Add realistic test fixtures with 50-100 chunks

---

### 3. Brittle Assertions
- Depend on exact ranking (non-deterministic)
- String matching for output messages
- Assume perfect BM25/vector separation

**Example:**
```python
# Brittle:
assert results[0].chunk.symbol == "multiply"

# Better:
assert "multiply" in {r.chunk.symbol for r in results}
```

---

### 4. Slow Tests Not Marked
- Tests that download embedding models (60+ seconds)
- Tests with git operations
- NOT marked `@pytest.mark.slow` → skipped by default

**Impact:** Running full suite takes much longer than indicated

---

## Organization Issues

### Test Categorization Confusion
```
tests/unit/              - ✓ Pure unit tests (good)
tests/integration/       - Mixed! Has E2E, subprocess, real DB
tests/performance/       - ✓ Performance benchmarks (good)
```

**Missing:** `tests/e2e/` for CLI integration tests

---

## What's Working Well

- ✓ Fast execution (1.5s for quick suite)
- ✓ Core happy paths tested
- ✓ Git adapter thoroughly tested
- ✓ Repository basic operations covered
- ✓ Domain entities fully tested
- ✓ Line chunker fully tested

---

## Quick Wins (Easy Fixes)

1. **Add timeout to subprocess (5 min)** - 47 calls to update
2. **Fix os.chdir in auto_sync (10 min)** - Use monkeypatch
3. **Mark slow tests (5 min)** - Add @pytest.mark.slow decorator
4. **Extract git_repo fixture (15 min)** - Move to conftest
5. **Add 3-4 error path tests (30 min)** - File errors, embedder failures

---

## Effort Estimates

| Task | Difficulty | Time | Tests Added |
|------|-----------|------|------------|
| Fix isolation | Easy | 10min | 0 |
| Add timeouts | Easy | 15min | 0 |
| Error paths | Medium | 2hrs | 20-30 |
| Realistic data | Medium | 2hrs | Improved |
| Extract fixtures | Easy | 30min | 0 |
| **Total** | | **5 hours** | **20-30 tests** |

---

## Full Analysis

See: `/docs/TEST_SUITE_ANALYSIS.md` for detailed breakdown
- Coverage gaps by module
- Line-by-line uncovered code
- Specific scenarios not tested
- Recommendations with priority
- Implementation guide

---

## Next Steps (Recommended Order)

1. **Today:** Review this summary + full analysis
2. **This week:** Fix critical issues (isolation, timeouts)
3. **Next week:** Add error path tests + extract fixtures
4. **Following week:** Expand coverage with realistic data

**Estimated impact:** 44% → 60% coverage, 0 isolation issues
