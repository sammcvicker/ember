# Ember

**Local codebase embedding and semantic search for developers and AI agents**

Ember turns any codebase into a searchable knowledge base using hybrid search (BM25 + vector embeddings). Fast, deterministic, and completely localno servers, no MCP, no cloud dependencies.

[![Tests](https://img.shields.io/badge/tests-801%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()

---

## Why Ember?

- **Blazingly fast**: Daemon-based model server makes searches near-instant (18.6x faster than cold start)
- **Fast local indexing**: Index your entire codebase in minutes, not hours
- **Hybrid search**: Combines BM25 (keyword) + vector embeddings (semantic) for best results
- **Incremental sync**: Only re-indexes changed files (9x+ speedup on typical workflows)
- **Multi-language**: Supports 9+ languages with tree-sitter-based semantic chunking
- **Developer-friendly**: `find -> cat -> open` workflow integrates with your editor
- **Deterministic**: Reproducible indexes via git tree SHAs and model fingerprints
- **Zero dependencies**: No servers, APIs, or cloud servicesruns entirely offline

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

**Automatically finds git root** - If you're in a git repository, `ember init` will initialize at the repository root, not your current directory.

**Options:**
- `--force` / `-f`: Reinitialize if `.ember/` already exists

**Example:**
```bash
# Run from anywhere in your repository
cd src/nested/directory
ember init
# Initialized ember index at /path/to/project/.ember (at git root)
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

### `ember find <query> [path]`

Search indexed code using hybrid search (BM25 + vector embeddings).

**Works from any subdirectory** - Like git, you can run ember commands from anywhere within your repository.

**Options:**
- `[path]`: Optional path to search within (relative to current directory)
- `-k, --topk <n>`: Number of results (default: 20)
- `-C, --context <n>`: Show N lines of context around each result (default: 0)
- `--in <glob>`: Filter by path pattern (e.g., `*.py`, `src/**/*.ts`)
- `--lang <code>`: Filter by language (e.g., `python`, `typescript`)
- `--json`: Output results as JSON

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

# Show surrounding context (like ripgrep -C)
ember find "authentication" -C 5

# JSON output for scripting
ember find "API endpoint" --json > results.json

# Context in JSON output (great for agents)
ember find "auth" -C 3 --json
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

### `ember cat <identifier>`

Display full content of a search result by index or chunk ID.

**Options:**
- `-C, --context <n>`: Show N lines of surrounding context from source file

**Examples:**
```bash
# Using numeric index (requires prior search)
ember cat 1
ember cat 1 --context 5

# Using chunk hash ID (stateless, no prior search needed)
ember find "auth" --json | jq -r '.[0].id' | xargs ember cat

# Using short hash prefix (like git)
ember cat a1b2c3d4
```

**Identifier formats:**
- **Numeric index** (e.g., `1`, `2`): References results from last `ember find` command
- **Full chunk ID** (64 hex characters): Stateless lookup by complete hash
- **Short hash prefix** (8+ characters): Like git SHAs, must be unambiguous

**Note:** Numeric indexes require running `ember find` first. Hash IDs work without prior search.

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

Display index status and configuration at a glance.

**Example:**
```bash
ember status
```

**Output:**
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
  Mode: daemon (auto-starts on first search)
```

**Features:**
- Works from any subdirectory (like all ember commands)
- Shows whether index needs syncing
- Displays current configuration from `.ember/config.toml`

---

### `ember config`

Manage Ember configuration with support for local and global settings.

**Commands:**
```bash
# Show effective config and file locations
ember config show

# Edit local config (.ember/config.toml)
ember config edit

# Edit global config (~/.config/ember/config.toml)
ember config edit --global

# Print config file paths for scripting
ember config path
ember config path --global
ember config path --local
```

**Config hierarchy:**
- Global config: `~/.config/ember/config.toml` (or `$XDG_CONFIG_HOME/ember/config.toml`)
- Local config: `.ember/config.toml` in your repository
- Local settings override global settings on a section-by-section basis

---

### `ember daemon`

Manage the embedding model daemon for instant searches.

The daemon keeps the embedding model loaded in memory, making searches **18.6x faster** (43ms avg vs 806ms cold start). It auto-starts transparently when needed and shuts down after 15 minutes of inactivity.

**Commands:**
```bash
# Check daemon status
ember daemon status

# Manually start daemon
ember daemon start

# Stop daemon
ember daemon stop

# Restart daemon
ember daemon restart
```

**Configuration** (`.ember/config.toml`):
```toml
[model]
mode = "daemon"        # or "direct" to disable daemon
daemon_timeout = 900   # auto-shutdown after 15 min (default)
```

**Why use the daemon?**
- **First search after daemon starts:** ~1s (one-time model loading cost)
- **Subsequent searches:** ~20ms (model already loaded)
- **Direct mode (no daemon):** 800ms+ per search

**Note:** Daemon auto-starts on first `ember find` or `ember sync` command. Manual management is optional.

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

[model]
model = "jina-code-v2"  # or "bge-small", "minilm", "auto"
mode = "daemon"  # or "direct"
daemon_timeout = 900  # 15 minutes

[redaction]
patterns = []  # Regex patterns for secret redaction
max_file_mb = 5  # Skip files larger than this
```

**Functional Settings (v1.2.0):**

The following configuration settings are now active and respected by Ember:

- **`search.topk`**: Default number of results for `ember find` (can be overridden with `-k` flag)
- **`index.line_window`**: Lines per chunk for line-based chunking
- **`index.line_stride`**: Stride between chunks (overlap = window - stride)
- **`model.model`**: Embedding model (`jina-code-v2`, `bge-small`, `minilm`, or `auto`)
- **`model.mode`**: Daemon mode (`daemon` or `direct`)—daemon provides 18.6x faster searches
- **`model.daemon_timeout`**: Auto-shutdown timeout in seconds (default: 900 = 15 min)

**Model Selection:**
- **`jina-code-v2`** (default): Best quality for code search, requires ~4GB RAM
- **`bge-small`**: Good balance of quality and resources, requires ~1GB RAM
- **`minilm`**: Lightweight option for low-memory systems, requires ~512MB RAM
- **`auto`**: Automatically selects based on available system RAM

**Not Yet Implemented:**
- `index.include` / `index.ignore` patterns (planned for future release)
- `index.chunk` strategy selection (currently always uses "symbol" with line fallback)
- `search.rerank` (planned for future release)
- `redaction.patterns` (planned for future release)

**File Indexing (v1.0.0):**
- **Code files only**: Only source code files are indexed (see supported extensions below)
- **All working directory files**: Indexes tracked, untracked, and unstaged files
- **`.gitignore` respected**: Patterns in `.gitignore` are automatically honored (won't index `node_modules/`, `.venv/`, etc.)
- **Search what you see**: Creating a new file? It's immediately searchable after auto-sync
- **`.emberignore`**: Optional, same format as `.gitignore` for additional exclusions

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
  adapters/         # Infrastructure implementations
    sqlite/         # SQLite repositories
    fts/            # FTS5 full-text search
    vss/            # sqlite-vec vector search
    git_cmd/        # Git subprocess adapter
    local_models/   # Jina Code embedder (daemon + direct modes)
    parsers/        # Tree-sitter + line chunkers
    daemon/         # Daemon lifecycle management
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
- sqlite-vec for fast vector similarity search (optimized k-NN with cosine distance)
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
| Search (daemon mode) | 43ms | 43ms | ~50ms* |
| Search (direct mode) | 806ms | 806ms | ~850ms* |
| Database size | 4MB | 16MB | 160MB* |

*Projected based on linear scaling

**Key speedups:**
- **Daemon mode:** 18.6x faster than direct mode (43ms vs 806ms average)
- **Incremental sync:** 9x+ faster than full reindex
- **First search after daemon starts:** ~1s (one-time model loading)
- **Subsequent searches:** ~20ms (model already in memory)

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
- **Testing:** 801 tests (unit, integration, performance, CLI)
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
A: Yes! As of v1.2.0, Ember supports three models:
- **jina-code-v2** (default): Best quality, ~1.6GB RAM, 768 dimensions
- **bge-small**: Good balance, ~130MB RAM, 384 dimensions
- **minilm**: Lightweight, ~100MB RAM, 384 dimensions, 5x faster

Set in config: `model = "minilm"` or use `ember init --model minilm`. Run `ember init` to auto-detect the best model for your hardware.

**Q: What about binary files / images / PDFs?**
A: Ember only indexes source code files with recognized code extensions (see Configuration section). Binary files, documentation, and data files are automatically skipped during indexing.

**Q: How do I exclude sensitive files?**
A: Use `.gitignore` or `.emberignore` to exclude files. Config-based `ignore` patterns in `.ember/config.toml` are planned for a future release.

**Q: Which config settings actually work?**
A: As of v1.0.0, `search.topk`, `index.line_window`, `index.line_stride`, `model.mode`, and `model.daemon_timeout` are functional. Other settings like `include`/`ignore` patterns and model selection are coming in future releases. See the Configuration section for details.

**Q: What's this daemon process and why is it running?**
A: The daemon keeps the embedding model loaded in memory, making searches 18.6x faster (43ms vs 806ms). It auto-starts when needed and shuts down after 15 minutes of inactivity. You can disable it by setting `model.mode = "direct"` in `.ember/config.toml` or manage it manually with `ember daemon stop`.

---

## Roadmap

**v1.0.0 "Be Like Water"** - Released (2025-10-29)
- [x] Core commands: init, sync, find, cat, open, status, daemon
- [x] Hybrid search (BM25 + vector with sqlite-vec)
- [x] Incremental indexing (9x+ speedup)
- [x] Daemon-based model server (18.6x faster searches)
- [x] Subdirectory support (works like git)
- [x] Index all working directory files (untracked, unstaged, tracked)
- [x] Hash-based chunk IDs for stateless retrieval
- [x] 9+ language support with tree-sitter
- [x] 271 comprehensive tests
- [x] Clean architecture with strict layer separation

**v1.1.0** (2025-11-06) ✅
- Context flag for `ember find` (-C/--context)
- Stable hash-based chunk IDs for parallel agent workflows

**v1.2.0** (2025-12-12) ✅
- Interactive search TUI with path filtering (`ember search [path]`)
- Syntax highlighting for cat, find, and search preview
- Global config with `ember config` command group
- Multiple embedding models: Jina (default), MiniLM (lightweight), BGE-small (balanced)
- Auto-detect hardware and recommend model during init
- Go/Rust struct, enum, trait extraction via TreeSitter
- TypeScript interface, type alias, and arrow function extraction
- Daemon reliability fixes (#214, #215, #216)
- 801 comprehensive tests (up from 271)

**Future** (see [GitHub Issues](https://github.com/sammcvicker/ember))
- Export/import bundles
- Audit command for secrets
- Include/ignore patterns from config
- Cross-encoder reranking
- Watch mode (auto-sync on file changes)
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
- [sqlite-vec](https://github.com/asg017/sqlite-vec) for fast vector similarity search
- [click](https://click.palletsprojects.com/) for CLI
- [sentence-transformers](https://www.sbert.net/) for embedding inference

Developed by [Sam @ KamiwazaAI](https://github.com/yourusername)
