# Ember Architecture

**Version:** v0.1.0+
**Last Updated:** 2025-10-19

---

## Overview

Ember follows **Clean Architecture** principles with a strict **ports and adapters** pattern. This ensures testability, maintainability, and the ability to swap implementations without touching business logic.

---

## Architectural Layers

### Directory Structure

```
ember/
  core/        # Use cases & services (pure Python, no infrastructure imports)
    indexing/  # Indexing use case
    retrieval/ # Search use case
    git/       # Git integration logic
    chunking/  # Chunking orchestration
    config/    # Configuration management
    export/    # Export/import/audit (future)

  domain/      # Entities & value objects
    entities.py   # Chunk, RepoState, Query, etc.
    config.py     # Configuration models

  ports/       # Abstract interfaces (Protocol-based)
    repositories.py  # ChunkRepository, MetaRepository, FileRepository
    embedders.py     # Embedder protocol
    search.py        # TextSearch, VectorSearch, Reranker
    vcs.py           # VCS (git) interface
    fs.py            # FileSystem interface
    chunkers.py      # Chunker protocol
    progress.py      # Progress reporting

  adapters/    # Infrastructure implementations
    sqlite/          # SQLite repositories
      chunk_repository.py
      vector_repository.py
      meta_repository.py
      file_repository.py
      schema.py
    fts/             # Full-text search
      sqlite_fts.py  # FTS5 implementation
    vss/             # Vector similarity search
      simple_vector_search.py
    git_cmd/         # Git command wrapper
      git_adapter.py
    local_models/    # Embedding models
      jina_embedder.py
    parsers/         # Code parsing
      tree_sitter_chunker.py
      line_chunker.py
    fs/              # File system operations
      local.py

  app/         # CLI commands & DTOs (thin layer, no business logic)

  entrypoints/ # CLI entry point
    cli.py     # Click commands

  shared/      # Cross-cutting concerns
    errors.py
    config_io.py
    state_io.py
```

---

## Layer Responsibilities

### 1. Domain Layer

**Purpose:** Core business entities and value objects

**Rules:**
- No dependencies on other layers
- Pure Python classes
- Immutable where possible
- Rich domain models with behavior

**Example:**
```python
@dataclass(frozen=True)
class Chunk:
    """A semantic unit of code with metadata."""
    file_path: Path
    start_line: int
    end_line: int
    content: str
    language: str

    @property
    def content_hash(self) -> str:
        """Compute deterministic hash of content."""
        return blake3(self.content.encode()).hexdigest()
```

---

### 2. Ports Layer

**Purpose:** Define interfaces between core and infrastructure

**Rules:**
- Use `Protocol` (not ABC) for runtime duck typing
- No implementation details
- Define contracts clearly
- Document expected behavior

**Example:**
```python
class Embedder(Protocol):
    """Interface for embedding text into vectors."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors."""
        ...

    def fingerprint(self) -> str:
        """Return model fingerprint for versioning."""
        ...
```

---

### 3. Core Layer (Use Cases)

**Purpose:** Business logic orchestration

**Rules:**
- Depends ONLY on `domain/` and `ports/`
- **NEVER** import from `adapters/`
- Pure Python - no database, no HTTP, no filesystem
- Dependencies injected via `__init__`
- Testable with mocks

**Example:**
```python
class IndexingUseCase:
    def __init__(
        self,
        vcs: VCS,
        chunker: ChunkUseCase,
        embedder: Embedder,
        chunk_repo: ChunkRepository,
        vector_repo: VectorRepository,
        # ... dependencies injected
    ):
        self.vcs = vcs
        self.chunker = chunker
        # ...

    def execute(self, request: IndexRequest) -> IndexResponse:
        # Business logic here
        files = self.vcs.diff_files(old_sha, new_sha)
        chunks = self.chunker.chunk_file(file)
        embeddings = self.embedder.embed_texts([c.content for c in chunks])
        # ...
```

**Violation Example (DO NOT DO THIS):**
```python
# ❌ BAD - importing adapter in core
from ember.adapters.sqlite.chunk_repository import SqliteChunkRepository

# ✅ GOOD - depend on port
from ember.ports.repositories import ChunkRepository
```

---

### 4. Adapters Layer

**Purpose:** Concrete implementations of ports

**Rules:**
- Implement port protocols
- Can import from infrastructure (SQLite, PyTorch, etc.)
- Handle errors and edge cases
- Return domain objects, not infrastructure objects

**Example:**
```python
class SqliteChunkRepository(ChunkRepository):
    """SQLite implementation of ChunkRepository protocol."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def add(self, chunk: Chunk) -> None:
        # SQLite-specific implementation
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO chunks (...) VALUES (...)",
                (chunk.id, chunk.content, ...)
            )
```

---

### 5. App Layer

**Purpose:** Translate CLI/API requests into use case calls

**Rules:**
- Thin layer - no business logic
- Wire up dependencies
- Convert CLI args to use case requests
- Format use case responses for display

---

## Dependency Injection

### Construction Site Pattern

All dependencies are wired together at the entry point (CLI commands).

**Example from `cli.py`:**
```python
@click.command()
def sync():
    # Wire up dependencies
    db_path = repo_root / ".ember" / "index.db"

    # Adapters
    vcs = GitAdapter(repo_root)
    embedder = JinaCodeEmbedder()
    chunk_repo = SqliteChunkRepository(db_path)
    vector_repo = SqliteVectorRepository(db_path)
    # ...

    # Use case
    indexing = IndexingUseCase(
        vcs=vcs,
        embedder=embedder,
        chunk_repo=chunk_repo,
        vector_repo=vector_repo,
        # ...
    )

    # Execute
    response = indexing.execute(request)
```

**Benefits:**
- Easy to test (inject mocks)
- Easy to swap implementations
- Dependencies explicit
- No hidden global state

---

## Data Flow

### Indexing Flow

```
CLI Command (sync)
  ↓
[Inject dependencies]
  ↓
IndexingUseCase.execute()
  ↓
├─→ VCS.diff_files() → list[Path]
├─→ ChunkUseCase.chunk_file() → list[Chunk]
├─→ Embedder.embed_texts() → list[Vector]
└─→ ChunkRepository.add() + VectorRepository.add()
  ↓
Response
```

### Search Flow

```
CLI Command (find)
  ↓
[Inject dependencies]
  ↓
SearchUseCase.execute()
  ↓
├─→ TextSearch.search() → list[ChunkScore]
├─→ VectorSearch.search() → list[ChunkScore]
├─→ RRF Fusion → Ranked Results
└─→ ChunkRepository.get_many() → list[Chunk]
  ↓
Response
```

---

## Key Design Patterns

### 1. Protocol-Based Interfaces

**Why:** Runtime duck typing, easier testing, no inheritance hierarchy

```python
class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
```

### 2. Dependency Injection

**Why:** Testability, flexibility, explicitness

```python
def __init__(self, repo: ChunkRepository, embedder: Embedder):
    self.repo = repo
    self.embedder = embedder
```

### 3. Request/Response Objects

**Why:** Explicit contracts, versioning, validation

```python
@dataclass
class IndexRequest:
    sync_mode: SyncMode
    tree_sha: str | None
    # ...

@dataclass
class IndexResponse:
    files_indexed: int
    chunks_created: int
    # ...
```

### 4. Use Case Classes

**Why:** Single responsibility, testability, reusability

```python
class IndexingUseCase:
    def execute(self, request: IndexRequest) -> IndexResponse:
        # Orchestrate business logic
        ...
```

---

## Testing Strategy

### Unit Tests

**Target:** Domain entities, use cases (with mocks)

**Example:**
```python
def test_indexing_usecase_with_mocks():
    # Arrange
    mock_vcs = Mock(spec=VCS)
    mock_embedder = Mock(spec=Embedder)
    usecase = IndexingUseCase(vcs=mock_vcs, embedder=mock_embedder)

    # Act
    response = usecase.execute(request)

    # Assert
    assert response.files_indexed == 5
    mock_embedder.embed_texts.assert_called_once()
```

### Integration Tests

**Target:** Adapters with real infrastructure

**Example:**
```python
def test_sqlite_chunk_repository():
    # Use real SQLite database
    repo = SqliteChunkRepository(Path("/tmp/test.db"))
    chunk = Chunk(...)

    repo.add(chunk)
    retrieved = repo.get(chunk.id)

    assert retrieved == chunk
```

### End-to-End Tests

**Target:** Full CLI commands in temp directories

**Example:**
```python
def test_ember_sync_command():
    # Create temp git repo
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir)
        subprocess.run(["ember", "init"], cwd=tmpdir)
        subprocess.run(["ember", "sync"], cwd=tmpdir)

        # Verify .ember/index.db exists and has data
        assert Path(tmpdir) / ".ember" / "index.db").exists()
```

---

## Storage Design

### SQLite Schema

**chunks** - Code chunks with metadata
```sql
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    language TEXT,
    indexed_at REAL
);
```

**chunk_text** - FTS5 virtual table for full-text search
```sql
CREATE VIRTUAL TABLE chunk_text USING fts5(
    chunk_id UNINDEXED,
    content,
    content=chunks,
    content_rowid=rowid
);
```

**vectors** - Embeddings for semantic search
```sql
CREATE TABLE vectors (
    chunk_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    model_fingerprint TEXT NOT NULL,
    created_at REAL
);
```

**meta** - Repository metadata
```sql
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

**files** - File tracking for incremental sync
```sql
CREATE TABLE files (
    file_path TEXT PRIMARY KEY,
    tree_sha TEXT NOT NULL,
    last_indexed_at REAL
);
```

---

## Performance Considerations

### Indexing

**Current:** Sequential file processing
```python
for file in files:
    chunks = chunk_file(file)
    for chunk in chunks:
        embedding = embedder.embed_texts([chunk.content])  # One at a time
        store(chunk, embedding)
```

**Optimized (Future):**
```python
# Batch embeddings across files
all_chunks = [chunk for file in files for chunk in chunk_file(file)]
embeddings = embedder.embed_texts([c.content for c in all_chunks])  # Batch!
store_all(zip(all_chunks, embeddings))
```

**Expected:** 2-4x speedup (see `PERFORMANCE.md`)

### Search

**Current:** Hybrid search with RRF fusion
- FTS5 for keyword search (~100ms)
- Simple cosine similarity for semantic search (~80ms)
- RRF fusion and ranking

**Future optimizations:**
- sqlite-vss for faster vector search
- Cross-encoder reranking
- Result caching

---

## Extension Points

### Adding a New Embedder

1. Create adapter in `adapters/local_models/`
2. Implement `Embedder` protocol
3. Register in CLI dependency injection
4. Test with existing integration tests

**Example:**
```python
class CustomEmbedder(Embedder):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # Your implementation
        ...

    def fingerprint(self) -> str:
        return "custom-model-v1"
```

### Adding a New Search Strategy

1. Define protocol in `ports/search.py`
2. Create adapter in `adapters/search/`
3. Update `SearchUseCase` to use new strategy
4. Add integration tests

### Adding a New Command

1. Add CLI command in `entrypoints/cli.py`
2. Create use case in `core/`
3. Define request/response DTOs
4. Wire dependencies in CLI command
5. Add integration test

---

## Quality Guardrails

### Pre-Commit Checks

```bash
# Tests must pass
uv run pytest

# Linting must pass
uv run ruff check .

# Type checking (future)
uv run pyright
```

### Code Review Checklist

- [ ] Core never imports from adapters
- [ ] All public functions have type hints
- [ ] Protocols used for ports (not ABC)
- [ ] Dependencies injected via `__init__`
- [ ] Tests added for new functionality
- [ ] CHANGELOG.md updated

---

## Future Architectural Improvements

### v0.2.0+

- **Configuration Loading:** Use `config.toml` for runtime settings
- **Plugin System:** Allow custom chunkers, embedders, search strategies
- **Multi-Repo Support:** Index multiple codebases in one Ember instance
- **HTTP API:** Server mode for AI agent integration

### v0.3.0+

- **Distributed Indexing:** Process large codebases in parallel
- **Remote Embedders:** Support OpenAI, Cohere, etc.
- **Advanced VSS:** Migrate to FAISS or sqlite-vss for scalability

---

## References

- [Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Ports and Adapters Pattern](https://alistair.cockburn.us/hexagonal-architecture/)
- [Python Protocols (PEP 544)](https://peps.python.org/pep-0544/)
- PRD: `prd.md` in repository root

---

**For more information:**
- Development workflow: `MAINTAINER_GUIDE.md`
- Current state: `CLAUDE.md`
- Decision history: `docs/decisions/`
