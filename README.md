# Ember

**Local codebase embedding and semantic search for developers and AI agents**

Ember turns any codebase into a searchable knowledge base using hybrid search (BM25 + vector embeddings). Fast, deterministic, and completely localno servers, no MCP, no cloud dependencies.

[![Tests](https://img.shields.io/badge/tests-103%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()

---

## Why Ember?

- **Fast local indexing**: Index your entire codebase in minutes, not hours
- **Hybrid search**: Combines BM25 (keyword) + vector embeddings (semantic) for best results
- **Incremental sync**: Only re-indexes changed files (9x+ speedup on typical workflows)
- **Multi-language**: Supports 9+ languages with tree-sitter-based semantic chunking
- **Developer-friendly**: `find ’ cat ’ open` workflow integrates with your editor
- **Deterministic**: Reproducible indexes via git tree SHAs and model fingerprints
- **Zero dependencies**: No servers, APIs, or cloud servicesruns entirely offline

---

## Quick Start

### Installation

```bash
# Using uv (recommended)
git clone https://github.com/yourusername/ember.git
cd ember
uv sync
uv run ember --version

# Or with pip (Python 3.11+ required)
pip install -e .
```

### Basic Usage

```bash
# Initialize Ember in your project
cd /path/to/your/codebase
ember init

# Index your codebase
ember sync

# Search for code
ember find "authentication logic" -k 10

# View full chunk with context
ember cat 1 --context 5

# Open result in your editor
ember open 1
```

That's it! Ember will download the embedding model (~600MB) on first sync and cache it for future use.

---

## Commands

### `ember init`

Initialize Ember in the current directory. Creates `.ember/` folder with:
- `config.toml` - Configuration file
- `index.db` - SQLite database (chunks, vectors, FTS5 index)
- `state.json` - Last sync metadata

**Options:**
- `--force` / `-f`: Reinitialize if `.ember/` already exists

**Example:**
```bash
ember init
# Initialized ember index at /path/to/project/.ember
#    Created config.toml
#    Created index.db
#    Created state.json
```

---

### `ember sync`

Index your codebase. Automatically uses incremental sync after the first full index.

**Options:**
- `--worktree` (default): Index working directory including unstaged changes
- `--staged`: Index only staged changes
- `--rev <ref>`: Index specific commit/branch
- `--reindex`: Force full reindex (ignores incremental detection)

**Examples:**
```bash
# Index current working directory (default)
ember sync

# Index only staged changes
ember sync --staged

# Index specific commit
ember sync --rev HEAD~3

# Force full reindex
ember sync --reindex
```

**Performance:**
- Initial sync: ~3-7 files/second (including embedding generation)
- Incremental sync: 9x+ faster (only changed files)
- No-op sync: Instant (tree SHA comparison only)

---

### `ember find <query>`

Search indexed code using hybrid search (BM25 + vector embeddings).

**Options:**
- `-k, --topk <n>`: Number of results (default: 20)
- `--in <glob>`: Filter by path pattern (e.g., `*.py`, `src/**/*.ts`)
- `--lang <code>`: Filter by language (e.g., `python`, `typescript`)
- `--json`: Output results as JSON

**Examples:**
```bash
# Semantic search
ember find "user authentication logic" -k 5

# Filter by file type
ember find "database connection" --in "*.py"

# Filter by language
ember find "error handling" --lang python

# JSON output for scripting
ember find "API endpoint" --json > results.json
```

**Output:**
```
Found 3 results:

1. src/auth/login.py:15-42 (authenticate_user)
   Score: 0.8247 (BM25: 2.39, Vector: 0.68)

   def authenticate_user(username: str, password: str) -> User | None:
       """Authenticate a user with username and password."""
       user = get_user_by_username(username)
       ...

2. src/auth/middleware.py:8-25 (require_auth)
   Score: 0.7156 (BM25: 1.82, Vector: 0.74)
   ...
```

---

### `ember cat <index>`

Display full content of a search result by index (from last `ember find`).

**Options:**
- `-C, --context <n>`: Show N lines of surrounding context from source file

**Examples:**
```bash
# Show chunk content
ember cat 1

# Show chunk with 5 lines of context before/after
ember cat 1 --context 5
```

**Note:** Requires running `ember find` first. Results are cached in `.ember/.last_search.json`.

---

### `ember open <index>`

Open search result in your editor at the correct line number.

**Examples:**
```bash
# Open first result in $EDITOR
ember open 1

# Set editor preference
export EDITOR=vim
ember open 2
```

**Supported editors:**
- vim, nvim, vi, nano, emacs (+line syntax)
- VS Code (`code --goto file:line`)
- Sublime Text, Atom (file:line syntax)

**Note:** Uses `$VISUAL` > `$EDITOR` > `vim` (fallback).

---

### `ember export [--rev <ref>]`

Export index to a portable bundle (not yet fully implemented).

### `ember import <bundle>`

Import index from a bundle (not yet fully implemented).

### `ember audit`

Scan indexed chunks for potential secrets/credentials (not yet fully implemented).

---

## Configuration

Edit `.ember/config.toml` to customize indexing behavior:

```toml
[index]
model = "jinaai/jina-embeddings-v2-base-code"  # Embedding model
chunk = "symbol"  # Chunking strategy: "symbol" or "lines"
line_window = 120  # Lines per chunk (for line-based chunking)
line_stride = 100  # Stride between chunks
overlap_lines = 15  # Overlap for context preservation
include = ["**/*.py", "**/*.ts", "**/*.go"]  # File patterns to index
ignore = [".git/", "node_modules/", "dist/", "build/"]  # Patterns to skip

[search]
topk = 20  # Default number of results
rerank = false  # Enable reranking (not yet implemented)
filters = []  # Default filters

[redaction]
patterns = []  # Regex patterns for secret redaction (not yet implemented)
max_file_mb = 5  # Skip files larger than this
```

**Respects:**
- `.gitignore` (automatically applied)
- `.emberignore` (optional, same format as .gitignore)

---

## Supported Languages

Ember uses **tree-sitter** for semantic chunking (extracts functions, classes, methods):

| Language | Extensions | Chunking |
|----------|-----------|----------|
| Python | `.py` | Functions, classes, methods |
| TypeScript | `.ts`, `.tsx` | Functions, classes, interfaces |
| JavaScript | `.js`, `.jsx` | Functions, classes |
| Go | `.go` | Functions, structs |
| Rust | `.rs` | Functions, structs, impls |
| Java | `.java` | Classes, interfaces, methods |
| C | `.c`, `.h` | Functions, structs |
| C++ | `.cpp`, `.hpp`, `.cc`, `.cxx` | Functions, classes, structs |
| C# | `.cs` | Classes, interfaces, methods |
| Ruby | `.rb` | Classes, modules, methods |

**Fallback:** For unsupported languages, Ember uses line-based chunking (120 lines, 100-line stride, 20-line overlap).

---

## Architecture

Ember follows **Clean Architecture** with strict layer separation:

```
ember/
  app/              # CLI commands, DTOs (no business logic)
  core/             # Use cases (pure Python, no infra dependencies)
    indexing/       # Sync/indexing orchestration
    retrieval/      # Search orchestration
    chunking/       # Chunking coordination
    config/         # Init/config management
  domain/           # Entities (Chunk, RepoState, Query)
  ports/            # Abstract interfaces (Protocol-based)
    repositories.py # Database interfaces
    embedders.py    # Embedding model interface
    search.py       # Search interfaces (FTS, vector)
    vcs.py          # Git interface
  adapters/         # Infrastructure implementations
    sqlite/         # SQLite repositories
    fts/            # FTS5 full-text search
    vss/            # Vector search (brute-force)
    git_cmd/        # Git subprocess adapter
    local_models/   # Jina Code embedder
    parsers/        # Tree-sitter + line chunkers
  shared/           # Utilities (config I/O, logging)
  entrypoints/      # CLI entry point
```

**Design Principles:**
- `core/` depends only on `ports/`, never on `adapters/`
- Adapters implement port protocols
- Dependency injection throughout
- SOLID principles (see `docs/decisions/`)

**Storage:**
- SQLite database in `.ember/index.db`
- FTS5 virtual table for BM25 text search
- BLOB-based vector storage (simple, fast for <100k chunks)
- State tracking in `.ember/state.json`

**Embedding Model:**
- [Jina Embeddings v2 Code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code)
- 161M parameters, 768 dimensions
- 8192 token context, 30+ languages
- CPU-friendly, ~600MB download (cached)

---

## Performance

See [docs/PERFORMANCE.md](docs/PERFORMANCE.md) for detailed benchmarks.

**Summary:**

| Metric | Small (50 files) | Medium (200 files) | Large (2000 files*) |
|--------|------------------|--------------------|--------------------|
| Initial index | 7s | 55s | ~9 min* |
| Incremental sync | <2s | ~11s | ~2 min* |
| Search (avg) | 180ms | 180ms | 200ms* |
| Database size | 4MB | 16MB | 160MB* |

*Projected based on linear scaling

**Incremental sync speedup:** 9x+ faster than full reindex

---

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/yourusername/ember.git
cd ember

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run type checker
uv run pyright
```

### Project Structure

- **`CLAUDE.md`**: Development continuity guide (start here for contributors)
- **`prd.md`**: Product requirements document
- **`TODO.md`**: Task backlog
- **`docs/`**: Documentation and decisions
  - **`progress.md`**: Chronological implementation log
  - **`decisions/`**: Architecture Decision Records (ADRs)
  - **`PERFORMANCE.md`**: Performance testing results
- **`tests/`**: Unit, integration, and performance tests

### Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# Integration tests
uv run pytest tests/integration/

# Performance tests (slow)
uv run pytest tests/performance/

# Skip slow tests
uv run pytest -m "not slow"

# With coverage
uv run pytest --cov=ember --cov-report=term-missing
```

### Quality Standards

- **Architecture:** Clean Architecture layers strictly enforced
- **Type hints:** All public functions fully typed
- **Testing:** 103 tests (unit, integration, performance)
- **Linting:** ruff (compliant)
- **Type checking:** pyright (strict mode)
- **Coverage:** 60%+ overall, 90%+ for critical paths

---

## Contributing

We welcome contributions! Please:

1. Read **CLAUDE.md** for development workflow and standards
2. Check **TODO.md** for planned features
3. Review **docs/decisions/** for architectural context
4. Follow existing code patterns (Clean Architecture, SOLID)
5. Add tests for new functionality
6. Update documentation (README, ADRs, progress.md)

---

## FAQ

**Q: How is this different from GitHub Copilot?**
A: Ember is a local search tool, not a code completion AI. It indexes *your* codebase for retrieval, while Copilot generates code based on broad training data.

**Q: Can I use this with large monorepos?**
A: Yes, but performance depends on size. Ember handles codebases with 1000-2000 files well. For larger repos, use `include`/`ignore` patterns to filter files.

**Q: Does Ember send my code to the cloud?**
A: No. Everything runs locally. The embedding model downloads once from HuggingFace and is cached.

**Q: Can I use a different embedding model?**
A: Not yet, but this is planned. The architecture supports swapping models via the `Embedder` protocol.

**Q: What about binary files / images / PDFs?**
A: Ember currently only indexes text-based source code. Binary files are skipped.

**Q: How do I exclude sensitive files?**
A: Add patterns to `ignore` in `.ember/config.toml` or use `.emberignore`.

---

## Roadmap

**v0.1 (MVP)** - Current
-  Core commands: init, sync, find, cat, open
-  Hybrid search (BM25 + vector)
-  Incremental indexing
-  9+ language support
- ó Export/import bundles
- ó Audit command for secrets

**v0.2** - Planned
- Cross-encoder reranking
- Explain command (why a result matched)
- Watch mode (auto-sync on file changes)

**v0.3** - Future
- HTTP server for AI agents
- Multi-project support
- Custom embedding models
- Advanced filtering (tags, metadata)

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

## Credits

Built with:
- [tree-sitter](https://tree-sitter.github.io/) for code parsing
- [Jina Embeddings v2 Code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code) for embeddings
- [SQLite FTS5](https://www.sqlite.org/fts5.html) for text search
- [click](https://click.palletsprojects.com/) for CLI
- [sentence-transformers](https://www.sbert.net/) for embedding inference

Developed by [Sam @ KamiwazaAI](https://github.com/yourusername)
