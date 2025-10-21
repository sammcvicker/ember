# Changelog

All notable changes to Ember will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-10-20

### Changed
- **CLI refactoring (Phase 1)**: Extracted shared utilities to reduce code duplication (#32)
  - Created `ember/core/cli_utils.py` with reusable CLI utilities
  - Extracted `RichProgressCallback` for progress bar management
  - Added `progress_context()` context manager to eliminate duplicated progress bar setup
  - Added `load_cached_results()` and `validate_result_index()` to eliminate 80% duplication between `cat` and `open` commands
  - Added `highlight_symbol()` and `format_result_header()` for consistent output formatting
  - Reduced duplication in `sync`, `find`, `cat`, and `open` commands
  - All tests pass, no user-facing changes
- **CLI refactoring (Phase 2)**: Extracted presentation logic to separate layer (#32)
  - Created `ember/core/presentation/` module with `ResultPresenter` class
  - Extracted 87-line human output formatter from `find` command
  - Added `serialize_for_cache()` to eliminate duplicate serialization logic
  - Added `format_json_output()` to eliminate duplicate JSON formatting
  - Added `format_human_output()` for reusable ripgrep-style formatting
  - Reduced `find` command from 257 lines to ~180 lines (30% reduction)
  - All tests pass, no user-facing changes
- **CLI refactoring (Phase 3)**: Simplified commands to thin layer pattern (#32)
  - Extracted `check_and_auto_sync()` helper to eliminate 50-line auto-sync block from `find` command
  - Commands now follow pattern: parse → call use case → present output
  - Reduced total CLI file from 899 lines to 639 lines (**29% reduction, 260 lines removed**)
  - Improved maintainability and testability
  - All tests pass, no user-facing changes

### Added
- **Model loading progress indicator**: Shows separate progress when loading embedding model during sync (#31)
  - Prevents first file from appearing abnormally slow (model loads in ~2-3s)
  - Shows "Loading embedding model..." progress bar before file indexing begins
  - Only displayed when model needs to be loaded (not on subsequent syncs)
  - Works with both full and incremental sync
  - More accurate file indexing metrics (no longer skewed by model loading time)
- **Auto-sync on search**: `ember find` now automatically syncs the index before searching (#26)
  - Detects stale index by comparing current git tree SHA vs last indexed SHA
  - Runs incremental sync automatically if changes detected (typically <2s overhead)
  - Shows clear progress: "Detected changes, syncing index... ✓ Synced N file(s) in X.Xs"
  - Ensures users never get stale search results
  - Added `--no-sync` flag to skip auto-sync for power users who want maximum speed
  - Silent in JSON mode (messages go to stderr, not stdout)
  - Added 4 new integration tests for auto-sync behavior
- **Functional config system**: `.ember/config.toml` settings are now loaded and respected (#25)
  - `search.topk`: Default number of search results (overridable with `-k` flag)
  - `index.line_window`: Lines per chunk for line-based chunking
  - `index.line_stride`: Stride between chunks
  - Graceful fallback to defaults if config is missing or invalid
  - Added `ConfigProvider` Protocol in ports layer
- **Code quality review slash command**: Added `/audit` command for systematic code review (#22)
  - Runs cyclomatic complexity analysis using radon
  - Systematically reviews codebase using sub-agents
  - Creates GitHub issues for tech debt and improvements (doesn't fix them)
  - Includes code snippets and line references for context preservation
  - Focuses on reflection about architectural decisions and trade-offs
  - Added `TomlConfigProvider` adapter for config loading
  - Added 8 new tests for config functionality (5 unit, 3 integration)
- Created `develop` branch for ongoing development
- Created GitHub milestones for release planning (0.2.0, Backlog)
- Added MAINTAINER_GUIDE.md with comprehensive operational procedures
- Added docs/ARCHITECTURE.md with detailed technical architecture guide
- Created docs/archive/ for historical documentation

### Changed
- **Replaced brute-force vector search with sqlite-vec**: Migrated from in-memory similarity search to optimized sqlite-vec extension (#41)
  - Replaced `SimpleVectorSearch` with `SqliteVecAdapter` using sqlite-vec for efficient k-NN queries
  - Uses vec0 virtual table with cosine distance metric (optimal for normalized embeddings)
  - Automatic synchronization from VectorRepository's vectors table to vec_chunks
  - Maintains backward compatibility with existing VectorSearch protocol
  - Better performance and scalability for larger codebases
  - Added sqlite-vec>=0.1.6 dependency
- **Auto-sync now uses progress bars**: Refactored to reuse sync command's progress display pattern (#28)
  - Eliminated code duplication between `sync` command and auto-sync
  - Auto-sync now shows the same professional progress bars as regular sync
  - Extracted `_create_indexing_usecase()` helper function for consistency
  - Reduced ~50 lines of duplicated dependency initialization code
- **TreeSitterChunker refactoring**: Major complexity reduction through extraction (#36, Phases 1-3)
  - **Phase 1 - LanguageRegistry**: Created centralized language configuration management
    - Eliminated 75% code duplication in language query patterns (163 lines → single source of truth)
    - Implemented lazy parser initialization (load languages only when used)
  - **Phase 2 - DefinitionMatcher**: Extracted complex AST matching logic
    - Isolated name-to-definition matching in standalone, testable class
    - Reduced chunk_file method complexity significantly
  - **Phase 3 - Logging**: Added comprehensive error logging
    - Specific logging for encoding errors, parse failures, and query execution errors
    - Debug logging for unsupported languages and extraction results
  - **Overall Impact**:
    - Reduced TreeSitterChunker from 293 lines to 109 lines (63% reduction)
    - Reduced cyclomatic complexity from C-16 toward target of C-10
    - Improved testability with 11 new DefinitionMatcher tests
    - All 125 tests passing with 100% coverage on new code
    - No behavioral changes, fully backward compatible

### Fixed
- **Test isolation and reliability improvements** (#38, Phase 1 Quick Wins)
  - Fixed test isolation by replacing all `os.chdir()` calls with `pytest.monkeypatch.chdir()`
  - Tests now properly restore working directory even on failures
  - Added `timeout=5` to all 47 subprocess calls to prevent test suite hangs
  - Tests can now run in parallel safely with `pytest -n auto`
  - Verified all slow tests (downloading models) properly marked with `@pytest.mark.slow`
- **Error path and edge case test coverage** (#38, Phase 2)
  - Added 3 IndexingUseCase error path tests: file permissions, encoding errors, embedder failures
  - Added 5 SearchUseCase edge case tests: empty results, combined filters, special characters, long queries
  - Documents current error handling behavior and improves test coverage
  - Total: 8 new tests to catch edge cases and improve reliability
  - Better architecture: follows DRY principle while maintaining clean separation
- **Batch embedding optimization**: Indexing is now ~27-38% faster due to batched embeddings (#14)
  - Refactored `_index_file()` to batch all chunks from a file in a single embedding call
  - Reduces embedding overhead from N calls per file to 1 call per file
  - Medium codebase (200 files): 55.34s → 40.09s (1.38x speedup)
  - Benefits increase with files that have more chunks
  - No architectural changes, same search quality
- **Fast test suite**: Default test run now completes in ~1-2s (57x faster) (#20)
  - Marked slow tests (performance tests, auto-sync tests, embedding tests) with `@pytest.mark.slow`
  - Configured pytest to skip slow tests by default with `-m 'not slow'`
  - Fast tests: 91 tests in ~1.5s (unit + fast integration tests)
  - Slow tests: 29 tests (can be run explicitly with `uv run pytest -m slow`)
  - Dramatically improves developer iteration speed
- Simplified CLAUDE.md to be more concise (~50% reduction)
- Moved detailed maintainer procedures to MAINTAINER_GUIDE.md
- Reorganized documentation structure for better discoverability
- Updated README to document functional config settings
- Updated README to reflect 120 passing tests (up from 103)
- Updated README with clarified test running instructions

### Fixed
- **IndexingUseCase error handling improvements**: Replaced blanket exception handling with structured error handling (#34)
  - Added specific exception handlers for common error types (FileNotFoundError, PermissionError, OSError, ValueError, RuntimeError)
  - KeyboardInterrupt and SystemExit now propagate correctly (no longer caught and hidden)
  - Added comprehensive logging throughout execute() method (info, debug, warning, error levels)
  - Error messages are now actionable - tell users what to fix instead of generic "something failed"
  - Unexpected errors use logger.exception() to capture full traceback for debugging
  - All 96 tests passing with no regressions
- **GitAdapter robustness improvements**: Fixed multiple error handling and edge case issues (#37)
  - Added helper method `_format_git_error()` to provide contextual error messages with exit codes
  - Fixed empty stderr issue - error messages now include git exit code and context instead of empty strings
  - Fixed index modification risk in `get_worktree_tree_sha()` - now uses try/finally to ensure index is always restored
  - Added empty repository detection - provides clear error message when repository has no commits
  - Added logging for unknown git status codes (C, T, X) - no longer silently skipped
  - Added UTF-8 decode error handling with graceful fallback for non-UTF-8 filenames
  - Extracted magic constant `EMPTY_TREE_SHA` and documented it
  - Added comprehensive test coverage for edge cases (empty repos, index restoration, error messages)
- **Data loss risk in indexing**: Fixed potential chunk deletion when re-indexing fails (#33)
  - Moved chunk deletion to occur AFTER validating chunking succeeds
  - When chunking fails, existing chunks are now preserved instead of deleted
  - Prevents silent data loss when files fail to parse or chunk
  - Added regression test to verify existing chunks preserved on chunking failure
- **Model loading now uses local cache**: Fixed HuggingFace connection timeouts
  - Added `local_files_only=True` to force using cached model files
  - Prevents network calls to HuggingFace when model is already cached
  - Falls back to downloading if model not cached locally
  - Eliminates "ReadTimeoutError" when HuggingFace is slow/unreachable
- Removed repetitive error message when running `ember init` with existing .ember/ directory

### Removed
- Moved historical v0.1.0 docs to docs/archive/ (AUDIT.md, UAT.md, progress.md)
- Removed "config is informational only" warning from README

---

## [0.1.0] - 2025-10-15

### Added

#### Core Functionality
- **Hybrid Search**: Combines BM25 (keyword) + vector embeddings (semantic) with RRF fusion
- **Incremental Indexing**: Diff-based sync that only reindexes changed files (9x+ speedup)
- **Multi-Language Support**: Tree-sitter-based semantic chunking for 9+ languages
  - Python, TypeScript, JavaScript, Go, Rust, Java, C, C++, C#, Ruby
  - Automatic fallback to line-based chunking for unsupported languages
- **Git Integration**: Automatic file tracking using git status and tree SHAs
- **Deterministic Indexing**: Reproducible indexes via git tree SHAs and model fingerprints

#### Commands
- `ember init`: Initialize .ember/ directory with config, database, and state
- `ember sync`: Index codebase with automatic incremental detection
  - `--worktree`: Index working directory including unstaged changes (default)
  - `--staged`: Index only staged changes
  - `--rev <ref>`: Index specific commit/branch
  - `--reindex`: Force full reindex
- `ember find <query>`: Hybrid search with filtering and ranking
  - `-k, --topk <n>`: Number of results (default: 20)
  - `--in <glob>`: Filter by file path pattern
  - `--lang <code>`: Filter by language
  - `--json`: JSON output for scripting
- `ember cat <index>`: Display full chunk content with optional context
  - `-C, --context <n>`: Show surrounding lines from source file
- `ember open <index>`: Open search result in $EDITOR at correct line number

#### Storage & Architecture
- SQLite-based storage with FTS5 full-text search
- BLOB-based vector storage (simple, fast for <100k chunks)
- Clean Architecture with strict layer separation (ports/adapters pattern)
- Protocol-based interfaces for swappable implementations

#### Embedding Model
- Jina Embeddings v2 Code (161M parameters, 768 dimensions)
- Code-aware, 8192 token context, 30+ language support
- CPU-friendly, ~600MB download (cached locally)

#### Testing & Quality
- 103 automated tests (unit, integration, performance)
- Performance validation on small/medium codebases
- 67% overall test coverage, 90%+ on critical paths

### Known Limitations

#### Configuration System
- `.ember/config.toml` is created but **not loaded or used** by v0.1 commands
- Settings in config.toml have no effect in v0.1
- File indexing determined by git tracking, not `include`/`ignore` patterns
- Model selection, chunking strategy, search defaults are hardcoded
- Configuration loading planned for v0.2

#### Commands Not Yet Implemented
- `ember export`: Export index bundles (planned for v0.2)
- `ember import`: Import index bundles (planned for v0.2)
- `ember audit`: Scan for secrets/credentials (planned for v0.2)
- `ember explain`: Result explainability (partial - scores shown)

#### Features Not Yet Implemented
- Cross-encoder reranking (flag exists but not implemented)
- Secret redaction patterns (defined but not applied)
- Watch mode for auto-sync
- HTTP server for AI agents
- Custom embedding models

### Performance

Measured on macOS (Apple Silicon):

| Metric | Small (50 files) | Medium (200 files) |
|--------|------------------|--------------------|
| Initial index | ~7s | ~55s |
| Incremental sync | <2s | ~11s |
| Search (avg) | 180ms | 180ms |
| Database size | 4MB | 16MB |

**Incremental sync speedup:** 9x+ faster than full reindex

### Dependencies

- Python 3.11+ (supports 3.11, 3.12, 3.13)
- PyTorch (CPU mode)
- sentence-transformers
- tree-sitter + language grammars
- SQLite 3.35+ (with FTS5 support)

### Documentation

- Comprehensive README with usage examples
- Architecture Decision Records (ADRs) in docs/decisions/
- Performance testing results in docs/PERFORMANCE.md
- Pre-release audit and UAT checklist in docs/
- Detailed development guide in CLAUDE.md

---

[0.1.0]: https://github.com/sammcvicker/ember/releases/tag/v0.1.0
