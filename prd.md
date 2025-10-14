# Ember — Local Codebase Embedding & Search CLI

**Owner:** Sam @ KamiwazaAI
**Tech choices:** Python 3.13, `click` for CLI, `uv` for packaging, SQLite for storage
**Principles:** Local-first • Fast • Deterministic • Clean Architecture • SOLID • Replaceable infra

---

## 1) Problem Statement & Goals

**Problem:** Quickly turn any codebase into a searchable knowledge base that both humans and AI agents can query—without servers, MCP, or cloud dependencies.

**Primary goals**

* *Fast local indexing* of codebases (worktree, staged, specific commit).
* *Incremental sync* using Git history—robust across rebases/renames.
* *High-quality retrieval* via hybrid search (BM25/FTS + vector) with sensible defaults and an optional reranker.
* *Determinism & shareability* via commit/tree SHA pinning and portable indexes.
* *Agent-friendly* JSON outputs with stable schemas.

**Non-goals (v1)**

* Full semantic code-understanding (e.g., whole-program analysis).
* Multi-repo distributed search (monorepo supported; multi-root supported in one DB).
* Hosted service. Keep everything local.

---

## 2) CLI Surface (MVP)

```bash
ember init                       # initialize .ember/ and config
ember sync [--worktree|--staged|--rev <ref>] [--reindex]
ember find <query> [--topk 20] [--json] [--in path/**.py] [--lang go,ts] [--filter key=val]
ember open <idx>                 # open result in $EDITOR at range
ember cat <idx> [--context N]    # print snippet with context
ember export [--rev <ref>]       # export portable index bundle
ember import <bundle.tar]        # import a shared index (no source needed)
ember audit                      # scan for likely secrets in chunks
ember explain <idx>              # show why a result matched (terms + sim)
```

**Flags & defaults**

* `--worktree` (default), `--staged`, `--rev <SHA|ref>`
* `--topk` default 20, `--no-rerank` disables cross-encoder reranking
* `--json` emits stable schema (see §9)
* `--in` glob filter; `--lang` comma list; `--filter key=val` tags

---

## 3) Architecture (Clean + SOLID)

**Layered (Clean Architecture) layout**

```
ember/
  app/                 # CLI commands, DTOs for IO, no business logic
  core/                # Use-cases & domain services (pure Python)
    indexing/
    retrieval/
    git/
    chunking/
    config/
    export/
  domain/              # Entities & value objects (Chunk, RepoState, Query)
  ports/               # Abstract interfaces
    repositories.py    # DB repo interfaces
    embedders.py       # vectorizer interface
    search.py          # BM25/vector/reranker ports
    vcs.py             # git interface
    fs.py              # filesystem interface
  adapters/            # Infra implementations
    sqlite/
    fts/
    vss/
    faiss/             # optional
    git_cmd/           # subprocess git
    local_models/      # gguf/onnx loaders
  shared/              # errors, logging, utils
  entrypoints/
    cli.py             # click commands
    http.py            # optional tiny HTTP server
```

**SOLID mapping**

* **S**: Each use-case (Init, Sync, Find, Export…) is a class/function in `core`.
* **O**: New storage (FAISS vs sqlite-vss) or models implement `ports.*`.
* **L**: Ports return minimal protocol-friendly types; adapters remain substitutable.
* **I**: Granular ports (Embedder, TextSearch, VectorSearch, Reranker) avoid fat interfaces.
* **D**: `core` depends only on `ports`, never concrete adapters.

**Why this helps later**: Swap `sqlite-vss` → `faiss`, or `bge-code` → `gte-code` with no core changes. Add a remote server adapter if desired without touching domain logic.

---

## 4) Data Model & Storage

**SQLite in `.ember/index.db`** (ships everywhere, simple backups)

Tables (logical):

* `chunks` — id, project_id, path, lang, symbol, start_line, end_line, content_hash, file_hash, tree_sha, rev, created_at
* `chunk_text` — FTS5 virtual table on `(content, path, symbol, lang)`
* `vectors` — chunk_id, embedding (BLOB), dim, model_fingerprint
* `meta` — key, value (model name+version, index version, chunking params)
* `tags` — chunk_id, key, value (e.g., `team=search`)
* `files` — path, file_hash, size, mtime, last_indexed_at

**Indexes**: by `(tree_sha, path)`, `chunk_text` FTS5, `vectors` VSS/FAISS.
**Alternative**: fall back to FAISS (file-backed) if `sqlite-vss` unavailable.

**State file**: `.ember/state.json`

```json
{"last_tree_sha":"…","last_sync_mode":"worktree","model":"local-default-code-embed","version":"0.1.0"}
```

---

## 5) Git Integration & Incremental Sync

**Snapshot semantics**

* `worktree` (default): index files on disk.
* `staged`: staged changes on top of last commit.
* `rev <ref>`: index exact commit tree.

**Robust incremental**

* Compute prior `tree_sha` per project; use `git diff --name-status <tree_sha> <target>` to detect A/M/D/R.
* Use `blake3` per **chunk** (not just file) to avoid re-embedding unchanged windows.
* Renames (`R`) transfer chunk rows without re-embed if file hash is identical.

**Rebase safety**

* Persist actual **tree SHA** (not HEAD) in `chunks.tree_sha`. Rebases won’t confuse sync.

---

## 6) Chunking Strategy

**Default**: symbol-aware chunks using **tree-sitter** where possible.

* Chunk = signature + docstring/comments + body.
* Add small overlap (e.g., 10–20 lines) to preserve context across boundaries.

**Fallback**: line-based sliding windows (e.g., 120 lines, stride 100) for unknown langs.

**Metadata**: path, lang, symbol, start/end lines, short summary.

**Rationale**: Function/class-level granularity improves retrieval quality, reduces duplication, and is more useful to paste into prompts.

---

## 7) Retrieval: Hybrid + Optional Reranking

**Phase 1 (candidate gen)**

* BM25/FTS5 against `chunk_text` for lexical/name matches.
* ANN query against `vectors` for semantic matches.
* Fuse (e.g., Reciprocal Rank Fusion or weighted sum) into top-K (100).

**Phase 2 (rerank, optional)**

* Local cross-encoder reranker (tiny model) on the 100 candidates → top-`k`.
* Off by default; enable via `--rerank` or config.

**Explainability**

* `ember explain <idx>` shows FTS terms matched + cosine sim.

---

## 8) Embedding Models & Performance

**Model port** (`ports.embedders.Embedder`):

```python
class Embedder(Protocol):
    name: str
    dim: int
    fingerprint: str
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
```

**Recommended defaults (local CPU-first)**

* Small, code-tuned models (e.g., `gte-code`/`bge-code` class), 384–768 dims.
* Batch size configurable; `--threads` for parallel encode.
* Optional quantized backends (gguf/onnx) for speed.

**Determinism**

* Record model name, fingerprint, pooling, normalization in `meta`.
* Preprocessing options (max tokens, truncation strategy) stored as well.

---

## 9) I/O Contracts & JSON Schema

**Find response (stable)**

```json
{
  "query": "how do we parse config?",
  "top_k": 10,
  "results": [
    {
      "id": 7,
      "path": "pkg/config/loader.go",
      "symbol": "LoadConfig",
      "lang": "go",
      "start_line": 42,
      "end_line": 97,
      "score": 0.83,
      "rev": "a1b2c3d",
      "tree_sha": "…",
      "preview": "func LoadConfig(path string) (Config, error) { … }",
      "tags": {"team": "platform"}
    }
  ]
}
```

**Errors**

* Machine-readable problem details `{ "error": { "code": "MODEL_MISSING", "message": "…" } }`.

---

## 10) Config & Ignore Rules

`.ember/config.toml` (created by `init`)

```toml
[index]
model = "local-default-code-embed"
chunk = "symbol"                # symbol|lines
line_window = 120
line_stride = 100
overlap_lines = 15
include = ["**/*.py", "**/*.ts", "**/*.go"]
ignore  = [".git/", "node_modules/", "dist/", "build/"]

[search]
topk = 20
rerank = false
filters = []

[redaction]
patterns = ["(?i)api_key\\s*[:=]\\s*['\"]?[A-Za-z0-9-_]{16,}"]
max_file_mb = 5
```

Respects `.gitignore` and optional `.emberignore`.

---

## 11) Security & Sharing

**Redaction**

* Pre-embedding regex redaction (`[REDACTED]`) applied to content.
* `ember audit` scans indexed chunks for likely secrets.

**Export/import**

* `ember export --rev <ref>` → `bundle.tar`: `{ index.db, manifest.json }`.
* `manifest.json`: repo url (optional), tree_sha, model fingerprint, created_at, previews policy.
* Allow `--no-preview` to strip chunk contents and keep only metadata + hashed previews.

**Threat model**

* Embeddings can leak. Treat `bundle.tar` as sensitive; provide `--share-audit` report.

---

## 12) Developer Experience & Packaging

**uv (package management)**

* `uv init`, `uv lock`, `uv run ember …`.
* Provide `pyproject.toml` with `project.scripts = { ember = "ember.entrypoints.cli:main" }`.

**click (CLI)**

* Subcommands map 1:1 to use-cases; all IO formatting happens in `app/` layer.

**Makefile / taskfile**

```make
setup:         ## install deps
	uv sync
lint:
	ruff check . && pyright
format:
	ruff format .
test:
	pytest -q
```

**Type checking & style**: `pyright`, `ruff`, `pytest`.

**Logging**: structured, leveled (`--verbose`, `--quiet`).

---

## 13) Performance Plan

* Batch embedding with backpressure.
* Chunk-level hashing to skip identical content.
* ANN index build on-demand; persisted between runs.
* Parallel file read + parse (ThreadPool) and model encode (ProcessPool if CPU-bound).
* Bench harness: `scripts/bench.py` against a known OSS repo; track `files/sec`, `chunks/sec`.

---

## 14) Testing Strategy

* **Unit**: domain entities, chunkers (golden files), fusers, explain.
* **Contract**: ports/adapters using test doubles.
* **Integration**: real SQLite + FTS5 + VSS path; fixture repo with synthetic commits (renames, rebases).
* **End-to-end**: run `init → sync → find` on a small repo; snapshot JSON.

---

## 15) Roadmap

**v0.1 (MVP)**

* `init`, `sync`, `find` (hybrid w/ FTS5 + vectors), `open`, `cat`, config, ignore.
* Local code-embedding model (default) + model registry.
* Git-aware incremental sync; chunk hashing; rename handling.
* Export/import bundle; basic `audit`.

**v0.2**

* Optional cross-encoder reranker.
* `explain` command.
* `watch` mode (fsnotify) for immediate updates.

**v0.3**

* `serve` lightweight HTTP for agents (CORS).
* `pack --tokens` to build prompt context packs.
* Multi-project tagging & filters.

**v1.0**

* Pluggable retrieval strategies; adapter registry via entry points.
* Full config validation; migration tooling for `index.db`.

---

## 16) Risks & Mitigations

* **Embedding model drift** → lock fingerprint in `meta`; refuse mixing dims.
* **FTS/VSS portability** → offer FAISS fallback; run-time capability detection.
* **Git edge cases** (submodules, LFS) → ignore by default; guide to include with flags.
* **Secret leakage via previews** → redaction + `--no-preview` + `audit`.
* **Performance on huge monorepos** → path filters, lazy vectorization, shard by `project_id`.

---

## 17) Open Questions

1. Default model choice: exact name + license? (decide before release)
2. Do we normalize to Unicode NFC and strip trailing whitespace before hashing? (recommend **yes**)
3. Reranker cost/benefit: which tiny model hits best P95?
4. How to treat generated code dirs (`gen/`, `api/`)? Default ignore or tag? (recommend **ignore**)
5. Should `export` include source snippets or only previews by default? (recommend **previews on**, with `--no-preview` option)

---

## 18) Implementation Sketches

**Port definitions (abridged)**

```python
# ports/embedders.py
class Embedder(Protocol):
    name: str
    dim: int
    fingerprint: str
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

# ports/search.py
class TextSearch(Protocol):
    def add(self, chunk_id: int, text: str, meta: dict): ...
    def query(self, q: str, topk: int) -> list[tuple[int,float]]: ...

class VectorSearch(Protocol):
    def add(self, chunk_id: int, vec: list[float]): ...
    def query(self, vec: list[float], topk: int) -> list[tuple[int,float]]: ...

class Reranker(Protocol):
    def rerank(self, query: str, candidate_pairs: list[tuple[int,str]]) -> list[int]: ...
```

**Use-case example**

```python
# core/retrieval/find_usecase.py
@dataclass
class FindRequest:
    query: str; topk: int = 20; filters: dict[str,str] | None = None; json: bool = False

class FindUseCase:
    def __init__(self, text: TextSearch, vec: VectorSearch, fuse: Fuser, repo: ChunkRepo, reranker: Reranker | None):
        ...
    def exec(self, req: FindRequest) -> FindResponse:
        text_hits = self.text.query(req.query, 100)
        vec_hits  = self.vec.query(self.embedder.embed_texts([req.query])[0], 100)
        candidates = self.fuse.combine(text_hits, vec_hits)
        if self.reranker:
            ordered = self.reranker.rerank(req.query, [(id, self.repo.get_text(id)) for id,_ in candidates])
        else:
            ordered = [id for id,_ in candidates]
        return self.repo.fetch_results(ordered[:req.topk])
```

**Click entrypoint**

```python
# entrypoints/cli.py
@click.group()
def main(): ...

@main.command()
@click.option('--worktree', is_flag=True, default=True)
@click.option('--staged', is_flag=True)
@click.option('--rev')
def sync(worktree, staged, rev):
    ...

@main.command()
@click.argument('query')
@click.option('--topk', default=20)
@click.option('--json', 'as_json', is_flag=True)
def find(query, topk, as_json):
    ...
```

---

## 19) Acceptance Criteria (MVP)

* `ember init` creates `.ember/` with config and empty `index.db`.
* `ember sync` on a mid-size repo (<10k files) completes <2 min on M4 MBP (baseline); re-run after 1-file edit completes <2s.
* `ember find` returns mixed lexical+semantic results, stable JSON with `--json`.
* Export/import works; `ember find` on imported bundle returns non-empty results.
* Redaction patterns applied before embedding; `audit` flags at least seeded test secrets.

---

## 20) Developer Notes

* Prefer dependency-injected constructors; no singletons in `core`.
* Keep adapters thin; if an adapter grows, split into submodules.
* All file access goes through `ports.fs` to simplify testing.
* Migrations: bump `meta.index_version`; provide simple migrator script.

---

## 21) Quick Start (dev)

```bash
uv init ember
uv add click ruff pyright pytest sqlite-vss # (or faiss-cpu) tree-sitter blake3
uv run ember init
uv run ember sync
uv run ember find "how is config loaded?" --topk 10
```
