# Ember v0.1 MVP - User Acceptance Testing (UAT) Checklist

**Version:** 0.1.0 (MVP)
**Date:** 2025-10-14
**Status:** Pre-release validation

## Purpose

This checklist validates that Ember v0.1 MVP meets all acceptance criteria from PRD §19 and works correctly in real-world scenarios. Complete all tests before tagging v0.1.0 release.

---

## Test Environment Setup

- [ ] Clean Python 3.11+ virtual environment
- [ ] Fresh installation via `pip install -e .`
- [ ] Test git repository with mixed languages
- [ ] Multiple terminal sessions for workflow testing

---

## 1. Installation & Setup Tests

### 1.1 Package Installation

- [ ] **Test:** `pip install -e .` succeeds without errors
- [ ] **Test:** `ember --version` shows correct version
- [ ] **Test:** `ember --help` displays all commands
- [ ] **Verify:** All dependencies install (PyTorch, sentence-transformers, tree-sitter)
- [ ] **Verify:** Installation time reasonable (<5 minutes with deps)

### 1.2 Init Command

- [ ] **Test:** `ember init` in empty git repo creates .ember/
- [ ] **Verify:** `.ember/config.toml` exists with valid TOML
- [ ] **Verify:** `.ember/index.db` exists and has correct schema
- [ ] **Verify:** `.ember/state.json` exists with initial state
- [ ] **Test:** `ember init` again without --force shows error
- [ ] **Test:** `ember init --force` reinitializes successfully
- [ ] **Test:** `ember init` in non-git directory shows error or warning

**Pass Criteria:** Init creates all required files with valid content

---

## 2. Indexing Tests

### 2.1 Initial Sync (Small Codebase)

**Setup:** Test repo with ~50 files (Python, TypeScript, JavaScript)

- [ ] **Test:** `ember sync` completes without errors
- [ ] **Verify:** All tracked files indexed (check file count)
- [ ] **Verify:** Chunks created for supported languages
- [ ] **Verify:** Vectors stored (check database)
- [ ] **Verify:** FTS5 index populated (query chunk_text table)
- [ ] **Timing:** Initial sync <2 min for 50 files
- [ ] **Test:** Re-run `ember sync` shows "No changes detected"

**Pass Criteria:** First sync indexes all files, second sync is no-op

### 2.2 Incremental Sync

**Setup:** Modify 3 files from previous test

- [ ] **Test:** `ember sync` detects only changed files
- [ ] **Verify:** Shows "incremental sync" in output
- [ ] **Verify:** Only 3 files reindexed (not all 50)
- [ ] **Verify:** Old chunks for changed files removed
- [ ] **Verify:** Unchanged files not reprocessed
- [ ] **Timing:** Incremental sync <10 seconds

**Pass Criteria:** Only changed files reindexed, 5-10x faster than full sync

### 2.3 File Operations

- [ ] **Test:** Add new file, `ember sync` indexes it
- [ ] **Test:** Delete file, `ember sync` removes its chunks
- [ ] **Test:** Rename file (git mv), chunks updated correctly
- [ ] **Test:** Modify unstaged file, sync detects changes

**Pass Criteria:** All file operations reflected in index correctly

### 2.4 Language Support

Test with sample files for each supported language:

- [ ] **Python** (.py): Functions and classes extracted
- [ ] **TypeScript** (.ts, .tsx): Functions and classes extracted
- [ ] **JavaScript** (.js, .jsx): Functions extracted
- [ ] **Go** (.go): Functions extracted
- [ ] **Rust** (.rs): Functions and impls extracted
- [ ] **Java** (.java): Classes and methods extracted
- [ ] **C** (.c, .h): Functions extracted
- [ ] **C++** (.cpp, .hpp): Classes and functions extracted
- [ ] **C#** (.cs): Classes and methods extracted
- [ ] **Ruby** (.rb): Classes and methods extracted
- [ ] **Unsupported language**: Falls back to line-based chunking

**Pass Criteria:** Tree-sitter extracts symbols correctly for all 9+ languages

---

## 3. Search Tests

### 3.1 Exact Keyword Search (BM25)

- [ ] **Test:** `ember find "multiply"` finds function named multiply
- [ ] **Verify:** Result shows high BM25 score
- [ ] **Verify:** Result shows file path, line numbers, symbol name
- [ ] **Verify:** Preview shows relevant code snippet
- [ ] **Test:** `ember find "class Calculator"` finds class definition

**Pass Criteria:** Exact matches return expected results with high scores

### 3.2 Semantic Search (Vector)

- [ ] **Test:** `ember find "greeting someone"` finds greet/hello functions
- [ ] **Verify:** Results include semantically related code (not just keyword matches)
- [ ] **Verify:** Vector similarity scores present
- [ ] **Test:** `ember find "parse JSON data"` finds parsing functions even without exact words

**Pass Criteria:** Semantic search finds conceptually related code

### 3.3 Hybrid Search Fusion

- [ ] **Test:** Query that matches both keyword and semantically
- [ ] **Verify:** Fused score combines BM25 and vector scores
- [ ] **Verify:** RRF fusion ranks results appropriately
- [ ] **Verify:** Both score types displayed in output

**Pass Criteria:** Hybrid search balances exact and semantic matches

### 3.4 Filtering

- [ ] **Test:** `ember find "function" --in "*.ts"` returns only TypeScript
- [ ] **Test:** `ember find "class" --lang python` returns only Python
- [ ] **Test:** `ember find "handler" --in "src/**/*.py"` respects path glob
- [ ] **Test:** Combined filters: `--in "*.py" --lang python` (redundant but valid)

**Pass Criteria:** All filters work correctly, can be combined

### 3.5 Result Limits and Formatting

- [ ] **Test:** `ember find "test" -k 5` returns exactly 5 results
- [ ] **Test:** `ember find "test"` uses default limit (20)
- [ ] **Test:** `ember find "test" --json` returns valid JSON
- [ ] **Verify:** JSON schema matches expected format (rank, score, path, symbol, etc.)
- [ ] **Test:** Query with no results shows friendly message

**Pass Criteria:** Result limiting and formatting work as expected

### 3.6 Search Performance

- [ ] **Timing:** Typical query completes in <500ms
- [ ] **Timing:** Cold query (first after restart) completes in <2s
- [ ] **Test:** Search on codebase with 200+ files
- [ ] **Verify:** Performance acceptable for interactive use

**Pass Criteria:** Search is fast enough for interactive workflows

---

## 4. Workflow Integration Tests

### 4.1 Find → Cat → Open Workflow

- [ ] **Test:** `ember find "multiply" -k 3`
- [ ] **Verify:** Results cached to `.ember/.last_search.json`
- [ ] **Test:** `ember cat 1` displays first result
- [ ] **Verify:** Shows chunk content with header
- [ ] **Test:** `ember cat 1 --context 5` shows surrounding lines
- [ ] **Verify:** Context lines dimmed, chunk lines highlighted
- [ ] **Test:** `ember open 1` opens file in $EDITOR
- [ ] **Verify:** Editor opens at correct line number
- [ ] **Test:** Try with different editors (vim, code, nano)

**Pass Criteria:** Complete workflow from search to edit works seamlessly

### 4.2 Session Persistence

- [ ] **Test:** Run `ember find` in one terminal
- [ ] **Test:** Run `ember cat 1` in another terminal
- [ ] **Verify:** Cat command uses cached results
- [ ] **Test:** Run new search, verify cache updates
- [ ] **Test:** `ember cat` after new search uses new results

**Pass Criteria:** Result cache enables stateful multi-command workflows

### 4.3 Error Handling

- [ ] **Test:** `ember cat 1` before running find
- [ ] **Verify:** Friendly error: "Run 'ember find' first"
- [ ] **Test:** `ember cat 999` with only 3 results
- [ ] **Verify:** Error: "Index out of range"
- [ ] **Test:** `ember open 1` with file deleted
- [ ] **Verify:** Graceful error message
- [ ] **Test:** `ember sync` without init
- [ ] **Verify:** Error message guides user to run init

**Pass Criteria:** All error messages are clear and actionable

---

## 5. Edge Cases & Robustness

### 5.1 Empty/Small Codebases

- [ ] **Test:** Init and sync in repo with 0 files
- [ ] **Verify:** Graceful handling (no crash)
- [ ] **Test:** Repo with only 1 file
- [ ] **Verify:** Indexing works correctly

### 5.2 Large Files

- [ ] **Test:** Index file with 1000+ lines
- [ ] **Verify:** Chunks created appropriately
- [ ] **Verify:** Line-based fallback for unsupported languages works

### 5.3 Binary/Invalid Files

- [ ] **Test:** Repo contains .pyc, images, or other binary files
- [ ] **Verify:** Binary files skipped or handled gracefully
- [ ] **Test:** File with invalid UTF-8
- [ ] **Verify:** Decoding errors handled (errors='replace')

### 5.4 Git Edge Cases

- [ ] **Test:** Sync on detached HEAD
- [ ] **Test:** Sync with merge conflicts present
- [ ] **Test:** Sync with submodules (if applicable)
- [ ] **Verify:** Git errors don't crash application

### 5.5 Database Integrity

- [ ] **Test:** Corrupt .ember/index.db and try to sync
- [ ] **Verify:** Error message suggests reinitializing
- [ ] **Test:** Delete state.json and sync
- [ ] **Verify:** State recreated or sensible error
- [ ] **Test:** Manually edit config.toml with invalid TOML
- [ ] **Verify:** Config load error shows line number (if loaded)

---

## 6. Performance Validation

### 6.1 PRD Acceptance Criteria (§19)

Per PRD requirements:

- [ ] **Init creates .ember/ in <1 second**
- [ ] **Sync 50-file codebase in <2 minutes** (Python, TypeScript)
- [ ] **Incremental sync (1 file changed) in <5 seconds**
- [ ] **Search returns results in <500ms** for typical query
- [ ] **Memory usage reasonable** (<2GB during indexing)

### 6.2 Scalability Tests

Run performance tests from `tests/performance/`:

- [ ] **Test:** `pytest tests/performance/test_performance.py`
- [ ] **Verify:** test_initial_indexing_small passes
- [ ] **Verify:** test_initial_indexing_medium passes
- [ ] **Verify:** test_incremental_sync_performance passes
- [ ] **Verify:** test_search_performance passes
- [ ] **Verify:** test_database_size_scaling passes
- [ ] **Check:** Results match projections in docs/PERFORMANCE.md

**Pass Criteria:** All performance tests pass, metrics within expected ranges

---

## 7. Documentation Validation

### 7.1 README Accuracy

- [ ] **Verify:** Installation instructions work as written
- [ ] **Verify:** Quick start example works
- [ ] **Verify:** All command examples are accurate
- [ ] **Verify:** Supported languages list is complete
- [ ] **Verify:** Performance numbers match actual results
- [ ] **Verify:** Links to other docs are valid

### 7.2 Help Text

- [ ] **Test:** `ember --help` lists all commands
- [ ] **Test:** `ember init --help` shows options and descriptions
- [ ] **Test:** `ember sync --help` documents all flags
- [ ] **Test:** `ember find --help` explains filtering options
- [ ] **Verify:** All help text is clear and accurate

---

## 8. Known Limitations Validation

Verify known limitations from AUDIT.md:

- [ ] **Verify:** config.toml exists but is NOT used by commands
- [ ] **Verify:** Git tracking determines indexed files (config.include/ignore unused)
- [ ] **Verify:** export/import/audit commands not yet implemented
- [ ] **Verify:** Redaction patterns defined but not applied
- [ ] **Document:** These limitations in README if not already clear

---

## 9. Cross-Platform Testing (Optional)

If testing on multiple platforms:

- [ ] **macOS:** All tests pass
- [ ] **Linux:** All tests pass
- [ ] **Windows:** All tests pass (or document incompatibilities)

---

## 10. Regression Testing

### 10.1 Core Test Suite

- [ ] **Run:** `uv run pytest -v`
- [ ] **Verify:** All 103+ tests pass
- [ ] **Check:** No new warnings or deprecations
- [ ] **Timing:** Full test suite completes in <3 minutes

### 10.2 Slow Tests (with model)

- [ ] **Run:** `uv run pytest -v --run-slow`
- [ ] **Verify:** Embedding tests pass
- [ ] **Verify:** Model downloads successfully on first run
- [ ] **Verify:** Cached model used on subsequent runs

---

## 11. Pre-Release Checklist

Before tagging v0.1.0:

- [ ] All UAT tests above pass
- [ ] All automated tests pass (`pytest`)
- [ ] README.md is accurate and complete
- [ ] CHANGELOG.md created with v0.1.0 notes
- [ ] AUDIT.md issues addressed or documented
- [ ] Version number updated in pyproject.toml
- [ ] Git tag created: `git tag v0.1.0`
- [ ] Release notes drafted
- [ ] Known limitations documented in README

---

## Test Execution Log

**Tester:**
**Date:**
**Environment:** Python ____, OS ____, Ember v____

| Test Section | Status | Notes |
|-------------|--------|-------|
| 1. Installation | ⬜ | |
| 2. Indexing | ⬜ | |
| 3. Search | ⬜ | |
| 4. Workflow | ⬜ | |
| 5. Edge Cases | ⬜ | |
| 6. Performance | ⬜ | |
| 7. Documentation | ⬜ | |
| 8. Known Limitations | ⬜ | |
| 9. Cross-Platform | ⬜ | |
| 10. Regression | ⬜ | |

**Overall UAT Status:** ⬜ PASS / ⬜ FAIL

**Blockers:**

**Recommendations:**

---

**UAT Complete:** ____-__-____
**Ready for Release:** ⬜ YES / ⬜ NO
