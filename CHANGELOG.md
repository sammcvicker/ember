# Changelog

All notable changes to Ember will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Stable hash-based chunk IDs for parallel agent workflows** (#107)
  - `ember find --json` now includes stable `id` field for each result
  - `ember cat` now accepts both numeric indexes (legacy) and chunk hash IDs
  - Supports short hash prefixes (e.g., `ember cat a1b2c3d4`) like git SHAs
  - Enables stateless, parallel chunk retrieval without .last_search.json dependency
  - Hash-based lookups work without prior `ember find` execution
  - Helpful error messages for ambiguous or non-existent hash prefixes
  - Full backward compatibility maintained for numeric index workflows

## [1.0.0] - 2025-10-29

### Changed
- **Refactored sync CLI command to reduce complexity** (#91)
  - Reduced cyclomatic complexity from C-level (20) to manageable levels by extracting 3 helper functions
  - Extracted `_parse_sync_mode()` for CLI option validation and sync mode determination
  - Extracted `_quick_check_unchanged()` for optimization logic to skip unchanged indexes
  - Extracted `_format_sync_results()` for result formatting and display
  - Improved readability and maintainability of sync command
  - All 257 tests passing - pure refactor, no behavior changes

### Performance
- **Implemented SQLite connection pooling to reduce overhead** (#87)
  - All SQLite repository adapters now reuse database connections instead of creating new ones for each operation
  - Reduces connection creation overhead from 1-5ms per operation to effectively zero
  - Batch indexing of 1000+ chunks is ~90%+ faster (3-5s overhead reduced to ~0.1s)
  - Memory overhead reduced by eliminating redundant connection setup/teardown
  - Added `close()` method to all SQLite repositories for explicit connection cleanup
  - All 210 tests passing - no functional changes, pure performance improvement

### Changed
- **Refactored IndexingUseCase.execute() to reduce complexity** (#86)
  - Reduced cyclomatic complexity from D-level (23) to manageable levels by extracting 5 helper methods
  - Extracted `_verify_model_compatibility()` for model fingerprint verification
  - Extracted `_ensure_model_loaded()` for eager model loading with progress reporting
  - Extracted `_index_files_with_progress()` for file indexing loop
  - Extracted `_update_metadata()` for metadata updates after successful indexing
  - Extracted `_create_success_response()` for success response creation with logging
  - Improved readability and maintainability of core indexing logic
  - All 210 tests passing - pure refactor, no behavior changes
- **Added missing methods to ChunkRepository port interface** (#82)
  - Added `delete_by_path()` and `delete_all_for_path()` to ChunkRepository protocol
  - Eliminates architectural violation where core layer called undocumented adapter methods
  - Port interface now matches adapter implementation completely
  - Improves maintainability and ensures future adapters implement required methods
  - No user-facing changes - internal architecture cleanup

### Fixed
- **find_ember_root() now respects git repository boundaries** (#100)
  - Prevents confusion between global daemon directory (~/.ember) and repository directories
  - Search now stops at git repository root, preventing false "Not a git repository" errors
  - Fixes issue where daemon running (with ~/.ember) would cause commands to fail in uninitialized repos
  - Added git boundary check to prevent crossing into parent directories beyond git root
  - Added comprehensive tests for git boundary checking and nested repository scenarios
  - Ensures ember only searches for .ember within the current git repository
- **Daemon protocol now handles large messages correctly and warns about data loss** (#83)
  - Increased buffer size from 1024 to 4096 bytes for better performance
  - Added warning when multiple messages received in single recv() call (potential data loss)
  - Documented one-message-per-connection protocol contract in function docstring
  - Added comprehensive tests for large messages (>4KB) and multiple messages
  - Prevents silent failures and makes debugging easier
- **Daemon startup race condition no longer creates stale PID files** (#85)
  - Fixed race condition where PID file was written before verifying daemon process survived
  - Now waits 0.1s after spawn and checks if process died instantly before writing PID file
  - Captures and reports stderr output when daemon fails to start (e.g., model loading errors)
  - Cleans up PID file if daemon exits during ready-wait loop
  - Prevents false success reports when daemon actually crashed
  - Added 2 new integration tests for daemon startup failure scenarios
- **Search now logs warnings when chunks can't be retrieved** (#88)
  - Missing chunks are now logged with count and sample IDs
  - Helps diagnose index corruption, stale data, or orphaned index entries
  - Warning includes first 5 missing chunk IDs for debugging
  - Previously silently dropped missing chunks, making problems invisible
  - Added test for missing chunk scenario
- **Daemon stop now properly handles SIGTERM failures and verifies SIGKILL** (#90)
  - SIGTERM failure now falls through to SIGKILL instead of giving up immediately
  - SIGKILL is now verified to actually kill the process before returning success
  - Cleanup of PID and socket files only happens after verified process death
  - Fixes issue where orphaned daemon processes could accumulate
  - Prevents stale PID files when process survives SIGKILL
  - Added 4 new tests for SIGTERM/SIGKILL edge cases and race conditions

### Added
- **CLI integration tests for all user-facing commands** (#62)
  - Added comprehensive test suite using `click.testing.CliRunner`
  - Tests cover all CLI commands: `init`, `sync`, `find`, `cat`, `open`, `status`
  - Verified exit codes, output formatting, error handling, and flag parsing
  - Tests ensure user-facing features work correctly end-to-end
  - Improved CLI test coverage from 0% to 72% (338 of 469 lines covered)
  - 38 new integration tests ensuring CLI reliability for v1.0.0
- **Model fingerprint change detection** (#65)
  - Detects when embedding model changes between indexing operations
  - Warns users that existing vectors may be incompatible with new model
  - Suggests running `ember sync --force` to rebuild index with new model
  - Prevents silent search quality degradation after model upgrades
  - Fingerprint comparison happens at start of each indexing operation

### Changed
- **CLI utilities no longer import from adapters layer** (#89)
  - Created `DaemonManager` protocol in `ports/daemon.py` for dependency inversion
  - Refactored `ensure_daemon_with_progress()` to accept injected `DaemonManager` instead of importing adapters
  - CLI commands (entrypoints layer) now inject `DaemonLifecycle` adapter implementation
  - Eliminates core → adapters dependency violation in Clean Architecture
  - Improves testability and flexibility (can swap daemon implementations without changing core code)
  - All 207 tests passing - no user-facing changes
- **Eliminated O(N) table scans with chunk_id column** (#59)
  - Added `chunk_id` column to chunks table for O(1) lookups
  - Created unique index on `chunk_id` for fast queries
  - Updated VectorRepository and ChunkRepository to use indexed column
  - Automatic migration from schema v1 to v2 on first run
  - Eliminates O(N²) complexity during indexing operations
  - Performance improvement: >10x faster on large repositories (10k+ chunks)
- **Extracted error response helper in IndexingUseCase** (#61)
  - Created `_create_error_response()` helper method for standardized error responses
  - Eliminated 60+ lines of duplicated IndexResponse creation code
  - All 6 exception handlers now use common helper
  - Improved maintainability - error response structure defined once
  - No user-facing changes - internal refactoring only
- **Extracted common CLI error handling to reduce boilerplate** (#67)
  - Created `handle_cli_errors()` decorator for consistent error handling across all commands
  - Eliminated 40+ lines of duplicated exception handling code
  - All commands (sync, find, cat, open) now use centralized error handler
  - Consistent error messages and verbose mode traceback support
  - No user-facing changes - internal refactoring only
- **Simplified editor detection logic in 'ember open' command** (#68)
  - Replaced 18-line if/elif chain with data-driven pattern lookup
  - Editor patterns defined once in `EDITOR_PATTERNS` dictionary
  - New editors can be added by updating the dictionary (no code changes)
  - Reduced code duplication (vim/emacs/nano now share pattern, subl/atom share pattern)
  - Improved maintainability and extensibility
  - No user-facing changes - internal refactoring only

### Fixed
- **Added vector dimension validation to prevent silent corruption** (#92)
  - VectorRepository now validates embedding dimensions before storing
  - Raises clear `ValueError` when dimension mismatch detected (e.g., expected 768, got 512)
  - Error messages include chunk ID for easy debugging
  - Optional validation via `expected_dim` parameter (backward compatible)
  - CLI automatically passes embedder dimension (768 for Jina v2 Code)
  - Prevents silent data corruption from malformed embeddings
- **Fixed vector encoding precision mismatch** (#84)
  - Standardized vector encoding to use float32 in both VectorRepository and SqliteVecAdapter
  - Eliminates precision loss during vector sync between storage layers
  - Reduces storage size by 50% (4 bytes vs 8 bytes per dimension)
  - Improves search quality by preventing gradual degradation from double→float conversion
  - Added comprehensive unit tests for vector round-trip precision
- **Fixed socket resource leaks in daemon client** (#64)
  - Added proper socket cleanup using finally blocks in `is_daemon_running()`
  - Socket now closed in all code paths, including exceptions
  - Fixed socket leak in `_connect()` method when connection fails
  - Prevents file descriptor leaks during daemon health checks and connection errors
- **Fixed path filtering to support glob patterns** (#60)
  - Replaced naive substring matching with proper glob pattern support
  - Now uses pathlib's `match()` method for flexible pattern matching
  - Supports wildcards: `*` (any files), `**` (any directories), `?` (single char)
  - Pattern "src/**/*.py" now correctly matches only Python files in src/ directory
  - Fixes false positives (e.g., "src" no longer matches "resources/src/")
  - Improves subdirectory support and path-scoped operations
- **Removed duplicate message in 'ember daemon status' output** (#73)
  - Daemon status now shows running state once instead of twice
  - Message field only displayed for error states (unresponsive, stale, stopped)
  - Cleaner, more concise status output
- **Improved error handling in 'ember sync' command** (#66)
  - Fixed duplicate "No changes detected" messages - now shows "(quick check)" vs "(full scan)" to indicate which code path executed
  - Quick check failures now always visible (not just in verbose mode) with clear warning message
  - Added validation for mutually exclusive sync options (--rev, --staged, --worktree)
  - Users now get immediate error when conflicting options are specified instead of silent last-one-wins behavior
  - Better observability: users can tell if quick check ran or full indexing occurred
- **Unreachable error handler in 'ember open' command** (#63)
  - Fixed unreachable `FileNotFoundError` exception handler
  - Now checks if editor exists using `shutil.which()` before running subprocess
  - Users get helpful error message when editor is not found instead of generic subprocess error
  - Removed dead code (unreachable exception handler)
- **Architecture violation: cli_utils imports from adapters** (#58)
  - Moved `check_and_auto_sync()` from `core/cli_utils.py` to `entrypoints/cli.py`
  - Eliminates circular dependency between `entrypoints/cli` and `core/cli_utils`
  - Restores clean architecture: `core/` now only depends on `ports/`, never `adapters/`
  - No user-facing changes - internal refactoring only
- **Daemon startup timeout increased and error reporting improved** (#50)
  - Increased daemon startup timeout from 10s to 20s to handle model loading
  - Model loading typically takes 3-5 seconds, but can be longer on first download
  - Now distinguishes between different failure modes with actionable error messages:
    - Process not responding after timeout (suggests checking logs)
    - Process crashed during startup (suggests checking logs)
  - Logs actual startup time when daemon becomes ready
  - Eliminates false "failed to start" warnings when daemon is successfully loading
- **Progress bars now clear properly during auto-sync** (#48)
  - Fixed progress bars not disappearing when `ember find` triggers auto-sync
  - Progress bars now fully clear before showing completion messages
  - Ensures clean, professional output without leftover progress bar artifacts
- **Path-scoped search now filters during SQL query instead of after retrieval** (#52)
  - Previously, path filtering happened after retrieving results, which could return fewer results than requested
  - Example: `ember find "query" tests/ -k 5` might only return 2 results if only 2 of the top-5 global results were in `tests/`
  - Now filters during SQL queries (both FTS5 and sqlite-vec), guaranteeing full topk results from filtered paths
  - Significantly improves performance by filtering earlier in the pipeline
  - Adds regression test to ensure path filtering returns full topk results
- **Progress bar stays in fixed position during indexing** (#44)
  - Progress bar no longer jumps horizontally as filenames change
  - Filename now appears after the progress percentage in a separate column
  - Makes progress display smooth and easier to read
  - Format: `⠋ Indexing files ━━━━━━━━━━━━━━━━━━━━ 50% src/adapters/file.py`

### Added
- **Subdirectory support** - Run ember from anywhere in your repository (#43)
  - All commands now work from any subdirectory, like git
  - `ember init` automatically finds git root and initializes there
  - `ember sync`, `ember find`, `ember cat`, `ember open` all discover `.ember/` by walking up directories
  - Clear error messages when not in an ember repository: "Not in an ember repository (or any parent directory)"
  - Path-scoped search with positional path argument:
    - `ember find "query"` - Search entire repo
    - `ember find "query" .` - Search current directory subtree
    - `ember find "query" src/` - Search specific path
  - Paths are relative to current working directory for natural workflow
  - Makes ember feel more natural and ergonomic for day-to-day use
- **Daemon-based model server for instant searches** (#46)
  - Keeps embedding model loaded in memory for near-instant searches
  - **18.6x faster** than direct mode: 43ms average vs 806ms
  - First search after daemon starts: ~1s (one-time model loading cost)
  - Subsequent searches: ~20ms (model already loaded)
  - Auto-starts transparently on first `ember find` or `ember sync` command
  - Auto-shuts down after 15 minutes of inactivity (configurable)
  - Manual daemon management: `ember daemon start|stop|status|restart`
  - Graceful fallback to direct mode if daemon fails
- **Index all files in working directory including untracked files** (#47)
  - Ember now indexes untracked and unstaged files, not just git-tracked files
  - Search what you see in your editor, regardless of git status
  - Creating a new file? It's immediately searchable after auto-sync
  - Respects .gitignore patterns (won't index node_modules/, .venv/, etc.)
  - Makes ember feel natural - no mental overhead about git staging
- **`ember status` command for index visibility** (#45)
  - See index state at a glance: `ember status`
  - Shows number of indexed files and chunks
  - Indicates whether index is up to date or needs sync
  - Displays current configuration (topk, chunk size, model)
  - Works from any subdirectory (like all ember commands)
  - Example output:
    ```
    ✓ Ember initialized at /Users/sam/project

    Index Status:
      Indexed files: 247
      Total chunks: 1,834
      Status: ✓ Up to date

    Configuration:
      Search results (topk): 5
      Chunk size: 512 tokens
      Model: jina-embeddings-v2-base-code
    ```
  - Configuration in `.ember/config.toml`:
    ```toml
    [model]
    mode = "daemon"  # or "direct" to disable daemon
    daemon_timeout = 900  # seconds (default: 15 min)
    ```
  - Eliminates the 2+ second model initialization delay on every command
  - Makes ember feel instant and effortless ("be like water")
- **Lazy daemon startup** - daemon only starts when embedding is needed
  - `ember sync` with no changes: 0.173s (was 2+ seconds)
  - `ember sync` with changes: 2.785s (daemon starts when needed)
  - Quick SHA check before creating indexing pipeline
  - Daemon auto-starts on first embedding request
- **Progress feedback during daemon startup**
  - Shows "Starting embedding daemon..." spinner during 3-5s startup
  - Transient progress that disappears when complete
  - Applied to `ember sync`, `ember find`, and `ember daemon start`
  - Makes startup feel responsive instead of hung

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
