# Ember TODO - v0.1 MVP

**Source:** PRD §15 (Roadmap) and §19 (Acceptance Criteria)
**Current Phase:** Phase 0 (Meta Setup)
**Last Updated:** 2025-10-14

This file breaks down the PRD roadmap into atomic, testable tasks. Each task should take 30-60 minutes and be committable independently.

---

## Phase 0: Meta Setup & Development Continuity ✅

- [x] Create CLAUDE.md with complete structure
- [x] Create docs/ folder with progress.md
- [x] Create ADRs for architecture and storage decisions
- [x] Create this TODO.md file
- [ ] Create .gitignore for Python and .ember/
- [ ] Update pyproject.toml with metadata and scripts
- [ ] Initial commit of meta documentation

**Completion Criteria:**
- User can say "continue" and Claude picks up work immediately
- CLAUDE.md reflects accurate current state
- All documentation in place

---

## Phase 1: Foundation (~2-3 hours)

### 1.1 Project Structure
- [ ] Create clean architecture folder structure (ports/, domain/, core/, adapters/, app/, entrypoints/, shared/)
- [ ] Add __init__.py files to make packages importable
- [ ] Create empty placeholder files for key modules

### 1.2 Dependencies & Tooling
- [ ] Update pyproject.toml with all dependencies:
  - click (CLI framework)
  - ruff (linter/formatter)
  - pyright (type checker)
  - pytest (testing)
  - sqlite-vss (vector search)
  - tree-sitter + grammars (parsing)
  - blake3 (hashing)
- [ ] Run `uv sync` to install dependencies
- [ ] Create ruff.toml and pyproject.toml configs for linting
- [ ] Create pytest.ini or pyproject.toml test config
- [ ] Verify tooling works: `uv run ruff check .`, `uv run pytest`

### 1.3 Domain Entities (PRD §4)
- [ ] Create `domain/entities.py` with Chunk dataclass
  - Fields: id, project_id, path, lang, symbol, start/end_line, content, content_hash, file_hash, tree_sha, rev
  - Add blake3 content hashing method
  - Add __post_init__ validation
- [ ] Create RepoState dataclass (last_tree_sha, last_sync_mode, model, version)
- [ ] Create Query dataclass (text, topk, filters, json_output)
- [ ] Create SearchResult dataclass (chunk, score, preview)
- [ ] Write unit tests for domain entities

### 1.4 Port Interfaces (PRD §3, §17, §18)
- [ ] Create `ports/repositories.py`:
  - ChunkRepository protocol (add, get, find_by_hash, delete, list_all)
  - MetaRepository protocol (get, set, delete)
  - FileRepository protocol (track, get_state)
- [ ] Create `ports/embedders.py`:
  - Embedder protocol (name, dim, fingerprint, embed_texts)
- [ ] Create `ports/search.py`:
  - TextSearch protocol (add, query)
  - VectorSearch protocol (add, query)
  - Reranker protocol (rerank)
  - Fuser protocol (combine)
- [ ] Create `ports/vcs.py`:
  - VCS protocol (get_tree_sha, diff_files, get_file_at_rev)
- [ ] Create `ports/fs.py`:
  - FileSystem protocol (read, write, exists, mkdir, glob)
- [ ] Add comprehensive docstrings to all protocols

### 1.5 CLI Skeleton
- [ ] Create `entrypoints/cli.py` with click group
- [ ] Add stub commands: init, sync, find, open, cat, export, import, audit
- [ ] Add --verbose, --quiet global flags
- [ ] Add --version flag
- [ ] Test: `uv run ember --help` shows all commands

### 1.6 Testing Infrastructure
- [ ] Create tests/ folder structure matching src
- [ ] Create conftest.py with common fixtures
- [ ] Create test helpers (mock repos, temp dirs)
- [ ] Add first test: test_cli_help_works
- [ ] Verify: `uv run pytest -v` runs

**Phase 1 Completion Criteria:**
- All folder structure in place
- All dependencies installed
- All port interfaces defined
- Domain entities created and tested
- CLI skeleton functional
- Tests run successfully

---

## Phase 2: Init Command (~2-3 hours)

### 2.1 Config Management (PRD §10)
- [ ] Create `domain/config.py` with Config dataclass
  - IndexConfig (model, chunk, line_window, overlap, include, ignore)
  - SearchConfig (topk, rerank, filters)
  - RedactionConfig (patterns, max_file_mb)
- [ ] Create default config template as TOML string
- [ ] Add config validation logic

### 2.2 SQLite Schema (PRD §4)
- [ ] Create `adapters/sqlite/schema.py` with DDL statements
  - chunks table
  - chunk_text FTS5 virtual table
  - vectors table
  - meta table
  - tags table
  - files table
  - All indexes
- [ ] Add schema version to meta table
- [ ] Create migration framework (simple version check)

### 2.3 File System Adapter
- [ ] Create `adapters/fs/local.py` implementing FileSystem protocol
  - Use pathlib.Path for all operations
  - Proper error handling
- [ ] Write tests for filesystem adapter

### 2.4 Init Use Case (PRD §2)
- [ ] Create `core/config/init_usecase.py`
  - Check if .ember/ already exists (error if so)
  - Create .ember/ directory
  - Write default config.toml
  - Initialize index.db with schema
  - Write initial state.json
  - Return success/failure result
- [ ] Add proper error handling and result types
- [ ] Write unit tests for InitUseCase

### 2.5 Wire Init Command
- [ ] Update `entrypoints/cli.py` init command
  - Create FileSystem adapter
  - Create InitUseCase with dependencies
  - Call use case
  - Handle result (success message or error)
  - Add --force flag to reinitialize
- [ ] Test manually: `uv run ember init`
- [ ] Write integration test for full init flow

**Phase 2 Completion Criteria:**
- `ember init` creates .ember/ with correct structure
- config.toml has sensible defaults
- index.db created with all tables
- state.json initialized
- Integration test passes
- Can run init multiple times (with --force)

---

## Phase 3: Git Integration (~3-4 hours)

### 3.1 Git Adapter (PRD §5)
- [ ] Create `adapters/git/git_cmd.py` implementing VCS protocol
  - get_tree_sha(ref) using `git rev-parse`
  - get_worktree_tree_sha() for current state
  - diff_files(from_sha, to_sha) returning list of (status, path)
  - get_file_content(path, ref)
  - Handle errors (not a repo, invalid ref)
- [ ] Write tests with fixture git repo

### 3.2 Git Use Cases
- [ ] Create `core/git/tree_usecase.py`
  - Get current tree SHA for worktree/staged/rev
  - Compare with last indexed tree SHA
- [ ] Create `core/git/diff_usecase.py`
  - Given two tree SHAs, return files changed
  - Categorize: added, modified, deleted, renamed
  - Handle rename detection

### 3.3 File Tracking
- [ ] Create `adapters/sqlite/file_repository.py` implementing FileRepository
  - track_file(path, hash, size, mtime)
  - get_file_state(path)
  - get_all_tracked_files()
- [ ] Write tests for file repository

**Phase 3 Completion Criteria:**
- Can get tree SHA for worktree/staged/commit
- Can diff between two tree SHAs
- Can track file state in DB
- All tests pass

---

## Phase 4: Chunking (~3-4 hours)

### 4.1 Tree-sitter Setup (PRD §6)
- [ ] Add tree-sitter language grammars to dependencies (Python, TypeScript, Go, Rust)
- [ ] Create `adapters/parsers/tree_sitter_chunker.py`
  - Load language grammar
  - Parse file into AST
  - Extract functions/classes/methods
  - Return chunks with metadata (symbol, start_line, end_line)
- [ ] Write tests with golden file examples

### 4.2 Fallback Chunker
- [ ] Create `adapters/parsers/line_chunker.py`
  - Sliding window (120 lines, stride 100, overlap 20)
  - For unknown file types
- [ ] Write tests for line chunker

### 4.3 Chunking Use Case
- [ ] Create `core/chunking/chunk_usecase.py`
  - Given file content and language, return chunks
  - Try tree-sitter, fall back to line chunker
  - Compute blake3 hash per chunk
  - Add overlap context if configured
- [ ] Write tests for chunking strategies

**Phase 4 Completion Criteria:**
- Can chunk Python/TypeScript/Go/Rust files
- Falls back to line chunking for unknown types
- Each chunk has content hash
- Tests with real code samples pass

---

## Phase 5: Embedding (~2-3 hours)

### 5.1 Model Selection (PRD §8)
- [ ] Research and choose default embedding model:
  - Small, code-tuned (bge-code, gte-code)
  - 384-768 dims
  - CPU-friendly
  - Permissive license
- [ ] Document choice in ADR

### 5.2 Local Embedder Adapter
- [ ] Create `adapters/embedders/local_embedder.py` implementing Embedder
  - Load model (using sentence-transformers or similar)
  - Implement embed_texts with batching
  - Generate fingerprint (model name + version + config)
  - Handle model not found errors
- [ ] Write tests (may need fixtures or mocks)

### 5.3 Embedding Use Case
- [ ] Create `core/indexing/embed_usecase.py`
  - Take list of chunks
  - Batch embed using Embedder port
  - Return chunk_id → embedding mapping
  - Handle errors (model unavailable, etc.)

**Phase 5 Completion Criteria:**
- Default model loads successfully
- Can embed batch of texts
- Fingerprint correctly identifies model
- Tests pass

---

## Phase 6: Indexing (~3-4 hours)

### 6.1 Chunk Repository
- [ ] Create `adapters/sqlite/chunk_repository.py` implementing ChunkRepository
  - add_chunk(chunk) with UPSERT logic
  - get_chunk(id)
  - find_by_content_hash(hash)
  - delete_chunk(id)
  - list_chunks(filters)
- [ ] Write tests for chunk repository

### 6.2 FTS Adapter (PRD §7)
- [ ] Create `adapters/fts/sqlite_fts.py` implementing TextSearch
  - add(chunk_id, text, metadata) - insert into FTS5
  - query(q, topk) - FTS5 MATCH, return [(chunk_id, score)]
  - Handle FTS5 query syntax errors
- [ ] Write tests for FTS adapter

### 6.3 Vector Storage Adapter
- [ ] Create `adapters/vss/sqlite_vss.py` implementing VectorSearch
  - Try to load sqlite-vss extension
  - add(chunk_id, vector)
  - query(vector, topk) - KNN search, return [(chunk_id, score)]
  - Fall back to FAISS if VSS unavailable (future)
- [ ] Write tests for vector adapter

### 6.4 Sync Use Case (PRD §5)
- [ ] Create `core/indexing/sync_usecase.py`
  - Get target tree SHA (worktree/staged/rev)
  - Compare with last indexed tree SHA
  - Get diff (added/modified/deleted files)
  - For each added/modified:
    - Read content
    - Chunk it
    - Embed chunks
    - Store in chunk repo
    - Index in FTS and VSS
  - For deleted:
    - Remove chunks from repo
  - Update state.json with new tree SHA
- [ ] Add progress logging
- [ ] Write integration tests

**Phase 6 Completion Criteria:**
- Can index a small repo (~100 files)
- Chunks stored in SQLite
- FTS5 index populated
- Vector index populated
- Incremental sync works (only processes changed files)
- Tests pass

---

## Phase 7: Sync Command (~1-2 hours)

### 7.1 Wire Sync Command
- [ ] Update `entrypoints/cli.py` sync command
  - Add --worktree, --staged, --rev flags
  - Add --reindex flag (force full reindex)
  - Create all adapters (FileSystem, VCS, Chunker, Embedder, Repos, Search)
  - Inject into SyncUseCase
  - Execute and show progress
  - Handle errors gracefully
- [ ] Add progress bar or status output
- [ ] Test manually on ember repo itself
- [ ] Write end-to-end test

**Phase 7 Completion Criteria:**
- `ember sync` indexes worktree successfully
- `ember sync --rev HEAD` indexes specific commit
- Incremental sync is fast (<2s for 1-file change)
- Progress visible to user
- Errors handled gracefully

---

## Phase 8: Retrieval (~3-4 hours)

### 8.1 Fusion Strategy (PRD §7)
- [ ] Create `core/retrieval/fusers.py` with fusion algorithms
  - ReciprocalRankFusion (RRF)
  - WeightedSum fusion
- [ ] Write tests for fusion logic

### 8.2 Find Use Case (PRD §7, §17)
- [ ] Create `core/retrieval/find_usecase.py`
  - Embed query text
  - Query TextSearch for BM25 results (topk=100)
  - Query VectorSearch for semantic results (topk=100)
  - Fuse results
  - Fetch full chunks from repo
  - Apply filters (path glob, language, tags)
  - Return top-k results
- [ ] Add explainability data (FTS terms matched, cosine sim)
- [ ] Write tests for find logic

### 8.3 Result Formatting
- [ ] Create `app/formatters.py` for output formatting
  - format_results_text(results) - human-readable
  - format_results_json(results) - stable schema (PRD §9)
- [ ] Write tests for formatters

**Phase 8 Completion Criteria:**
- Hybrid search works (combines BM25 + vector)
- Results are relevant and ranked
- Filters work (path, lang)
- JSON output has stable schema
- Tests pass

---

## Phase 9: Find Command (~1-2 hours)

### 9.1 Wire Find Command
- [ ] Update `entrypoints/cli.py` find command
  - Accept query argument
  - Add --topk, --json, --in, --lang, --filter flags
  - Create all adapters
  - Inject into FindUseCase
  - Execute and format results
  - Handle no results gracefully
- [ ] Test manually: `ember find "config loading"`
- [ ] Write end-to-end test

**Phase 9 Completion Criteria:**
- `ember find "query"` returns relevant results
- `ember find "query" --json` returns valid JSON
- `ember find "query" --in "src/**/*.py"` filters correctly
- Works on ember repo itself (dogfooding)

---

## Phase 10: Utility Commands (~1-2 hours)

### 10.1 Cat Command (PRD §2)
- [ ] Implement `ember cat <idx>` command
  - Get result by index from last find
  - Print chunk content with syntax highlighting
  - Add --context N flag for surrounding lines
- [ ] Store last find results in temp file or cache

### 10.2 Open Command (PRD §2)
- [ ] Implement `ember open <idx>` command
  - Get result by index
  - Open in $EDITOR at correct line range
  - Handle EDITOR not set

### 10.3 Explain Command (PRD §7)
- [ ] Implement `ember explain <idx>` command
  - Show FTS terms that matched
  - Show cosine similarity score
  - Show why result ranked where it did

**Phase 10 Completion Criteria:**
- `ember cat 1` shows chunk content
- `ember open 1` opens editor
- `ember explain 1` shows match reasons

---

## Phase 11: Export/Import (~2-3 hours)

### 11.1 Export Use Case (PRD §11)
- [ ] Create `core/export/export_usecase.py`
  - Copy index.db to bundle
  - Create manifest.json (tree_sha, model fingerprint, created_at)
  - Optional: strip content with --no-preview
  - Package as .tar or .zip
- [ ] Test export

### 11.2 Import Use Case (PRD §11)
- [ ] Create `core/export/import_usecase.py`
  - Unpack bundle
  - Validate manifest
  - Check model compatibility
  - Import index.db
  - Update state.json
- [ ] Test import

### 11.3 Wire Commands
- [ ] Implement `ember export` command
- [ ] Implement `ember import` command
- [ ] Test round-trip: export then import

**Phase 11 Completion Criteria:**
- Can export index to bundle
- Can import bundle without source code
- Can query imported index
- Manifest validates correctly

---

## Phase 12: Audit (~1-2 hours)

### 12.1 Redaction Patterns (PRD §11)
- [ ] Create `core/security/redaction.py`
  - Compile regex patterns from config
  - Apply to content before embedding
  - Replace with [REDACTED]

### 12.2 Audit Use Case (PRD §2)
- [ ] Create `core/security/audit_usecase.py`
  - Scan all chunks for secret patterns
  - Report matches with context
  - Suggest fixes

### 12.3 Wire Audit Command
- [ ] Implement `ember audit` command
  - Run audit use case
  - Format report
  - Exit with error code if secrets found

**Phase 12 Completion Criteria:**
- Default patterns catch API keys, tokens
- `ember audit` scans indexed content
- Reports likely secrets with locations

---

## Phase 13: Polish & Documentation (~2-3 hours)

### 13.1 Error Handling
- [ ] Review all error paths
- [ ] Add proper error messages
- [ ] Use structured error types (PRD §9)
- [ ] Add --verbose flag for debugging

### 13.2 Logging
- [ ] Set up structured logging
- [ ] Add log levels (debug, info, warn, error)
- [ ] Respect --quiet and --verbose flags

### 13.3 User Documentation
- [ ] Update README.md with:
  - What is Ember
  - Installation instructions
  - Quick start guide
  - Example usage
  - Links to PRD
- [ ] Add CONTRIBUTING.md if needed

### 13.4 Performance Testing (PRD §13, §19)
- [ ] Test on mid-size repo (~5k files)
- [ ] Verify: initial sync <2 min on M4 MBP
- [ ] Verify: incremental sync after 1-file edit <2s
- [ ] Profile if slow

### 13.5 Final Testing
- [ ] Run full test suite
- [ ] Test all CLI commands end-to-end
- [ ] Verify PRD acceptance criteria (§19)
- [ ] Fix any bugs found

**Phase 13 Completion Criteria:**
- All PRD acceptance criteria met
- README is clear and helpful
- Error messages are actionable
- Performance targets met
- All tests pass

---

## Phase 14: v0.1 Release

- [ ] Tag release: v0.1.0
- [ ] Write release notes
- [ ] Update CLAUDE.md for v0.2 planning
- [ ] Retrospective: what went well, what to improve

---

## Future Phases (Post-v0.1)

See PRD §15 for v0.2 and v0.3 roadmap:
- Cross-encoder reranker
- `explain` command enhancements
- `watch` mode with fsnotify
- HTTP server for agents
- Multi-project support
- Advanced filtering

---

## Notes

- Each checkbox represents ~30-60 minutes of focused work
- Tasks are designed to be atomic and testable
- Update CLAUDE.md after completing each section
- Update docs/progress.md with decisions and learnings
- Commit frequently at stable checkpoints
- Refer to PRD sections for detailed requirements
