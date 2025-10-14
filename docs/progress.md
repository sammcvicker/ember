# Ember Implementation Progress

This file tracks chronological implementation progress across sessions. Each entry should answer: What was built? Why? What decisions were made? What's next?

---

## 2025-10-14 Session 1 - Meta Setup & Development Continuity System

**Phase:** Foundation Setup (Phase 0) - COMPLETE ✅
**Duration:** ~60min
**Commits:** docs(meta): establish development continuity system

### Completed
- Created comprehensive CLAUDE.md as primary navigation and state machine
  - Quick Start workflow for session continuity
  - Current State tracking
  - Next Priority task queue
  - Development workflow and quality standards
  - Commit guidelines with conventional commits
  - Common commands reference
- Set up docs/ folder structure
  - This file (progress.md) for chronological logging
  - decisions/ folder for Architecture Decision Records
- Created ADRs:
  - 001-clean-architecture-layers.md (ports/adapters pattern)
  - 002-sqlite-storage.md (SQLite + FTS5 + VSS)
- Created TODO.md with complete v0.1 MVP task breakdown (14 phases, ~200 tasks)
- Updated .gitignore for Python, .ember/, IDE, OS-specific files
- Updated pyproject.toml with:
  - Project metadata and description
  - CLI entrypoint (ember.entrypoints.cli:main)
  - Dev dependencies (ruff, pyright, pytest)
  - Tool configurations (ruff, pyright, pytest)

### Decisions Made
- **CLAUDE.md as state machine**: Primary file that answers all questions a new session needs
  - What phase are we in?
  - What was last completed?
  - What should I do next?
  - How should I do it?
  - What standards must I follow?

- **Documentation as executable state**: Not passive notes, but version-controlled state that drives development

- **30-60 minute task granularity**: Each task should be atomic, testable, committable

- **Conventional commits with state updates**: Each commit includes CLAUDE.md update showing new state

### Architecture Decisions
See `docs/decisions/001-architecture-layers.md` and `002-storage-choice.md` for detailed ADRs.

### Next Steps
- Complete Phase 0 setup:
  - Create ADRs for architecture and storage decisions
  - Create TODO.md with complete v0.1 task breakdown
  - Set up .gitignore
  - Update pyproject.toml metadata
  - Commit everything
- Begin Phase 1: Foundation
  - Create folder structure
  - Set up dependencies
  - Define port interfaces

### Blockers
None

### Notes
- This system is designed for maximum session continuity
- User should be able to say "continue" with zero context
- All future sessions start by reading CLAUDE.md
- Quality standards enforced through pre-commit checklist

---

## 2025-10-14 Session 2 - Phase 1: Foundation

**Phase:** Phase 1 (Foundation) - COMPLETE ✅
**Duration:** ~90min
**Commits:** feat(foundation): implement clean architecture structure and port interfaces

### Completed
- Created complete clean architecture folder structure per PRD §3:
  - `ember/{app,core,domain,ports,adapters,shared,entrypoints}/`
  - Core use-case folders: `core/{indexing,retrieval,git,chunking,config,export}/`
  - Adapter folders: `adapters/{sqlite,fts,vss,git_cmd,local_models}/`
  - All packages have `__init__.py` files
- Set up all dependencies in pyproject.toml:
  - Runtime: click, blake3, tree-sitter (+language grammars), sentence-transformers, torch
  - Dev: ruff, pyright, pytest, pytest-cov
  - Installed with `uv pip install -e ".[dev]"`
- Defined all port interfaces using Protocol pattern:
  - `ports/repositories.py`: ChunkRepository, MetaRepository, FileRepository
  - `ports/embedders.py`: Embedder protocol
  - `ports/search.py`: TextSearch, VectorSearch, Reranker, Fuser
  - `ports/vcs.py`: VCS (Git) protocol
  - `ports/fs.py`: FileSystem protocol
  - All protocols have comprehensive docstrings
- Created domain entities in `domain/entities.py`:
  - Chunk dataclass with blake3 hashing methods
  - RepoState, Query, SearchResult dataclasses
  - Pure Python, no infrastructure dependencies
- Set up pytest testing infrastructure:
  - Test folder structure: `tests/{unit,integration,fixtures}/`
  - `conftest.py` with shared fixtures (temp_dir, sample_chunk, sample_chunks)
  - `test_entities.py` with 4 passing tests for Chunk entity
  - All tests pass with coverage reporting
- Created CLI skeleton with click:
  - All 8 commands stubbed: init, sync, find, cat, open, export, import, audit
  - Global flags: --verbose, --quiet, --version
  - Per-command options following PRD specifications
  - CLI registered at `ember.entrypoints.cli:main`
  - Verified: `uv run ember --help` works correctly

### Decisions Made
- **Protocol-based ports**: Using `typing.Protocol` instead of ABC for ports
  - More Pythonic, better type checking
  - No inheritance required for implementations
  - Follows structural subtyping pattern

- **blake3 for hashing**: Using blake3 instead of sha256
  - Faster than MD5, SHA1, SHA2
  - Better security properties
  - Deterministic chunk IDs

- **Comprehensive type hints**: All public APIs have complete type annotations
  - Supports pyright static type checking
  - Better IDE autocomplete and error detection

- **Test fixtures pattern**: Using pytest fixtures for common test data
  - DRY principle for test setup
  - Easy to extend with new fixtures

### Architecture Verification
- ✅ Clean architecture layers respected (no violations)
- ✅ All ports defined before adapters
- ✅ Domain entities are pure Python
- ✅ Type hints on all public interfaces
- ✅ Linter passes (ruff)
- ✅ Tests pass (4/4)
- ✅ CLI functional

### Next Steps
Begin Phase 2: Init Command
- Create Config domain model with defaults
- Implement SQLite schema creation
- Build InitUseCase in core/config/
- Wire init command to use case
- Test: `ember init` creates .ember/ directory

### Blockers
None

### Notes
- Phase 1 took slightly longer than estimated (90 min vs 2-3 hour estimate for full phase)
- Foundation is solid - all structure and interfaces in place
- Ready to start implementing actual business logic
- All quality standards maintained throughout

---

## 2025-10-14 Session 3 - Phase 2: Init Command

**Phase:** Phase 2 (Init Command) - COMPLETE ✅
**Duration:** ~90min
**Commits:** feat(init): implement complete init command with config, db, and state

### Completed
- Created Config domain model in `domain/config.py`:
  - IndexConfig, SearchConfig, RedactionConfig, EmberConfig dataclasses
  - Frozen dataclasses with sensible defaults matching PRD §10
  - Type-safe with Literal types for chunk strategy
- Created config I/O utilities in `shared/config_io.py`:
  - load_config() and save_config() using tomllib/tomli-w
  - create_default_config_file() with commented template
  - Added tomli-w dependency for TOML writing
- Implemented SQLite schema in `adapters/sqlite/schema.py`:
  - init_database() creates complete schema per PRD §4
  - Tables: chunks, chunk_text (FTS5), vectors, meta, tags, files
  - FTS5 triggers for automatic content indexing
  - Indexes for efficient queries (tree_sha+path, content_hash, etc.)
  - Schema versioning in meta table
- Created state I/O utilities in `shared/state_io.py`:
  - load_state() and save_state() for state.json
  - create_initial_state() for new indexes
  - ISO-8601 timestamps for tracking
- Created LocalFileSystem adapter in `adapters/fs/local.py`:
  - Implements FileSystem protocol using pathlib
  - All operations use absolute paths
  - Deterministic glob results (sorted)
- Implemented InitUseCase in `core/config/init_usecase.py`:
  - Clean architecture - orchestrates without infrastructure dependencies
  - InitRequest and InitResponse DTOs
  - Creates .ember/ directory with config.toml, index.db, state.json
  - Supports --force flag for reinitialization
  - Proper error handling (FileExistsError)
- Wired init command in CLI:
  - Updated `entrypoints/cli.py` to use InitUseCase
  - Added --force/-f flag
  - User-friendly output with checkmarks
  - Proper error messages and exit codes
- Comprehensive integration tests (7 tests, all passing):
  - test_init_creates_all_files
  - test_init_config_is_valid_toml
  - test_init_creates_valid_database_schema
  - test_init_creates_valid_state_json
  - test_init_fails_if_ember_dir_exists
  - test_init_force_reinitializes
  - test_init_database_has_fts5_triggers

### Decisions Made
- **TOML for config**: Human-readable, comments preserved in template
  - Used tomllib (built-in Python 3.11+) for reading
  - Added tomli-w for writing (maintains formatting)

- **Commented config template**: create_default_config_file() uses string template
  - Preserves helpful comments for users
  - Better UX than programmatic TOML generation

- **Frozen config dataclasses**: All config types are immutable
  - Prevents accidental modification
  - Clear that config is read-only during execution

- **FTS5 with Porter stemming**: Better English text matching
  - Using tokenize='porter unicode61' for FTS5
  - Automatic trigger-based sync between chunks and chunk_text

- **Schema versioning**: meta.schema_version for future migrations
  - Currently at version 1
  - check_schema_version() utility for migration checks

### Architecture Verification
- ✅ Clean architecture respected (core depends only on ports)
- ✅ InitUseCase has no infrastructure imports
- ✅ All adapters implement protocols correctly
- ✅ Type hints on all public interfaces
- ✅ Proper error handling at boundaries
- ✅ All tests pass (11/11)
- ✅ Integration tests cover happy path and error cases

### Testing Results
```
11 passed in 0.09s
Coverage: 50% (361 statements, 181 missing)
```

### Manual Testing
```bash
$ uv run ember init
Initialized ember index at /tmp/test/.ember
  ✓ Created config.toml
  ✓ Created index.db
  ✓ Created state.json

$ uv run ember init  # Without force
Error: Directory /tmp/test/.ember already exists. Use --force to reinitialize.

$ uv run ember init --force
Reinitialized existing ember index at /tmp/test/.ember
  ✓ Created config.toml
  ✓ Created index.db
  ✓ Created state.json
```

### Next Steps
Begin Phase 3: Git Integration
- Create Git adapter implementing VCS protocol
- Implement tree SHA computation
- Create git diff operations for incremental sync
- Build file tracking repository
- Test with fixture git repo

### Blockers
None

### Notes
- Phase 2 completed in ~90 minutes as estimated
- Init command is fully functional and tested
- Database schema includes all tables needed for MVP
- Config template has helpful comments for users
- All quality standards maintained
- Test coverage is good (100% for init use case)
- Ready to implement git integration for sync command

---

## 2025-10-14 Session 4 - Phase 3: Git Integration

**Phase:** Phase 3 (Git Integration) - COMPLETE ✅
**Duration:** ~90min
**Commits:** feat(git): implement Git adapter and FileRepository with comprehensive tests

### Completed
- Created Git adapter in `adapters/git_cmd/git_adapter.py`:
  - Implements VCS protocol using subprocess git commands
  - `get_tree_sha(ref)` - Gets tree SHA for any git ref (HEAD, branch, commit)
  - `get_worktree_tree_sha()` - Computes virtual tree SHA for worktree including unstaged changes
  - `diff_files(from_sha, to_sha)` - Returns changed files between tree SHAs with status (added/modified/deleted/renamed)
  - `get_file_content(path, ref)` - Retrieves file content at specific ref
  - Proper error handling with descriptive error messages
  - Uses git plumbing commands (hash-object, mktree) for worktree tree computation
- Implemented worktree tree SHA computation:
  - Uses `git ls-files` to get all tracked files
  - Hashes each file's current content with `git hash-object -w`
  - Builds tree structure with proper file modes (100644/100755)
  - Computes final tree SHA with `git mktree`
  - Correctly handles unstaged changes, deletions, and empty repos
- Created FileRepository adapter in `adapters/sqlite/file_repository.py`:
  - Implements FileRepository protocol for tracking indexed files
  - `track_file()` - UPSERT semantics for storing file metadata
  - `get_file_state()` - Retrieves tracked file metadata (hash, size, mtime)
  - `get_all_tracked_files()` - Returns all tracked paths sorted
  - Automatic `last_indexed_at` timestamp management
  - Proper connection lifecycle (open/close per operation)
- Comprehensive Git adapter tests (14 tests, all passing):
  - test_git_adapter_initialization
  - test_git_adapter_rejects_non_repo
  - test_get_tree_sha_for_head
  - test_get_tree_sha_for_invalid_ref
  - test_get_worktree_tree_sha
  - test_get_worktree_tree_sha_with_unstaged_changes (verifies unstaged change detection)
  - test_diff_files_between_commits
  - test_diff_files_from_empty_tree
  - test_diff_files_with_deletions
  - test_diff_files_with_renames (with -M flag)
  - test_get_file_content_at_head
  - test_get_file_content_nonexistent_file
  - test_get_file_content_invalid_ref
  - test_diff_files_returns_empty_for_identical_trees
- Comprehensive FileRepository tests (10 tests, all passing):
  - test_track_file
  - test_track_file_updates_existing (UPSERT verification)
  - test_get_file_state_nonexistent
  - test_get_all_tracked_files_empty
  - test_get_all_tracked_files
  - test_get_all_tracked_files_sorted
  - test_last_indexed_at_timestamp
  - test_track_file_with_absolute_path
  - test_track_multiple_files_independence
  - test_file_repository_connection_cleanup

### Decisions Made
- **Git subprocess approach**: Use subprocess to call git CLI commands
  - Simple, reliable, no need for libgit2 bindings
  - Leverages user's installed git version
  - Standard approach for git integrations

- **Worktree tree SHA implementation**: Compute virtual tree using git plumbing
  - Gets all tracked files with `git ls-files -z`
  - Hashes actual file content (not just index)
  - Properly detects unstaged changes
  - Returns git-compatible tree SHA for comparison

- **Connection-per-operation pattern**: FileRepository opens/closes DB per operation
  - Simpler than connection pooling for MVP
  - No connection leaks
  - Thread-safe by default
  - Can optimize later if needed

- **UPSERT for file tracking**: Use ON CONFLICT DO UPDATE
  - Prevents duplicate path errors
  - Automatically updates changed files
  - Single query for insert or update

### Architecture Verification
- ✅ Clean architecture respected (adapters implement ports)
- ✅ GitAdapter has no business logic, pure infrastructure
- ✅ FileRepository properly encapsulates SQLite operations
- ✅ All protocols correctly implemented
- ✅ Type hints on all public interfaces
- ✅ Proper error handling at boundaries
- ✅ All tests pass (35/35 total across project)
- ✅ Integration tests use real git repos (not mocks)

### Testing Results
```
35 passed in 1.42s
Coverage: 63% (494 statements, 182 missing)
Git adapter: 90% coverage (91 statements, 9 missing)
FileRepository: 100% coverage (36 statements, 0 missing)
```

### Next Steps
Begin Phase 4: Chunking
- Create tree-sitter adapter for code-aware chunking
- Implement fallback line-based chunker
- Create chunking use case
- Test with real code samples (Python, TypeScript, Go, Rust)

### Blockers
None

### Notes
- Phase 3 completed in ~90 minutes as estimated
- Git integration is robust and well-tested
- Worktree tree SHA correctly handles unstaged changes (critical for sync)
- FileRepository uses simple connection pattern (can optimize later)
- All git operations tested with real git repos (high confidence)
- Ready to implement chunking strategies
- Test coverage increased from 27% to 63%
- All quality standards maintained

---

## 2025-10-14 Session 5 - Phase 4: Chunking

**Phase:** Phase 4 (Chunking) - COMPLETE ✅
**Duration:** ~2 hours
**Commits:** (pending) feat(chunking): implement tree-sitter and line-based chunking with comprehensive tests

### Completed
- Created Chunker port in `ports/chunkers.py`:
  - ChunkData dataclass for raw chunk information
  - Chunker protocol with chunk_file() and supported_languages property
- Created tree-sitter adapter in `adapters/parsers/tree_sitter_chunker.py`:
  - Supports Python, TypeScript, JavaScript, Go, Rust
  - Extracts functions, classes, and methods using AST queries
  - Uses QueryCursor API with byte-position-based node matching
  - Handles nested definitions (extracts both classes and methods within)
  - Returns chunks sorted by line number
- Created line-based fallback chunker in `adapters/parsers/line_chunker.py`:
  - Sliding window implementation (120 lines, stride 100, 20-line overlap)
  - Configurable window size and stride
  - Universal fallback for unsupported languages
  - Handles edge cases (small files, exact window size)
- Implemented ChunkingUseCase in `core/chunking/chunk_usecase.py`:
  - Tries tree-sitter first for supported languages
  - Automatically falls back to line-based chunking
  - Clean architecture - depends only on Chunker port
  - Returns strategy used ("tree-sitter", "line-based", or "none")
- Comprehensive test suite (33 tests, all passing):
  - Tree-sitter tests (12 tests): Python, TypeScript, Go, Rust function/class extraction
  - Line chunker tests (11 tests): Window sizing, overlap, edge cases
  - Use case tests (10 tests): Strategy selection, fallback behavior, metadata preservation
- All tests pass (68 total across project)
- Test coverage increased from 63% to 71%

### Decisions Made
- **Tree-sitter query-based extraction**: Use tree-sitter Query and QueryCursor APIs
  - Adapted to new tree-sitter-py API (captures returns dict, not list of tuples)
  - Byte-position-based node matching instead of id() for stability
  - Separate language function names for TypeScript (language_typescript vs language)
  
- **Nested function extraction**: Extract both top-level and nested definitions
  - Classes contain their methods as separate chunks
  - More granular chunking improves retrieval quality
  - Test expectations updated to reflect this behavior

- **Simple ChunkData structure**: Minimal data before creating full Chunk entities
  - start_line, end_line, content, symbol, lang
  - Use case layer will add project_id, hashes, tree_sha later
  - Clean separation of concerns

- **Universal line-based fallback**: LineChunker returns empty set() for supported_languages
  - Indicates it supports all languages as a fallback
  - Use case checks tree-sitter support first

### Architecture Verification
- ✅ Clean architecture respected (core depends only on ports)
- ✅ ChunkingUseCase has no infrastructure imports
- ✅ Adapters implement Chunker protocol correctly
- ✅ Type hints on all public interfaces
- ✅ Proper error handling (empty lists on failures)
- ✅ All tests pass (68/68 total across project)
- ✅ Real code samples tested (Python, TypeScript, Go, Rust)

### Testing Results
```
68 passed in 1.45s
Coverage: 71% (644 statements, 189 missing)
Tree-sitter chunker: 91% coverage (76 statements, 7 missing)
Line chunker: 100% coverage (33 statements, 0 missing)
ChunkingUseCase: 100% coverage (27 statements, 0 missing)
```

### Technical Challenges
- **Tree-sitter API changes**: New version uses QueryCursor and returns dict from captures()
  - Required adaptation from legacy query.captures(node) → QueryCursor(query).captures(node)
  - Return format changed from list[(node, name)] to dict[name: [nodes]]
  
- **Node identity stability**: Python id() not stable across API calls
  - Switched to byte position tuples (start_byte, end_byte) for matching
  - Parent-child matching now works correctly

- **TypeScript language loading**: Different module structure than other languages
  - Has language_typescript() and language_tsx() instead of language()
  - Updated _LANG_MAP to include function name per language

### Next Steps
Begin Phase 5: Embedding
- Research and choose default embedding model (small, code-tuned, CPU-friendly)
- Create local embedder adapter implementing Embedder protocol
- Implement batched embedding with fingerprinting
- Test embedding functionality
- Document model choice

### Blockers
None

### Notes
- Phase 4 completed in ~2 hours (on the faster end of 3-4 hour estimate)
- Chunking is robust with good test coverage
- Tree-sitter extracts semantic units (functions, classes, methods)
- Line-based chunker provides solid fallback for unsupported languages
- Both chunkers tested with real code samples
- Ready to implement embedding with local models
- Test coverage continues to climb (now at 71%)
- All quality standards maintained
