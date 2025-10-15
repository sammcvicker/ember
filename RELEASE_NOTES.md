# Ember v0.1.0 Release Notes

**Release Date:** October 15, 2025
**Status:** MVP Release

---

## Overview

Ember v0.1.0 is the first official release of Ember, a local codebase embedding and semantic search tool designed for developers and AI agents. This MVP release provides a complete workflow for indexing, searching, and navigating codebases using hybrid search (BM25 + vector embeddings).

---

## What's New

### Core Features

**🔍 Hybrid Search**
- Combines BM25 (keyword matching) with vector embeddings (semantic similarity)
- Reciprocal Rank Fusion (RRF) for balanced result ranking
- Both exact and conceptual code discovery in a single query

**⚡ Incremental Indexing**
- Diff-based sync detects and reindexes only changed files
- 9x+ speedup over full reindex on typical workflows
- Git tree SHA comparison for instant no-op detection

**🌐 Multi-Language Support**
- Tree-sitter-based semantic chunking for 9+ languages:
  - Python, TypeScript, JavaScript, Go, Rust
  - Java, C, C++, C#, Ruby
- Automatic fallback to line-based chunking for unsupported files
- Function/class/method extraction with symbol names

**🔗 Git Integration**
- Automatic file tracking via `git ls-files`
- Index working directory, staged changes, or specific commits
- Respects `.gitignore` and `.emberignore`
- Deterministic indexing via git tree SHAs

---

### Commands

#### `ember init`
Initialize Ember in your project. Creates `.ember/` directory with config, database, and state files.

```bash
ember init
# Initialized ember index at /path/to/project/.ember
#    ✓ Created config.toml
#    ✓ Created index.db
#    ✓ Created state.json
```

#### `ember sync`
Index your codebase. Automatically uses incremental sync after first full index.

```bash
# Index working directory (default)
ember sync

# Index only staged changes
ember sync --staged

# Index specific commit
ember sync --rev HEAD~3

# Force full reindex
ember sync --reindex
```

#### `ember find <query>`
Search indexed code with hybrid BM25 + vector search.

```bash
# Semantic search
ember find "user authentication logic" -k 5

# Filter by file type
ember find "database connection" --in "*.py"

# Filter by language
ember find "error handling" --lang python

# JSON output for scripting
ember find "API endpoint" --json
```

#### `ember cat <index>`
Display full content of a search result.

```bash
# Show chunk content
ember cat 1

# Show with 5 lines of context
ember cat 1 --context 5
```

#### `ember open <index>`
Open search result in your editor at the correct line number.

```bash
# Open in $EDITOR
ember open 1

# Works with vim, nvim, VS Code, etc.
export EDITOR=code
ember open 2
```

---

### Architecture & Storage

**Clean Architecture**
- Strict layer separation (domain → ports → adapters)
- Protocol-based interfaces for swappable implementations
- SOLID principles throughout
- No infrastructure dependencies in business logic

**Storage**
- SQLite database in `.ember/index.db`
- FTS5 virtual table for BM25 text search
- BLOB-based vector storage (fast for <100k chunks)
- State tracking in `.ember/state.json`

**Embedding Model**
- [Jina Embeddings v2 Code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code)
- 161M parameters, 768 dimensions
- 8192 token context, code-aware training
- CPU-friendly, ~600MB download (cached)

---

### Testing & Quality

**Test Coverage**
- 103 automated tests (unit, integration, performance)
- 67% overall coverage, 90%+ on critical paths
- Performance validated on small/medium codebases

**Performance** (measured on Apple Silicon):
- Small codebase (50 files): ~7s initial index, <2s incremental
- Medium codebase (200 files): ~55s initial index, ~11s incremental
- Search latency: ~180ms average
- Database size: ~80KB per file

---

## Known Limitations

### Configuration System (v0.2 Planned)

⚠️ **Important:** The `.ember/config.toml` file is created but **not yet loaded or used** by v0.1 commands.

- Changing config.toml settings has no effect
- File indexing determined by git tracking, not `include`/`ignore` patterns
- Model selection, chunking strategy, and search defaults are hardcoded
- Config file serves as documentation of intended defaults
- Full configuration loading planned for v0.2

### Commands Not Yet Implemented

The following commands are planned but not included in v0.1:
- `ember export`: Export index bundles (v0.2)
- `ember import`: Import index bundles (v0.2)
- `ember audit`: Scan for secrets/credentials (v0.2)

### Features Not Yet Implemented

- Cross-encoder reranking (flag exists, not functional)
- Secret redaction patterns (defined but not applied)
- Watch mode for auto-sync
- HTTP server for AI agents
- Custom embedding models
- Multi-project support

---

## Installation

### Requirements

- Python 3.11+ (supports 3.11, 3.12, 3.13)
- Git repository (for file tracking)
- ~2GB disk space (including model cache)

### Install from Source

```bash
git clone https://github.com/yourusername/ember.git
cd ember
git checkout v0.1.0

# Using uv (recommended)
uv sync
uv run ember --version

# Or with pip
pip install -e .
ember --version
```

---

## Quick Start

```bash
# 1. Initialize in your project
cd /path/to/your/codebase
ember init

# 2. Index your code (downloads model on first run)
ember sync

# 3. Search for code
ember find "authentication logic" -k 10

# 4. View results
ember cat 1 --context 5

# 5. Open in editor
ember open 1
```

That's it! The embedding model (~600MB) downloads automatically on first sync and is cached for future use.

---

## Migration & Compatibility

This is the first release, so no migrations are required. Future v0.2+ releases may require database migrations if schema changes.

**Breaking Changes:** None (first release)

---

## Documentation

- **README.md**: Complete usage guide and examples
- **CHANGELOG.md**: Detailed feature list and limitations
- **docs/PERFORMANCE.md**: Performance benchmarks and scaling
- **docs/AUDIT.md**: Pre-release audit findings
- **docs/decisions/**: Architecture Decision Records (ADRs)
- **CLAUDE.md**: Development continuity guide

---

## What's Next?

### Planned for v0.2

- **Configuration loading**: Honor settings in config.toml
- **Cross-encoder reranking**: Improve result quality with two-stage ranking
- **Explain command**: Show why a result matched (feature attribution)
- **Watch mode**: Auto-sync on file changes
- **Export/import**: Share indexes across machines
- **Audit command**: Scan for secrets before embedding

### Planned for v0.3+

- **HTTP server**: REST API for AI agents and tools
- **Multi-project support**: Index multiple repos simultaneously
- **Custom models**: Swap embedding models via config
- **Advanced filtering**: Tags, metadata, date ranges

See **CHANGELOG.md** for the complete roadmap.

---

## Contributing

We welcome contributions! Please see:
- **CLAUDE.md**: Development workflow and standards
- **TODO.md**: Planned features and tasks
- **docs/decisions/**: Architectural context

---

## Support & Feedback

- **Issues**: [GitHub Issues](https://github.com/yourusername/ember/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/ember/discussions)
- **Documentation**: [README.md](README.md)

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

## Credits

Built with:
- [tree-sitter](https://tree-sitter.github.io/) for code parsing
- [Jina Embeddings v2 Code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code) for embeddings
- [SQLite FTS5](https://www.sqlite.org/fts5.html) for text search
- [sentence-transformers](https://www.sbert.net/) for embedding inference

---

**Thank you for trying Ember v0.1.0!** 🔥

If you find it useful, please consider starring the repository and sharing with others.
