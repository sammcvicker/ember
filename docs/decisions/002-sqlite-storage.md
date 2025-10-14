# ADR-002: SQLite with FTS5 and VSS for Storage

**Date:** 2025-10-14
**Status:** Accepted
**Deciders:** Sam @ KamiwazaAI
**References:** PRD §4 (Data Model & Storage), §7 (Retrieval)

## Context

Ember needs to store and search:
- Code chunks (text, metadata, line ranges)
- Embeddings (high-dimensional vectors)
- File state tracking for incremental sync
- Configuration and metadata

Requirements:
- **Local-first**: No servers, no cloud dependencies
- **Fast hybrid search**: Both lexical (BM25) and semantic (vector similarity)
- **Portable**: Easy to backup, share, and version
- **Simple**: Minimal setup for users
- **Deterministic**: Reproducible results

Search patterns needed:
1. **Text search**: "function LoadConfig", "error handling"
2. **Vector search**: Semantic similarity to query embedding
3. **Hybrid**: Combine both with fusion (RRF or weighted)
4. **Filtered**: By path, language, tags

## Decision

Use **SQLite** as primary storage with:
- **FTS5** for full-text search (built into Python's sqlite3)
- **sqlite-vss** for vector similarity search (or FAISS as fallback)
- **JSON state file** for lightweight metadata (`.ember/state.json`)

### Schema Design

```sql
-- Core chunks table
CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  project_id TEXT NOT NULL,
  path TEXT NOT NULL,
  lang TEXT,
  symbol TEXT,
  start_line INTEGER,
  end_line INTEGER,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,  -- blake3
  file_hash TEXT NOT NULL,
  tree_sha TEXT,
  rev TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, path, content_hash)
);

-- FTS5 virtual table for text search
CREATE VIRTUAL TABLE chunk_text USING fts5(
  content, path, symbol, lang,
  content='chunks',
  content_rowid='id'
);

-- Vector embeddings
CREATE TABLE vectors (
  chunk_id INTEGER PRIMARY KEY,
  embedding BLOB NOT NULL,
  dim INTEGER NOT NULL,
  model_fingerprint TEXT NOT NULL,
  FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

-- Metadata (index version, model info, chunking params)
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Optional tags
CREATE TABLE tags (
  chunk_id INTEGER,
  key TEXT,
  value TEXT,
  PRIMARY KEY(chunk_id, key),
  FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

-- File tracking for incremental sync
CREATE TABLE files (
  path TEXT PRIMARY KEY,
  file_hash TEXT NOT NULL,
  size INTEGER,
  mtime REAL,
  last_indexed_at TEXT
);
```

### State File
`.ember/state.json`:
```json
{
  "last_tree_sha": "abc123...",
  "last_sync_mode": "worktree",
  "model": "local-default-code-embed",
  "version": "0.1.0"
}
```

## Consequences

### Positive
- ✅ **Single file database**: Easy backup (just copy .ember/)
- ✅ **Built-in FTS5**: No external dependencies for text search
- ✅ **ACID transactions**: Atomic updates, no corruption risk
- ✅ **Cross-platform**: SQLite works everywhere Python does
- ✅ **Portable bundles**: Can export/import entire index
- ✅ **Simple schema migrations**: ALTER TABLE, pragma user_version
- ✅ **Well-understood**: sqlite3 in Python stdlib
- ✅ **Efficient**: Proper indexes, query planner

### Negative
- ⚠️ **sqlite-vss dependency**: May need compilation or fallback
- ⚠️ **Scaling limits**: Large monorepos (100k+ files) may be slow
- ⚠️ **No distributed search**: Single-machine only
- ⚠️ **Vector search performance**: Not as fast as purpose-built systems (Qdrant, Weaviate)

### Mitigations
- Provide **FAISS fallback** if sqlite-vss unavailable (PRD §4)
- Use **proper indexes**: (tree_sha, path), (file_hash), etc.
- Support **path filters** to limit scope: `--in "src/**/*.py"`
- Consider **sharding by project_id** for huge monorepos (future)
- Runtime capability detection: check for VSS on init

## Alternatives Considered

### FAISS + JSON files
**Pros:**
- No sqlite-vss dependency
- Fast vector search
- Simple to reason about

**Cons:**
- No atomic updates (separate vector/text files)
- Manual transaction management
- No built-in text search (need separate index)
- Harder to do filtered queries

### Separate text/vector stores
(e.g., Tantivy for FTS + FAISS for vectors)

**Pros:**
- Best-in-class for each search type

**Cons:**
- Multiple dependencies to install
- Complex synchronization between stores
- Harder to export/import atomically
- Against "local-first, simple" principle

### Embedded databases (DuckDB, LanceDB)
**Pros:**
- Modern, columnar storage
- Good analytical performance

**Cons:**
- Less mature Python ecosystem
- No built-in FTS equivalent to FTS5
- More moving parts
- Overkill for this use case

## Implementation Notes

### Phase 1: sqlite-vss primary
- Try to load `sqlite-vss` extension on init
- If successful, use for vector search
- Store vectors as BLOBs (pickle or numpy bytes)

### Phase 2: FAISS fallback (if needed)
- If sqlite-vss unavailable, fall back to file-based FAISS index
- Keep chunks in SQLite, vectors in `.ember/index.faiss`
- Slightly more complex sync, but works everywhere

### Future optimizations
- **Lazy loading**: Don't load all vectors into memory
- **Quantization**: Use 8-bit or 4-bit vectors for speed
- **Caching**: In-memory cache for hot chunks
- **Sharding**: Split by project_id for multi-repo setups

## References

- SQLite FTS5 docs: https://www.sqlite.org/fts5.html
- sqlite-vss: https://github.com/asg017/sqlite-vss
- FAISS: https://github.com/facebookresearch/faiss
- PRD §4: Data Model & Storage
- PRD §7: Retrieval (Hybrid + Reranking)

## Review Date

Re-evaluate after v0.1 MVP if:
- Performance inadequate on repos >50k files
- sqlite-vss proves too hard to install
- Need distributed/multi-machine search
