# Changelog

All notable changes to Ember will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Simplified CLAUDE.md to be more concise (~50% reduction)
- Moved detailed maintainer procedures to MAINTAINER_GUIDE.md
- Reorganized documentation structure for better discoverability

### Added
- Created `develop` branch for ongoing development
- Created GitHub milestones for release planning (0.2.0, Backlog)
- Added MAINTAINER_GUIDE.md with comprehensive operational procedures
- Added docs/ARCHITECTURE.md with detailed technical architecture guide
- Created docs/archive/ for historical documentation

### Removed
- Moved historical v0.1.0 docs to docs/archive/ (AUDIT.md, UAT.md, progress.md)

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
