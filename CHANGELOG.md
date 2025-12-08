# Changelog

All notable changes to Ember will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Go struct and interface extraction** (#232)
  - TreeSitter now extracts Go struct definitions: `type User struct { ... }`
  - TreeSitter now extracts Go interface definitions: `type Reader interface { ... }`
  - Works with generic types (Go 1.18+): `type Container[T any] struct { ... }`
  - Works with embedded interfaces: `type ReadWriter interface { Reader; Writer }`
  - Comprehensive test coverage for Go constructs (6 new test cases)

- **Rust struct, enum, and trait extraction** (#232)
  - TreeSitter now extracts Rust struct definitions: `struct User { ... }`, `struct Empty;`, `struct Tuple(i32, i32);`
  - TreeSitter now extracts Rust enum definitions: `enum Status { Active, Inactive }`
  - TreeSitter now extracts Rust trait definitions: `trait Display { ... }`
  - Works with generic types: `struct Container<T> { ... }`, `trait Iterator<T> { ... }`
  - Works with trait bounds: `trait Comparable: PartialEq + PartialOrd { ... }`
  - Comprehensive test coverage for Rust constructs (8 new test cases)

- **Comprehensive TypeScript TreeSitter test coverage** (#231)
  - Added 18 new test cases for TypeScript code extraction, bringing total to 40+ TS-related tests
  - Test coverage now matches Python's depth across all major TypeScript constructs
  - New tests cover: async functions, nested classes, generic functions/classes/arrow functions,
    decorators, malformed code handling, TSX functional/class components, method signatures,
    computed properties, function overloads, and namespaces
  - Tests document expected behavior for each TypeScript pattern

- **TypeScript/JavaScript export statement handling** (#230)
  - TreeSitter correctly captures exported functions, classes, interfaces, and type aliases
  - Exported declarations include the `export` keyword in chunk content
  - Comprehensive test coverage for all export patterns:
    - `export function processData()` - named function exports
    - `export class UserService` - class exports
    - `export const handler = () => {}` - arrow function exports
    - `export default class App` - default exports
    - `export interface Config` - interface exports
    - `export type Status = ...` - type alias exports
  - Works across TypeScript (.ts), JavaScript (.js), TSX (.tsx), and JSX (.jsx) files

- **Named arrow function extraction for TypeScript/JavaScript** (#229)
  - TreeSitter now extracts named arrow functions with proper symbol names
  - Supports all assignment patterns: `const foo = () => {}`, `let bar = () => {}`, `var baz = () => {}`
  - Works with async arrow functions: `const fetch = async () => {}`
  - Works with typed arrows: `const handler: Handler = () => {}`
  - Applies to TypeScript (.ts), JavaScript (.js), TSX (.tsx), and JSX (.jsx) files
  - Arrow functions now appear in search results with their variable names instead of "unnamed"

- **TypeScript type alias extraction support** (#228)
  - TreeSitter now extracts TypeScript `type` alias declarations as semantic chunks
  - Simple type aliases: `type UserId = string`
  - Union types: `type Status = 'active' | 'inactive' | 'pending'`
  - Generic type aliases: `type Handler<T> = (event: T) => void`
  - Complex mapped/conditional types: `type DeepPartial<T> = { [P in keyof T]?: DeepPartial<T[P]> }`
  - Type aliases have proper symbol names for search (e.g., "UserId", "Handler")
  - Also added to TSX files for React TypeScript projects

- **TypeScript interface extraction support** (#227)
  - TreeSitter now extracts TypeScript `interface` declarations as semantic chunks
  - Works with generic interfaces: `interface Foo<T>`, `interface KeyValuePair<K, V>`
  - Works with extended interfaces: `interface Admin extends User`
  - Interfaces have proper symbol names for search (e.g., "User", "Admin")
  - Also added to TSX files for React TypeScript projects

- **Global config fallback with `ember config` command group** (#225)
  - Config loading now supports a two-tier system: local (.ember/config.toml) and global (~/.config/ember/config.toml)
  - Local config overrides global config on a section-by-section basis
  - Global config location: `~/.config/ember/config.toml` (Linux/macOS), `%APPDATA%/ember/config.toml` (Windows)
  - Respects `XDG_CONFIG_HOME` environment variable on Linux/macOS
  - New `ember config` command group with subcommands:
    - `ember config show` - Display config locations and effective merged settings
    - `ember config edit [--global]` - Open config in your editor (creates if missing)
    - `ember config path [--global|--local]` - Print paths for scripting
  - Use cases: consistent settings across multiple repos, organization-wide defaults

- **Auto-detect hardware and recommend embedding model during init** (#224)
  - `ember init` now detects available system RAM and recommends an appropriate model
  - Shows resource detection output: available RAM, recommended model, and reasoning
  - Prompts user if recommended model differs from default (jina-code-v2)
  - New `--model` / `-m` flag to explicitly select model (jina-code-v2, bge-small, minilm, auto)
  - New `--yes` / `-y` flag to accept recommended model without prompting
  - `model = "auto"` in config now works: auto-selects based on system resources
  - New `psutil` dependency for reliable hardware detection
  - Selection thresholds: >=4GB → jina-code-v2, >=1GB → bge-small, <1GB → minilm

- **Embedding model selection logic with daemon support** (#223)
  - New model registry (`ember/adapters/local_models/registry.py`) centralizes model selection
  - Supports user-friendly presets (`jina-code-v2`, `minilm`, `bge-small`) and full HuggingFace IDs
  - Daemon mode now respects `model` config - can run MiniLM or BGE-small in daemon mode
  - Config validation rejects unknown model names with helpful error messages
  - `create_embedder()` factory function for consistent embedder creation
  - `get_model_info()` and `list_available_models()` for programmatic model discovery
  - All models (Jina, MiniLM, BGE-small) now work in both daemon and direct modes
  - Example config: `model = "minilm"` with `mode = "daemon"` for memory-efficient indexing

- **BGE-small retrieval-optimized embedding adapter** (#222)
  - New `BGESmallEmbedder` adapter using `BAAI/bge-small-en-v1.5` (33M params, 384 dims)
  - Uses only ~130MB RAM - good balance between accuracy and resource usage
  - Optimized for retrieval tasks, strong MTEB leaderboard performance
  - 512 token context length (vs 256 for MiniLM)
  - Can be selected via config: `model = "bge-small"` in `.ember/config.toml`

- **MiniLM lightweight embedding adapter for resource-constrained systems** (#221)
  - New `MiniLMEmbedder` adapter using `sentence-transformers/all-MiniLM-L6-v2` (22M params, 384 dims)
  - Uses only ~100MB RAM vs ~1.6GB for Jina - ideal for Raspberry Pi, CI, older laptops
  - ~5x faster inference than larger models
  - Can be selected via config: `model = "minilm"` in `.ember/config.toml`

- **Unified sync behavior with visible progress across all commands** (#209)
  - Added `ensure_synced()` helper function as single entry point for sync-before-run
  - `ember search` now shows "Syncing index..." message when auto-syncing (previously silent)
  - `ember find` continues to show progress bar in human mode, silent in JSON mode
  - New commands can easily add sync-before-run by calling `ensure_synced()`
  - Returns `SyncResult` with status information for commands that need it
  - Deprecated `check_and_auto_sync()` in favor of the new unified helper

### Changed
- **Added color separation to `ember search` results list for faster scanning** (#208)
  - File paths are magenta bold (consistent with `ember find`)
  - Matched symbol names are red bold (visual anchor - "the thing you searched for")
  - Line numbers use same styling as `ember cat` (dim white)
  - Removed scores from results list (visible in status bar instead)
  - Selected item uses underline only (no background highlight)
  - Uses ANSI color names to respect user's terminal theme (Solarized, Dracula, etc.)
  - Makes it easier to scan results list without relying solely on the preview pane

- **Simplified `ember find` highlighting for faster visual scanning** (#207)
  - `ember find` now uses red bold highlighting for matched symbols only
  - Removed syntax highlighting from find output (both with and without `--context`)
  - Line numbers are dim, body text is regular - easier to scan at a glance
  - `ember cat` and `ember search` (TUI) retain full syntax highlighting
  - Improves developer experience by reducing visual noise when locating symbols

### Fixed
- **Suppressed HuggingFace tokenizer fork warning during `ember search`** (#215)
  - Set `TOKENIZERS_PARALLELISM=false` before loading the embedding model
  - Also set the variable when spawning the daemon subprocess for belt-and-suspenders safety
  - Users can override by explicitly setting `TOKENIZERS_PARALLELISM=true` in their environment
  - Eliminates the distracting "parallelism has already been used" warning message

- **Fixed daemon status showing "PID None" when PID file is missing** (#214)
  - When daemon is running but PID file is missing/corrupted, status now recovers PID from daemon
  - Daemon health check now returns server PID, allowing status recovery
  - Status message now shows "PID unknown" instead of confusing "PID None" as fallback
  - Added `get_daemon_pid()` helper function to query daemon PID via health check

- **Fixed daemon startup race condition causing "running (PID None)" status** (#216)
  - When daemon startup timed out (>20s), the process was left running without a PID file
  - This caused `ember daemon status` to show "running (PID None)"
  - Now properly terminates unresponsive daemon processes before cleaning up PID file
  - Prevents orphan daemon processes from causing confusing status reports

- **Error messages in interactive search TUI now wrap instead of truncating** (#206)
  - Long error messages (e.g., "Search error: SQLite objects created in a thread...") were being cut off at terminal width
  - Error messages now display in a dedicated window with `wrap_lines=True`
  - Wrapping respects terminal width while maintaining red error styling

- **Fixed SQLite thread safety error in interactive search** (#204)
  - Interactive search (`ember search`) was failing with "SQLite objects created in a thread can only be used in that same thread"
  - Added `check_same_thread=False` to SQLite connections in FTS, vector search, and chunk repository adapters
  - This allows search operations to run in a thread executor for responsive UI while maintaining connection reuse
  - Added 5 new integration tests to verify cross-thread SQLite access works correctly

- **Interactive search now displays error messages instead of silently showing "No results found"** (#202)
  - Added `error_message` field to `InteractiveSearchSession` to track search errors
  - Added `set_error()` method to capture error state and clear stale results
  - Search exceptions now display meaningful error messages in red (e.g., "Search error: daemon connection failed")
  - Added "error" style to prompt_toolkit color palette
  - Added 6 new tests for error handling behavior

### Changed
- **Refactored ResultPresenter into focused components (SRP compliance)** (#182)
  - Extracted `JsonResultFormatter` for JSON serialization and cache formatting
  - Extracted `CompactPreviewRenderer` for compact preview rendering (3-line previews)
  - Extracted `ContextRenderer` for rendering results with surrounding context
  - `ResultPresenter` now acts as thin orchestrator delegating to specialized components
  - Each component has single responsibility and is independently testable
  - Added 8 new tests for extracted components
  - Maintains backward compatibility with existing API

- **Optimized slow daemon test (20s → 0.2s)** (#181)
  - Mocked `time.sleep` in `test_start_failure_during_ready_wait_cleans_pid` to skip actual waits
  - Test now completes in ~0.2s instead of 20+ seconds (100x speedup)
  - Full test suite time reduced by ~20 seconds

- **Consolidated duplicate git repository test fixtures** (#178)
  - Created shared helper functions in `tests/conftest.py`: `init_git_repo()`, `git_add_and_commit()`, `create_test_files()`, `create_git_repo()`
  - Replaced ~280 lines of duplicate git setup code across 10 test files
  - All test fixtures now use the consolidated helpers for consistent repository initialization
  - Reduces duplication and makes test infrastructure easier to maintain

### Added
- **Helpful error messages with context and hints** (#177)
  - New `EmberCliError` exception class with `hint` support for actionable guidance
  - Helper functions for common error patterns: `repo_not_found_error()`, `no_search_results_error()`, `path_not_in_repo_error()`, `index_out_of_range_error()`
  - All CLI errors now display a hint to help users resolve issues
  - Examples: "Not in an ember repository" → Hint: "Run 'ember init' in your project root"
  - Added 11 new tests for error handling

### Changed
- **Reduced `ResultPresenter._render_compact_preview()` complexity from C=12 to B=6** (#179)
  - Extracted `_safe_get_lines()` helper for safe 1-based line extraction with boundary clamping
  - Extracted `_render_highlighted_preview()` for syntax-highlighted output path
  - Extracted `_render_plain_preview()` for fallback chunk content rendering
  - Eliminated off-by-one error risks via centralized line extraction helper
  - Unified rendering algorithm with clear highlighting vs plain text paths
  - Added 13 unit tests covering line extraction edge cases

- **Reduced `GitAdapter.diff_files()` complexity from C=16 to B=4** (#176)
  - Extracted `_parse_status_code()` helper function for git status code parsing
  - Replaced 11-branch if/elif chain with table-driven lookup
  - Created `_EXACT_STATUS_MAP` for direct status code matches (A, D, M, T)
  - Created `_PREFIX_STATUS_MAP` for prefix matches (R###, C###)
  - Centralized path extraction logic with consistent fallback behavior
  - Added 15 unit tests covering all status codes and edge cases

### Added
- **Unit tests for DaemonServer** (#183)
  - Added 9 tests covering socket timeout handling, error backoff, and model cleanup
  - Tests verify server continues operating after timeouts and general exceptions
  - Tests verify backoff delay is applied on persistent errors
  - Tests verify model resources are properly released during cleanup

- **Unit tests for untested infrastructure modules** (#174)
  - Added 20 tests for SimpleVectorSearch (100% coverage) - covers cosine similarity, vector decoding, query operations
  - Added 11 tests for TomlConfigProvider (100% coverage) - covers valid/invalid TOML parsing, partial configs, defaults
  - Added 42 tests for Daemon Protocol (100% coverage) - covers Request/Response serialization, socket message handling

- **Input validation for domain entities** (#173)
  - Query validates `topk > 0` and non-empty text on construction
  - Chunk validates `start_line` and `end_line` are >= 1 and `start_line <= end_line`
  - IndexConfig validates `line_window > 0`, `line_stride > 0`, `overlap_lines >= 0`, and `overlap_lines < line_window`
  - SearchConfig validates `topk > 0`
  - RedactionConfig validates `max_file_mb > 0`
  - ModelConfig validates `daemon_timeout > 0` and `daemon_startup_timeout > 0`
  - Invalid configuration values now fail fast with clear error messages
  - Added 35 new tests covering validation edge cases

### Changed
- **Improved DaemonServer error handling and cleanup** (#183)
  - Added backoff delay (100ms) on persistent errors to prevent tight CPU loops
  - Added model resource cleanup on server shutdown to release memory
  - Cleaned up exception handling comments in serve_forever loop

- **Extract duplicate editor integration code** (#175)
  - Created `open_file_in_editor()` helper function for consistent editor handling
  - Moved `EDITOR_PATTERNS` and `get_editor_command()` to cli_utils module
  - Unified error handling across `search()` and `open_result()` commands
  - Both commands now use identical error messages and editor detection logic
  - Added 6 unit tests covering editor opening scenarios

- **Reduced `DaemonLifecycle.start()` complexity from C=13 to B=6** (#172)
  - Extracted `_wait_for_daemon_ready()` for consolidated health check waiting
  - Extracted `_cleanup_failed_startup()` for PID file cleanup after failures
  - Extracted `_read_stderr_output()` for safe stderr reading with logging
  - Extracted `_start_foreground()` for foreground daemon execution
  - Extracted `_spawn_background_process()` for background process creation
  - Extracted `_write_pid_file()` for PID file writing with process termination on failure
  - Extracted `_check_instant_failure()` for early process failure detection
  - Extracted `_handle_startup_timeout()` for timeout error handling
  - Main `start()` function reduced to simple orchestration of helper methods

- **Removed architecture violation: adapter import in core layer** (#180)
  - `InitUseCase` now uses dependency injection for database initialization
  - Created `DatabaseInitializer` port interface in `ember/ports/database.py`
  - Created `SqliteDatabaseInitializer` adapter implementation
  - Core layer (`ember/core/`) no longer imports from adapters layer
  - Clean architecture dependency rule is now fully restored

- **Reduced `cat` command complexity from C=16 to C=5** (#171)
  - Extracted `lookup_result_from_cache()` helper for numeric index lookups
  - Extracted `lookup_result_by_hash()` helper for hash-based chunk lookups
  - Extracted `display_content_with_context()` helper for context line display
  - Extracted `display_content_with_highlighting()` helper for syntax highlighting
  - Main `cat` function reduced from 130 lines to ~50 lines
  - All helpers are individually testable with 11 new unit tests

- **ResultPresenter refactored to use dependency injection for file I/O** (#170)
  - Extracted file reading from core presentation layer to respect clean architecture
  - ResultPresenter now accepts a FileSystem port via constructor injection
  - Added `read_text_lines()` method to FileSystem protocol and LocalFileSystem adapter
  - Tests can now easily mock file content without touching the filesystem
  - Core layer no longer directly performs file I/O operations

### Added
- **Comprehensive unit tests for ResultPresenter class** (#149)
  - Increased test coverage from 76% to 100%
  - Added 11 new tests covering edge cases, error handling, and all code paths
  - Tests for `_get_context` method with file boundary handling
  - Tests for syntax highlighting paths in preview and context rendering
  - Tests for error handling when files are missing or unreadable
  - Fast tests using mocks (< 0.2s total for 28 tests)

### Improved
- **Optimized ChunkRepository.delete() by removing redundant get() call** (#148)
  - Deletes chunks directly using indexed chunk_id column instead of fetching full chunk first
  - Eliminates unnecessary database query and deserialization of chunk content
  - Improves performance for bulk deletions during file re-indexing
  - Added 3 unit tests for delete behavior

- **SqliteVecAdapter now caches database connections for better search performance** (#147)
  - Connection is reused across operations instead of creating new ones per call
  - sqlite-vec extension loaded once instead of per operation
  - Reduces overhead for high-frequency search operations
  - Now follows same connection management pattern as other repository classes

- **Missing chunks warning now includes recovery guidance** (#146)
  - Warning message now suggests running `ember sync --force` to rebuild the index
  - Directs users to report an issue if the problem persists
  - Helps users resolve index corruption or stale data issues

### Fixed
- **Resolve 466 ResourceWarning for unclosed SQLite database connections** (#184)
  - Added autouse pytest fixture to garbage collect database connections after each test
  - Added pytest warning filter to suppress remaining ResourceWarning during test teardown
  - Note: Production code properly supports context managers (tested in test_repository_context_manager.py)
  - Test suite now runs cleanly with 0 warnings

- **Fix daemon end-to-end tests failing with health check timeout** (#185)
  - Fixed socket path length issue: Unix domain sockets have ~104 char limit on macOS
  - Test fixtures now use short paths in `/tmp` instead of pytest's long temp paths
  - Fixed zombie process detection in `is_process_alive()` by reaping child processes
  - Increased SIGKILL verification timeout from 0.5s to 2.5s with retry loop
  - Added `auto_start=False` to fallback test to ensure proper fallback behavior

- **Fix race condition in daemon PID file management** (#152)
  - PID file is now written immediately after spawning daemon process
  - Eliminates race where process could die between alive-check and PID write
  - PID file properly cleaned up in all error paths (instant failure, write failure)
  - If PID file write fails, spawned process is terminated to prevent orphans
  - Added 2 unit tests for PID file handling

- **Add logging when TOML config parsing fails** (#145)
  - Config parsing failures now log a warning with the error details
  - Missing config file (expected) does not log a warning
  - Invalid TOML syntax logs a clear message to help users debug config issues
  - Graceful fallback to defaults still works, but users are now informed

- **Improve "No changes detected" feedback clarity** (#143)
  - Sync feedback now correctly distinguishes between full and incremental scans
  - Previously always showed "(full scan)" even for incremental scans
  - Now shows "(full scan completed)" or "(incremental scan completed)" as appropriate
  - Helps users understand what type of scan was performed

### Changed
- **Extracted common repo_root initialization pattern in CLI** (#151)
  - Added `get_ember_repo_root()` helper function to reduce code duplication
  - Consolidated 5 command implementations (sync, find, search, cat, open, status)
  - Consistent error handling and messaging across all commands
  - Added 3 unit tests for the helper function

- **Refactored render_syntax_highlighted for reduced complexity and maintainability** (#137)
  - Extracted `AnsiCodes` class with named constants for ANSI escape sequences (replaces magic strings)
  - Extracted `EXTENSION_TO_LEXER` mapping as module-level constant for file extension detection
  - Extracted `_get_lexer()` helper for Pygments lexer selection with fallback handling
  - Extracted `_get_token_color_map()` for configurable token-to-color mapping
  - Extracted `_find_token_color()` for token hierarchy lookup
  - Extracted `_colorize_text()` for ANSI color application
  - Extracted `_format_line_number()` for consistent line number formatting
  - Main function reduced from 92 lines to 32 lines with clear single responsibility
  - Added 23 unit tests covering all aspects of syntax highlighting
  - No functional changes - pure refactoring for maintainability and future extensibility

- **Refactored IndexingUseCase._get_files_to_index for reduced complexity** (#136)
  - Reduced cyclomatic complexity from C15 to A4 (main method)
  - Extracted `_determine_files_to_sync()` for git state handling (B6)
  - Extracted `_filter_code_files()` for extension filtering (A3)
  - Extracted `_apply_path_filters()` for glob pattern matching (A5)
  - Each extracted method has single responsibility and is independently testable
  - Added 18 unit tests covering all edge cases
  - No functional changes - pure refactoring for maintainability

- **Refactored ResultPresenter for reduced complexity** (#135)
  - Reduced `format_human_output` cyclomatic complexity from C19 to under threshold
  - Extracted display settings, file reading, result grouping, and rendering logic into focused methods
  - File reading logic now uses single `_read_file_lines()` method (was duplicated in 3 places)
  - Each extracted method has single responsibility and is independently testable
  - Added comprehensive unit tests for all extracted methods (17 new tests)
  - No functional changes - pure refactoring for maintainability

### Fixed
- **Add logging for chunking failures during indexing** (#144)
  - Chunking failures now log a warning with the file path and error message
  - `IndexResponse` now includes `files_failed` count for tracking chunking failures
  - Summary log includes failed file count when failures occur
  - Helps users identify which files are failing and why
  - Preserves existing chunks on failure to avoid data loss

- **Make path filters mutually exclusive in find and search commands** (#142)
  - `ember find` PATH argument and `--in` filter are now mutually exclusive
  - `ember search` `--path` and `--in` flags are now mutually exclusive
  - Clear error message explains which options conflict and how to use them correctly
  - Prevents silent data loss where one filter was previously ignored
  - Consistent behavior between find and search commands
  - Updated help text to document the mutual exclusivity
  - Added integration tests for filter combination behavior

- **Consistent header formatting for `ember cat` command** (#141)
  - Both numeric index and hash-based lookups now use identical header formatting
  - Previously, numeric lookups showed `[rank] line: (symbol)` while hash lookups showed `path [symbol]`
  - Now both use: line 1 shows path, line 2 shows `[rank] line: (symbol)` or `line: (symbol)`
  - Uses centralized EmberColors for consistent styling (magenta paths, green ranks, red symbols)
  - Added integration test to verify header format consistency

- **GitAdapter now raises exception on index restoration failure** (#140)
  - `get_worktree_tree_sha()` now raises `RuntimeError` if git index restoration fails
  - Previously, restoration failures were silently logged as warnings
  - Error message includes recovery guidance: suggests running `git status` and `git reset`
  - Prevents silent repository corruption that could cause data loss
  - Added comprehensive tests for restoration failure scenarios

### Added
- **Context manager support for all repository classes** (#138)
  - All SQLite repository classes now implement the context manager protocol (`__enter__`/`__exit__`)
  - Enables proper resource cleanup with `with` statement: `with SQLiteChunkRepository(db_path) as repo: ...`
  - Connection is automatically closed when exiting the context
  - Supports gradual migration to context-managed resource handling
  - Prevents database connection leaks in long-running processes
  - Affected classes: `SQLiteChunkRepository`, `SQLiteFileRepository`, `SQLiteVectorRepository`, `SQLiteMetaRepository`, `SQLiteFTS`, `SqliteVecAdapter`
  - Added comprehensive unit tests for context manager behavior

### Added
- **Added syntax highlighting to `ember find` (non-context mode)**
  - `ember find` now applies syntax highlighting by default, matching `ember find --context` behavior
  - Shows compact 3-line preview with syntax highlighting (keeps distinction from `ember cat`)
  - Uses terminal-native ANSI colors consistent with other commands
  - Automatically detects language from file extension
  - Respects `display.syntax_highlighting` config setting (can be disabled)
  - Uses configured theme from `display.theme` (default: "ansi")
  - Graceful fallback to plain text if file not readable or highlighting fails

### Fixed
- **Removed ellipses (`...`) from `ember find` output**
  - Preview no longer shows `...` at the end of truncated chunks
  - Consistent behavior between context and non-context modes

- **Fixed `ember find -C/--context` output format to match ripgrep-style** (#129)
  - Context output now uses compact ripgrep-style format: `[rank] line_num:content`
  - Shows only N lines before and after the match line (not the entire chunk)
  - Context lines are dimmed and indented for visual distinction
  - Rank indicator appears only on the match line (not on context lines)
  - Maintains consistency with non-context output format
  - Significantly improves readability for large code chunks
  - Works with both syntax highlighting enabled and disabled
  - Updated integration tests to verify new format

- **Improved daemon startup error reporting in interactive mode** (#126)
  - Daemon now starts and verifies health BEFORE entering interactive search TUI
  - Startup failures are caught early and display clean error messages
  - Prevents TUI corruption from daemon errors during initialization
  - Error messages show detailed information including exit code, stderr, and log file location
  - Added test coverage for daemon startup failure scenarios

- **Fixed stderr file descriptor leak on daemon startup failure** (#139)
  - stderr pipe is now closed in all exit paths using try/finally
  - Prevents file descriptor exhaustion from repeated daemon startup failures
  - Added test to verify stderr cleanup on instant daemon failure

- **Fixed missing chunks during search retrieval** (#125)
  - Search adapters now return the actual `chunk_id` stored in the database instead of computing it on-the-fly
  - Prevents "Missing chunks during retrieval" warnings caused by ID mismatches
  - Improves search reliability and data integrity
  - Updated FTS, sqlite-vec, and simple vector search adapters
  - Added regression tests to prevent future occurrences

- **Suppressed logging during interactive search** (#124)
  - All logging output is now disabled during `ember search` interactive TUI mode
  - Prevents terminal corruption from stderr output (warnings, info messages)
  - Logging is automatically restored after the TUI exits
  - Handles daemon startup messages, missing chunk warnings, and other log output
  - Comprehensive test coverage (5 new unit tests)

- **Improved spacing in `ember find --context` output** (#123)
  - Multiple results from the same file now have blank lines between them for better readability
  - Results are visually separated making it easier to distinguish individual matches
  - Test coverage added to verify proper spacing behavior

### Added
- **Syntax highlighting for interactive search preview pane** (#120)
  - `ember search` preview pane (ctrl-v) now displays code with syntax highlighting by default
  - Uses terminal-native ANSI colors consistent with `ember cat` and `ember find --context`
  - Automatically detects language from file extension
  - Respects `display.syntax_highlighting` config setting (can be disabled)
  - Uses configured theme from `display.theme` (default: "ansi")
  - Graceful fallback to plain text if highlighting fails
  - Preview pane scrolling still works correctly with highlighted code
  - Comprehensive test coverage (5 new unit tests)

- **Syntax highlighting for `ember find --context` output** (#119)
  - `ember find --context N` now displays code with syntax highlighting by default
  - Uses same terminal-native ANSI colors as `ember cat` for consistent experience
  - Automatically detects language from file extension
  - Shows line numbers with syntax-highlighted code
  - Respects `display.syntax_highlighting` config setting (can be disabled)
  - Uses configured theme from `display.theme` (default: "ansi")
  - Graceful fallback to original pipe-separated format when highlighting is disabled
  - Updated config I/O to support model and display configuration sections
  - Comprehensive test coverage (7 new tests)

- **Syntax highlighting for `ember cat` command** (#118)
  - `ember cat` now displays code with syntax highlighting by default using terminal-native colors
  - **Seamless integration** - Uses ANSI 16-color palette that respects your terminal theme (Solarized, Dracula, base16, etc.)
  - Automatically detects language from file extension (.py, .ts, .js, .go, .rs, etc.)
  - Shows line numbers with dimmed formatting
  - Respects `display.syntax_highlighting` config setting (can be disabled)
  - Uses configured theme from `display.theme` (default: "ansi" for terminal colors)
  - Graceful fallback to plain text if highlighting fails
  - Works with both numeric indexes and chunk hash IDs
  - Comprehensive test coverage (7 new tests)

- **Syntax highlighting infrastructure with Pygments** (#116)
  - Added `render_syntax_highlighted()` function for code highlighting using Pygments
  - **Default "ansi" theme respects terminal color scheme** - batteries included, zero config
  - Supports 15+ languages (Python, TypeScript, JavaScript, Go, Rust, Java, C/C++, C#, Ruby, etc.)
  - Automatic language detection from file extensions
  - Added `DisplayConfig` to domain configuration for display preferences:
    - `syntax_highlighting`: Enable/disable syntax highlighting (default: True)
    - `color_scheme`: Color output mode - "auto", "always", or "never" (default: "auto")
    - `theme`: Syntax highlighting theme (default: "ansi" for terminal colors, alternative: "monokai", etc.)
  - Infrastructure ready for use in `ember find --context` and interactive search preview

### Changed
- **Centralized color scheme across all commands** (#116)
  - Created `ember/core/presentation/colors.py` with centralized color palette
  - All commands now use consistent colors: paths (magenta), symbols (red/orange), ranks (green), line numbers (dimmed)
  - Updated `ResultPresenter`, `cli_utils`, and interactive search UI to use centralized colors
  - Improved maintainability - colors defined once and reused everywhere
  - No user-facing changes - internal refactoring for consistency

### Added
- **Interactive search interface with `ember search` command** (#114)
  - fzf-style interactive search UI with real-time results as you type
  - Keyboard navigation: arrow keys, ctrl-n/p, ctrl-d/u for page up/down
  - Live preview pane showing code context (toggle with ctrl-v)
  - Direct file opening in $EDITOR with Enter key
  - Search mode switching (hybrid/bm25/vector) with ctrl-r
  - Debounced search with 150ms delay for smooth typing experience
  - Async search with cancellation support for instant feedback
  - Supports all existing filters: --path, --in, --lang
  - Auto-sync before search (disable with --no-sync)
  - Built with prompt_toolkit for robust terminal UI

## [1.1.0] - 2025-11-06

### Added
- **Add -C/--context flag to `ember find` command** (#108)
  - Show surrounding lines of context inline with search results
  - Works with both human-readable and JSON output formats
  - Matches ripgrep's `-C` flag behavior for familiar UX
  - Reduces round-trips by eliminating need for separate `ember cat` calls
  - Improves agent workflow efficiency - get full context in single API call
  - Context displayed with line numbers, dimmed for non-chunk lines
  - JSON output includes structured `context` field with before/after/chunk sections
  - Fully backward compatible - defaults to 0 (no context)
  - Works with all existing flags: `--topk`, `--in`, `--lang`, `--json`

- **Stable hash-based chunk IDs for parallel agent workflows** (#107)
  - `ember find --json` now includes stable `id` field for each result
  - `ember cat` now accepts both numeric indexes (legacy) and chunk hash IDs
  - Supports short hash prefixes (e.g., `ember cat a1b2c3d4`) like git SHAs
  - Enables stateless, parallel chunk retrieval without .last_search.json dependency
  - Hash-based lookups work without prior `ember find` execution
  - Helpful error messages for ambiguous or non-existent hash prefixes
  - Full backward compatibility maintained for numeric index workflows

### Changed
- **Updated README.md for v1.0.0 release** (#109)
  - Updated test count badge from 116 to 271 tests
  - Added comprehensive documentation for daemon-based model server and `ember daemon` commands
  - Added documentation for `ember status` command
  - Updated "Why Ember?" section to highlight 18.6x daemon speedup
  - Updated Configuration section to reflect v1.0.0 features (daemon settings, untracked file indexing)
  - Updated File Indexing section to document untracked/unstaged file support
  - Updated Architecture section to mention sqlite-vec instead of BLOB-based storage
  - Updated Performance section with daemon vs direct mode benchmarks
  - Updated Roadmap to show v1.0.0 as released with all completed features
  - Updated FAQ with daemon-related questions and v1.0.0 config settings
  - Updated Quality Standards section with correct test count (271 tests)
  - Added sqlite-vec to Credits section
  - Fixed typo in "Zero dependencies" bullet point
  - Fixed installation URL from "yourusername" to "sammcvicker"

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
