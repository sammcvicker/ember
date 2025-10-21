# Ember v0.1 MVP Audit

**Date:** 2025-10-14
**Status:** Pre-release audit before v0.1.0
**Auditor:** Claude (Session 14)

## Executive Summary

This audit identifies discrepancies between documentation, planning artifacts, and actual implementation. The goal is to ensure consistency before MVP release and create a UAT checklist for final validation.

---

## 1. Documentation Discrepancies

### 1.1 TODO.md Out of Date ❌

**Issue:** TODO.md shows "Current Phase: Phase 2" but actual state is Phase 8 complete.

**Location:** `/TODO.md` line 4

**Impact:** Medium - Misleading for new contributors

**Recommendation:** Update TODO.md to reflect Phase 8 completion or mark as historical reference

---

### 1.2 Progress Tracking Accurate ✅

**Status:** `docs/progress.md` is accurate and up-to-date through Session 13

**Last Updated:** 2025-10-14 Session 13

**Verified:** All 13 sessions documented with decisions and completion status

---

## 2. Unused Code

### 2.1 ember/app/ Module Empty and Unused ⚠️

**Location:** `ember/app/__init__.py` (only file in directory)

**Imports Found:** 0 references to `ember.app` in codebase

**Original Purpose:** According to PRD §3, intended for "DTOs and formatters"

**Current State:** All DTOs live in domain entities and use case request/response objects. No formatters needed (CLI does formatting inline).

**Recommendation:**
- **Option A:** Remove `ember/app/` directory entirely (preferred)
- **Option B:** Document as reserved for future expansion
- **Option C:** Move result formatting logic from CLI into `ember/app/formatters.py`

**Priority:** Low (not blocking release)

---

### 2.2 Config System: Defined but Not Used ❌

**Critical Finding:** Configuration system exists but is NEVER loaded or used by any command.

**Evidence:**
```bash
# Config models exist
ember/domain/config.py          # IndexConfig, SearchConfig, RedactionConfig
ember/shared/config_io.py       # load_config(), save_config()

# Config gets created
ember init                      # Creates .ember/config.toml

# But config is NEVER loaded by commands
$ rg "load_config" ember/entrypoints/
# No results

$ rg "EmberConfig|IndexConfig|SearchConfig|RedactionConfig" ember/entrypoints/ ember/core/
# No results
```

**Specific Unused Settings:**

1. **`search.topk`**: Defined as default result count (20), but `find` command uses its own `-k` flag
2. **`search.rerank`**: Cross-encoder reranking not implemented (feature flag exists but no code)
3. **`search.filters`**: Default filters defined but never applied
4. **`redaction.patterns`**: Secret redaction patterns defined but NEVER applied before embedding
5. **`redaction.max_file_mb`**: File size limit never checked
6. **`index.model`**: Model name in config, but JinaCodeEmbedder is hardcoded in CLI
7. **`index.chunk`**: Strategy setting exists but not respected (always tries tree-sitter first)
8. **`index.include/ignore`**: File patterns defined but git tracking determines what gets indexed

**Impact:** HIGH - Users can modify config.toml but it has zero effect

**Recommendation:**
- **Immediate (Pre-release):** Document in README that config is currently for informational purposes only
- **Post v0.1:** Implement config loading in CLI or remove config system entirely
- **Alternative:** Mark config as "planned for v0.2" and don't generate it in init

**Priority:** HIGH (affects user expectations)

---

## 3. Test Coverage Gaps

### 3.1 InitUseCase: 0% Coverage ⚠️

**Source:** `docs/progress.md` Session 7 - "InitUseCase: 0% coverage"

**Note:** May be outdated from Session 7. Integration tests in `tests/integration/test_init.py` do exercise the init flow.

**Recommendation:** Verify current coverage and add unit tests if still at 0%

---

### 3.2 Core Config Module: 0% Coverage ⚠️

**Location:** `ember/core/config/init_usecase.py`

**Reported Coverage:** 0% (34/34 lines missing) per Session 7

**Reason:** Config is created but never loaded/validated by other commands

**Recommendation:** Either implement config usage or remove init_usecase entirely

---

### 3.3 Shared Config I/O: 0% Coverage ⚠️

**Location:** `ember/shared/config_io.py` and `ember/shared/state_io.py`

**Reported Coverage:** 0% (50/50 lines missing combined)

**Note:** Used by init command and integration tests, so coverage report may be incomplete

**Recommendation:** Run full coverage report to verify actual usage

---

## 4. Feature Implementation Status

### 4.1 Fully Implemented ✅

- [x] `ember init` - Creates .ember/ with config, db, state
- [x] `ember sync` - Incremental indexing with git integration
- [x] `ember find` - Hybrid BM25 + vector search with RRF fusion
- [x] `ember cat` - Display chunks with context
- [x] `ember open` - Editor integration
- [x] Tree-sitter chunking - 9 languages supported
- [x] Performance testing - Benchmarked and documented

---

### 4.2 Partially Implemented ⚠️

- [ ] **Config system** - Created but never loaded
- [ ] **Redaction** - Patterns defined but never applied
- [ ] **Index.include/ignore** - Patterns exist but not used (git determines files)

---

### 4.3 Not Implemented (Planned) 📋

Per README:
- [ ] `ember export` - Export index bundles
- [ ] `ember import` - Import index bundles
- [ ] `ember audit` - Scan for secrets
- [ ] `ember explain` - Result explainability (partially exists via scores)
- [ ] Cross-encoder reranking
- [ ] Watch mode
- [ ] HTTP server for agents

---

## 5. Architectural Concerns

### 5.1 CLI Hardcoded Dependencies ⚠️

**Issue:** CLI instantiates specific adapters instead of using config

**Example:**
```python
# ember/entrypoints/cli.py
embedder = JinaCodeEmbedder()  # Hardcoded, ignores config.index.model
```

**Impact:** Config system cannot change model without code changes

**Recommendation:** Either wire config to CLI or remove config.index.model setting

---

### 5.2 File Selection Logic Unclear ⚠️

**Issue:** `config.index.include/ignore` patterns exist but actual file selection uses git tracking

**Current Behavior:**
- `git ls-files` determines what's indexed
- Config patterns are generated but never consulted
- .gitignore implicitly controls what's indexed

**Recommendation:**
- Document that git tracking determines indexed files
- Remove or clarify include/ignore config options
- OR implement config-based filtering on top of git tracking

---

## 6. Recommendations Summary

### Pre-Release (v0.1) - MUST FIX

1. **Document config limitations** in README
   - Add note: "Configuration in .ember/config.toml is currently informational. Settings will be honored in v0.2."
   - Or remove config generation from init command

2. **Update TODO.md** to reflect Phase 8 completion
   - Mark historical or update to current state

3. **Clarify README on file selection**
   - Document that git tracking controls indexed files
   - Explain .gitignore is respected

### Post-Release (v0.2) - SHOULD FIX

4. **Implement config loading** in CLI commands
   - Wire config.search.topk to find command default
   - Wire config.index.chunk to chunking strategy
   - Wire config.index.model to embedder selection

5. **Implement or remove redaction**
   - Either apply patterns before embedding
   - Or remove from config until implemented

6. **Clean up unused code**
   - Decide on ember/app/ directory fate
   - Remove dead code paths

### Future (v0.3+) - COULD FIX

7. **Complete remaining commands**
   - export/import/audit per PRD

8. **Add config-based file filtering**
   - Layer include/ignore patterns on top of git tracking
   - Allow indexing non-git files

---

## 7. UAT Checklist Reference

See `docs/UAT.md` for comprehensive user acceptance testing checklist.

---

## Appendix: Verification Commands

```bash
# Check config usage
rg "load_config|EmberConfig" ember/entrypoints/ ember/core/

# Check app module usage
rg "from ember\.app|import ember\.app" .

# Verify TODO.md current phase
head -10 TODO.md

# Check test coverage
uv run pytest --cov=ember --cov-report=term-missing -m "not slow"
```

---

**Audit Complete:** 2025-10-14
**Next Action:** Review findings and create UAT checklist
