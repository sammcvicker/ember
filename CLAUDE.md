# Ember Development Guide for Claude

## 🚦 QUICK START (Read This First Every Session)

When the user says "continue" or similar, follow this pattern:

1. **Read this file completely** (you are here)
2. **Check recent work**: `git log --oneline -5`
3. **Review current state**: See "Current State" section below
4. **Check next priority**: See "Next Priority" section below
5. **Execute top priority task**: Work through it completely
6. **Update documentation**: Update progress.md and this file
7. **Commit changes**: Follow commit guidelines below

**The goal**: Any session should be able to pick up work with ZERO external context.

---

## 📍 CURRENT STATE

**Phase:** Phase 6 Complete → Ready for Phase 7 (Search Use Case)
**Last Session:** 2025-10-14 (Session 7)
**Last Completed:** Phase 6 - Full indexing pipeline (git → chunk → embed → store)
**Active Work:** Ready to begin Phase 7 - Search use case (FTS5 + vector retrieval)
**Blockers:** None

---

## 🎯 NEXT PRIORITY (Work Top to Bottom)

### Phase 2: Init Command - COMPLETE ✅
1. [x] Create Config domain model in `domain/config.py` with sensible defaults
2. [x] Create default config.toml template
3. [x] Implement SQLite schema in `adapters/sqlite/schema.py` (chunks, chunk_text FTS5, vectors, meta, files tables)
4. [x] Create FileSystem adapter in `adapters/fs/local.py`
5. [x] Implement InitUseCase in `core/config/init_usecase.py`
6. [x] Wire init command to InitUseCase in CLI
7. [x] Test: `ember init` creates .ember/ with config.toml, index.db, state.json
8. [x] Write integration test for init flow

### Phase 3: Git Integration - COMPLETE ✅
1. [x] Create Git adapter implementing VCS protocol
2. [x] Implement tree SHA and diff operations (including worktree SHA with unstaged changes)
3. [x] Create file tracking repository
4. [x] Test with fixture git repo (14 tests, all passing)

### Phase 4: Chunking - COMPLETE ✅
1. [x] Add tree-sitter language grammars to dependencies
2. [x] Create tree-sitter adapter for code-aware chunking (functions/classes)
3. [x] Create fallback line-based chunker (120 lines, stride 100, overlap 20)
4. [x] Create ChunkingUseCase that tries tree-sitter then falls back
5. [x] Test with real code samples (Python, TypeScript, Go, Rust)

### Phase 5: Embedding - COMPLETE ✅
1. [x] Research and choose default embedding model (small, code-tuned, CPU-friendly)
2. [x] Create local embedder adapter implementing Embedder protocol
3. [x] Implement embed_texts with batching
4. [x] Generate model fingerprint for determinism
5. [x] Write tests for embedding adapter (13 tests, all passing)
6. [x] Document model choice in ADR 003

### Phase 6: Indexing Use Case - COMPLETE ✅
1. [x] Create ChunkRepository adapter in `adapters/sqlite/chunk_repository.py`
2. [x] Create MetaRepository adapter in `adapters/sqlite/meta_repository.py`
3. [x] Implement vector storage (start with simple BLOB, optimize later)
4. [x] Create IndexingUseCase in `core/indexing/index_usecase.py`
5. [x] Orchestrate: git diff → chunk files → embed → store
6. [x] Wire sync command to IndexingUseCase
7. [x] Test: `ember sync` indexes files and creates embeddings
8. [x] Write integration tests for full indexing flow

### Phase 7: Search Use Case (~3-4 hours total)
1. [ ] Create TextSearch adapter implementing FTS5 in `adapters/fts/sqlite_fts.py`
2. [ ] Create VectorSearch adapter for BLOB-based similarity in `adapters/vss/simple_vector_search.py`
3. [ ] Implement SearchUseCase in `core/retrieval/search_usecase.py`
4. [ ] Orchestrate hybrid search: BM25 + vector + fusion
5. [ ] Wire find command to SearchUseCase
6. [ ] Test retrieval with real queries
7. [ ] Verify ranking quality

---

## 🏗️ ARCHITECTURE QUICK REFERENCE

**Clean Architecture Layers** (PRD §3):
```
ember/
  app/                 # CLI commands, DTOs - NO business logic
  core/                # Use-cases & services (pure Python, no infra imports)
    indexing/
    retrieval/
    git/
    chunking/
    config/
    export/
  domain/              # Entities & value objects (Chunk, RepoState, Query)
  ports/               # Abstract interfaces (Protocol-based)
    repositories.py    # ChunkRepository, MetaRepository
    embedders.py       # Embedder protocol
    search.py          # TextSearch, VectorSearch, Reranker
    vcs.py             # VCS (git) interface
    fs.py              # FileSystem interface
  adapters/            # Infrastructure implementations
    sqlite/
    fts/
    vss/
    git_cmd/
    local_models/
  shared/              # Errors, logging, utils
  entrypoints/
    cli.py             # Click commands
```

**Key Principles**:
- `core/` depends ONLY on `ports/`, never on `adapters/`
- Adapters implement port protocols
- Inject dependencies via constructors
- All paths are absolute (use `pathlib.Path`)
- Type hints everywhere

**Storage** (PRD §4):
- SQLite at `.ember/index.db`
- FTS5 for text search (built-in)
- sqlite-vss or FAISS for vector search
- State file at `.ember/state.json`

---

## 📋 DEVELOPMENT WORKFLOW

### Before Starting Any Task:
- [ ] Read CLAUDE.md (this file) completely
- [ ] Check `git status` and recent commits
- [ ] Review relevant PRD section
- [ ] Check if tests exist and pass

### While Working:
- [ ] Follow clean architecture (no layer violations)
- [ ] Add type hints to all functions
- [ ] Write docstrings for public interfaces
- [ ] Keep changes atomic and focused
- [ ] Test as you go (when tests exist)
- [ ] Handle errors at boundaries

### Before Committing:
- [ ] Run tests if they exist: `uv run pytest`
- [ ] Run linter if configured: `uv run ruff check .`
- [ ] Update `docs/progress.md` with what was done and why
- [ ] Update this file's "Current State" section
- [ ] Update this file's "Next Priority" (mark completed, set new top)
- [ ] Write conventional commit message
- [ ] Include CLAUDE.md updates in the same commit

---

## 🔄 COMMIT GUIDELINES

**Format**: `<type>(<scope>): <description>`

**Types**:
- `feat`: New feature or capability
- `fix`: Bug fix
- `docs`: Documentation only (including CLAUDE.md updates)
- `refactor`: Code restructuring without behavior change
- `test`: Adding or updating tests
- `chore`: Build, dependencies, tooling

**Scopes**: `domain`, `core`, `ports`, `adapters`, `cli`, `meta`, `deps`

**Examples**:
```bash
feat(domain): add Chunk entity with blake3 content hashing
feat(ports): define Embedder and search protocol interfaces
feat(cli): implement init command with .ember/ setup
chore(deps): add click, ruff, pyright to pyproject.toml
docs(claude): update current state after init implementation
```

**Important**:
- Each commit should be a stable, working checkpoint
- Always update CLAUDE.md in the same commit to reflect new state
- Reference PRD sections when relevant (e.g., "per PRD §3")
- Commits should tell a story when read in sequence

---

## ✅ QUALITY STANDARDS (Never Break These)

1. **Architecture**: `core/` never imports from `adapters/`
2. **Types**: All public functions have type hints
3. **Protocols**: Use `Protocol` for ports, not ABC
4. **Injection**: Dependencies injected via __init__, never global
5. **Paths**: Use `pathlib.Path`, always absolute paths
6. **Errors**: Handle at boundaries, return typed results
7. **Docs**: Update CLAUDE.md per commit
8. **Tests**: Critical business logic must have tests
9. **Naming**: Clear, intention-revealing names
10. **SOLID**: Follow principles from PRD §3

---

## 📖 KEY DOCUMENTS

- **`prd.md`**: Product requirements (source of truth for features)
- **`TODO.md`**: Complete task backlog from PRD roadmap
- **`docs/progress.md`**: Detailed chronological implementation log
- **`docs/decisions/*.md`**: Architecture Decision Records (ADRs)
- **`CONTRIBUTING.md`**: Development standards (create when team grows)

**Reading Order for New Sessions**:
1. This file (CLAUDE.md)
2. git log -5
3. docs/progress.md (last entry)
4. TODO.md (current phase)
5. Relevant PRD section

---

## 🧭 COMMON COMMANDS

```bash
# Run ember CLI
uv run ember --help
uv run ember init

# Development
uv sync                    # Install/update dependencies
uv run pytest              # Run tests
uv run pytest -v           # Verbose test output
uv run ruff check .        # Lint code
uv run ruff format .       # Format code
uv run pyright             # Type check

# Git workflow
git status
git log --oneline -5
git add -A
git commit -m "feat(scope): description"
```

---

## 🚨 KNOWN ISSUES & GOTCAS

**Current**:
- None yet (project just starting)

**Dependencies**:
- Requires Python 3.13+ (per PRD)
- sqlite-vss may need system dependencies (fallback to FAISS planned)
- tree-sitter requires language grammars (add as needed)

**Platform**:
- Developed on macOS, should work on Linux
- Windows support TBD (Path handling should work)

---

## 🔍 DECISION LOG (Quick Reference)

See `docs/decisions/` for full ADRs.

- **001**: Clean Architecture with ports/adapters pattern
- **002**: SQLite + FTS5 + VSS for storage (simple, local, portable)
- **003**: Jina Embeddings v2 Code model (161M params, 768 dims, code-aware)

---

## 🎯 SUCCESS CRITERIA

This system works if:
1. ✅ User can say "continue" with no additional context
2. ✅ Any session can pick up work immediately
3. ✅ Each commit is a stable checkpoint
4. ✅ No repeated work or confusion between sessions
5. ✅ Documentation stays current automatically
6. ✅ Quality standards maintained consistently
7. ✅ Progress is visible and trackable

---

## 📝 NOTES FOR CLAUDE

**Remember**:
- You are the sole developer - own the quality
- This file is your source of truth for state
- Always update this file before committing
- Break large tasks into 30-60 minute chunks
- Ask questions in comments/docs if uncertain
- Document decisions as you make them
- Keep the "Next Priority" list current
- Trust the process - it scales as project grows

**When stuck**:
1. Re-read relevant PRD section
2. Check if similar pattern exists in codebase
3. Review relevant ADR in docs/decisions/
4. Document the blocker in CLAUDE.md "Current State"
5. Move to next unblocked task if needed

**End of each session**:
- Current State updated? ✓
- Next Priority updated? ✓
- Progress.md updated? ✓
- Changes committed? ✓
- Tests passing? ✓

---

**Last Updated**: 2025-10-14 (Session 7 - Phase 6 Complete)
**Format Version**: 1.0
