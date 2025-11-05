# Ember

**Local codebase embedding and semantic search for developers and AI agents**

Ember turns any codebase into a searchable knowledge base using hybrid search (BM25 + vector embeddings). Fast, deterministic, and completely local—no servers, no MCP, no cloud dependencies.

[![Tests](https://img.shields.io/badge/tests-257%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()
[![Version](https://img.shields.io/badge/version-1.0.0-blue)]()

---

## Why Ember?

- **Instant search**: Daemon keeps model loaded in memory for 18.6x faster searches (~40ms)
- **Fast local indexing**: Index your entire codebase in minutes with optimized batching
- **Hybrid search**: Combines BM25 (keyword) + vector embeddings (semantic) for best results
- **Incremental sync**: Only re-indexes changed files (9x+ speedup on typical workflows)
- **Multi-language**: Supports 9+ languages with tree-sitter-based semantic chunking
- **Developer-friendly**: `find -> cat -> open` workflow integrates with your editor
- **Works like git**: Run from any subdirectory, search what you see (including untracked files)
- **Deterministic**: Reproducible indexes via git tree SHAs and model fingerprints
- **Zero dependencies**: No servers, APIs, or cloud services—runs entirely offline

---

## Quick Start

### Installation

```bash
# Using uv (recommended)
git clone https://github.com/sammcvicker/ember.git
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

# Index your codebase (daemon starts automatically)
ember sync

# Search for code (instant after first search)
ember find "authentication logic" -k 10

# Check daemon and index status
ember status

# View full chunk with context
ember cat 1 --context 5

# Open result in your editor
ember open 1
```

**First-time setup:** Ember will download the embedding model (~600MB) on first sync and cache it for future use. The daemon will start automatically and keep the model loaded in memory for near-instant searches.

---

## Commands

### `ember init`

Initialize Ember in the current directory. Creates `.ember/` folder with:
- `config.toml` - Configuration file
- `index.db` - SQLite database (chunks, vectors, FTS5 index)
- `state.json` - Last sync metadata

**Automatically finds git root** - If you're in a git repository, `ember init` will initialize at the repository root, not your current directory.

**Options:**
- `--force` / `-f`: Reinitialize if `.ember/` already exists

**Example:**
```bash
# Run from anywhere in your repository
cd src/nested/directory
ember init
# Initialized ember index at /path/to/project/.ember (at git root)
#    Created config.toml
#    Created index.db
#    Created state.json
```

---

### `ember sync`

Index your codebase. Automatically uses incremental sync after the first full index.

**Options:**
- `--worktree` (default): Index working directory including unstaged and untracked files
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
- Daemon startup: ~3-5s first time, then stays loaded for 15+ minutes

---

### `ember find <query> [path]`

Search indexed code using hybrid search (BM25 + vector embeddings).

**Works from any subdirectory** - Like git, you can run ember commands from anywhere within your repository. Ember automatically syncs the index before searching if changes are detected.

**Options:**
- `[path]`: Optional path to search within (relative to current directory)
- `-k, --topk <n>`: Number of results (default: 20)
- `--in <glob>`: Filter by path pattern (e.g., `*.py`, `src/**/*.ts`)
- `--lang <code>`: Filter by language (e.g., `python`, `typescript`)
- `--json`: Output results as JSON
- `--no-sync`: Skip auto-sync (for maximum speed when you know index is current)

**Examples:**
```bash
# Semantic search (entire repo)
ember find "user authentication logic" -k 5

# Search only in current directory subtree
cd src/auth
ember find "authentication" .

# Search specific path (from anywhere)
ember find "database connection" src/db/

# Filter by file type
ember find "error handling" --in "*.py"

# Filter by language
ember find "async functions" --lang typescript

# JSON output for scripting
ember find "API endpoint" --json > results.json

# Skip auto-sync for speed
ember find "query" --no-sync
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

### `ember status`

Display the current state of the ember index and configuration.

**Examples:**
```bash
# Check index status
ember status

# Example output:
# ✓ Ember initialized at /Users/sam/project
#
# Index Status:
#   Indexed files: 247
#   Total chunks: 1,834
#   Status: ✓ Up to date
#
# Configuration:
#   Search results (topk): 20
#   Chunk size: 120 lines
#   Model: jina-embeddings-v2-base-code
```

**Works from any subdirectory** - Like all ember commands.

---

### `ember daemon start|stop|status|restart`

Manage the embedding daemon (keeps model loaded in memory).

**Commands:**
- `ember daemon start`: Manually start the daemon
- `ember daemon stop`: Stop the daemon
- `ember daemon status`: Check daemon status
- `ember daemon restart`: Restart the daemon

**Examples:**
```bash
# Check if daemon is running
ember daemon status

# Stop daemon to free memory
ember daemon stop

# Restart daemon (useful after config changes)
ember daemon restart
```

**Note:** The daemon starts automatically when needed (during `ember sync` or `ember find`) and shuts down after 15 minutes of inactivity (configurable in `.ember/config.toml`).

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
[model]
mode = "daemon"          # "daemon" (fast) or "direct" (no background process)
daemon_timeout = 900     # Seconds before daemon auto-shutdown (default: 15 min)

[index]
model = "local-default-code-embed"  # Embedding model
chunk = "symbol"         # Chunking strategy: "symbol" or "lines"
line_window = 120        # Lines per chunk (for line-based chunking)
line_stride = 100        # Stride between chunks
overlap_lines = 15       # Overlap for context preservation
include = ["**/*.py", "**/*.ts", "**/*.go"]  # File patterns to index
ignore = [".git/", "node_modules/", "dist/", "build/"]  # Patterns to skip

[search]
topk = 20                # Default number of results
rerank = false           # Enable reranking (not yet implemented)
filters = []             # Default filters

[redaction]
patterns = []            # Regex patterns for secret redaction
max_file_mb = 5          # Skip files larger than this
```

**Functional Settings (v1.0.0):**

The following configuration settings are active and respected by Ember:

- **`model.mode`**: Daemon mode (`"daemon"`) or direct mode (`"direct"`)
- **`model.daemon_timeout`**: Seconds before auto-shutdown (default: 900)
- **`search.topk`**: Default number of results for `ember find` (can be overridden with `-k` flag)
- **`index.line_window`**: Lines per chunk for line-based chunking
- **`index.line_stride`**: Stride between chunks (overlap = window - stride)

**Not Yet Implemented:**
- `index.include` / `index.ignore` patterns (use `.gitignore` or `.emberignore` instead)
- `index.chunk` strategy selection (currently always uses "symbol" with line fallback)
- `index.model` selection (currently hardcoded to Jina v2 Code)
- `search.rerank` (cross-encoder reranking)
- `redaction.patterns` (secret redaction)

**File Indexing (v1.0.0):**
- **Code files only**: Only source code files are indexed (see supported extensions below)
- **All working directory files**: Indexes tracked, staged, unstaged, and untracked files
- **Respects .gitignore**: Files matching `.gitignore` patterns are automatically skipped
- **Optional .emberignore**: Additional patterns in same format as `.gitignore`

**Indexed file extensions:**
`.py`, `.pyi`, `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.go`, `.rs`, `.java`, `.kt`, `.scala`, `.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hh`, `.hxx`, `.cs`, `.rb`, `.php`, `.swift`, `.sh`, `.bash`, `.zsh`, `.vue`, `.svelte`, `.sql`, `.proto`, `.graphql`

**Skipped files (not indexed):**
- Documentation: `.md`, `.txt`, `.rst`, `.adoc`
- Data/Config: `.json`, `.yaml`, `.yml`, `.toml`, `.xml`, `.csv`
- Binary files: `.png`, `.jpg`, `.jpeg`, `.gif`, `.pdf`, `.zip`, etc.
- Build artifacts: `.pyc`, `.class`, `.o`, `.so`, `.dll`, `.exe`
- Lock files: `.lock`, `.sum`
- Other non-code files

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
    daemon.py       # Daemon lifecycle interface
  adapters/         # Infrastructure implementations
    sqlite/         # SQLite repositories
    fts/            # FTS5 full-text search
    vss/            # sqlite-vec for fast vector search
    git_cmd/        # Git subprocess adapter
    local_models/   # Jina Code embedder + daemon
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
- [sqlite-vec](https://github.com/asg017/sqlite-vec) extension for fast vector similarity search
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
| Search (daemon) | 43ms | 43ms | ~50ms* |
| Search (direct) | 806ms | 806ms | ~850ms* |
| Database size | 4MB | 16MB | 160MB* |

*Projected based on linear scaling

**Daemon speedup:** 18.6x faster than direct mode (43ms vs 806ms average)
**Incremental sync speedup:** 9x+ faster than full reindex

---

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/sammcvicker/ember.git
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
- **`MAINTAINER_GUIDE.md`**: Detailed operational procedures for releases, PRs, etc.
- **`prd.md`**: Product requirements document
- **`docs/`**: Documentation and decisions
  - **`ARCHITECTURE.md`**: Technical architecture guide
  - **`PERFORMANCE.md`**: Performance testing results
  - **`decisions/`**: Architecture Decision Records (ADRs)
- **`tests/`**: Unit, integration, and performance tests

### Running Tests

```bash
# Fast tests only (default - skips slow tests, runs in ~1-2s)
uv run pytest

# Run slow tests (includes performance and integration tests with embeddings)
uv run pytest -m slow

# All tests (fast + slow, takes several minutes)
uv run pytest -m ""

# Unit tests only
uv run pytest tests/unit/

# Integration tests
uv run pytest tests/integration/

# With coverage
uv run pytest --cov=ember --cov-report=term-missing
```

### Quality Standards

- **Architecture:** Clean Architecture layers strictly enforced
- **Type hints:** All public functions fully typed
- **Testing:** 257 tests (210 fast, 47 slow) - unit, integration, and performance
- **Linting:** ruff (compliant)
- **Type checking:** pyright (strict mode)
- **Coverage:** 26%+ overall (focus on critical paths)

---

## Contributing

We welcome contributions! Please:

1. Read **CLAUDE.md** for development workflow and current state
2. Check [GitHub Issues](https://github.com/sammcvicker/ember/issues) for planned features
3. Review **MAINTAINER_GUIDE.md** for release procedures
4. Review **docs/decisions/** for architectural context
5. Follow existing code patterns (Clean Architecture, SOLID)
6. Add tests for new functionality
7. Update documentation (README, CHANGELOG, ADRs)

---

## FAQ

**Q: How is this different from GitHub Copilot?**
A: Ember is a local search tool, not a code completion AI. It indexes *your* codebase for retrieval, while Copilot generates code based on broad training data.

**Q: Can I use this with large monorepos?**
A: Yes, but performance depends on size. Ember handles codebases with 1000-2000 files well. Larger repos work but may have slower initial indexing.

**Q: Does Ember send my code to the cloud?**
A: No. Everything runs locally. The embedding model downloads once from HuggingFace and is cached.

**Q: Can I use a different embedding model?**
A: Not yet, but this is planned. The architecture supports swapping models via the `Embedder` protocol.

**Q: What about binary files / images / PDFs?**
A: Ember only indexes source code files with recognized code extensions (see Configuration section). Binary files, documentation, and data files are automatically skipped during indexing.

**Q: How do I exclude sensitive files?**
A: Use `.gitignore` or `.emberignore` to exclude files. Config-based `ignore` patterns in `.ember/config.toml` are planned for a future release.

**Q: Which config settings actually work?**
A: As of v1.0.0, `model.mode`, `model.daemon_timeout`, `search.topk`, `index.line_window`, and `index.line_stride` are functional. Other settings like `include`/`ignore` patterns and model selection are coming in future releases. See the Configuration section for details.

**Q: What is the daemon and why is it running?**
A: The daemon is a background process that keeps the embedding model loaded in memory. This makes searches 18.6x faster (~40ms instead of ~800ms). It starts automatically when needed and shuts down after 15 minutes of inactivity. You can disable it by setting `mode = "direct"` in `.ember/config.toml`.

---

## Roadmap

**v1.0.0 (Current)** - Released 2025-10-29 ✅
- [x] Core commands: init, sync, find, cat, open, status
- [x] Daemon-based model server (18.6x faster searches)
- [x] Subdirectory support (works like git)
- [x] Index untracked/unstaged files
- [x] Hybrid search (BM25 + vector with sqlite-vec)
- [x] Incremental indexing
- [x] 9+ language support
- [x] Auto-sync on search
- [ ] Export/import bundles
- [ ] Audit command for secrets

**Future** - See [GitHub Issues](https://github.com/sammcvicker/ember/issues)
- Include/ignore patterns from config
- Context flag on find command (`-C` for immediate context)
- Stable hash IDs for parallel agent workflows
- Cross-encoder reranking
- Custom embedding models
- HTTP server for AI agents
- Multi-project support

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

## Credits

Built with:
- [tree-sitter](https://tree-sitter.github.io/) for code parsing
- [Jina Embeddings v2 Code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code) for embeddings
- [SQLite FTS5](https://www.sqlite.org/fts5.html) for text search
- [sqlite-vec](https://github.com/asg017/sqlite-vec) for vector similarity search
- [click](https://click.palletsprojects.com/) for CLI
- [sentence-transformers](https://www.sbert.net/) for embedding inference

Developed by [Sam @ KamiwazaAI](https://github.com/sammcvicker)
