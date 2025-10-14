# ADR 003: Embedding Model Choice

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** Sam @ KamiwazaAI

---

## Context

Ember needs a text embedding model for semantic code search (PRD §8). The model must:

1. **Code-aware**: Understand code syntax and semantics across multiple languages
2. **Local & CPU-friendly**: Run efficiently on consumer hardware without GPU
3. **Small size**: Reasonable parameter count (100M-500M) for fast inference
4. **Right dimensions**: 384-768 dims as specified in PRD
5. **Sentence-transformers compatible**: Work with our existing dependency

The model will be used to:
- Embed code chunks (functions, classes, methods)
- Enable semantic similarity search
- Power hybrid search (BM25 + vector)
- Support deterministic fingerprinting for index compatibility

---

## Decision

We will use **jinaai/jina-embeddings-v2-base-code** as the default embedding model.

### Model Specifications

- **Name:** `jinaai/jina-embeddings-v2-base-code`
- **Parameters:** 161 million
- **Dimensions:** 768
- **Context length:** 8192 tokens
- **Languages:** English + 30 programming languages
- **Architecture:** BERT with ALiBi for longer sequences
- **Pooling:** Mean pooling
- **Normalization:** L2 normalized by default
- **License:** Apache 2.0 (open source)

### Integration Details

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "jinaai/jina-embeddings-v2-base-code",
    trust_remote_code=True
)
model.max_seq_length = 512  # Conservative default
embeddings = model.encode(texts, normalize_embeddings=True)
```

---

## Rationale

### Why Jina Embeddings v2 Code?

1. **Code-specific training**: Specifically trained on coding-related datasets, unlike general-purpose models
2. **Multi-language support**: Handles 30+ programming languages (Python, TypeScript, Go, Rust, Java, etc.)
3. **Optimal size**: 161M params hits sweet spot for CPU inference (fast enough without GPU)
4. **Long context**: 8192 tokens handles large functions/classes without truncation
5. **Production-ready**: Actively maintained by Jina AI with good documentation
6. **Memory efficient**: Designed for "fast and memory efficient" inference
7. **Sentence-transformers native**: First-class support, no adapter needed

### Alternatives Considered

| Model | Params | Dims | Pros | Cons |
|-------|--------|------|------|------|
| **bge-small-en-v1.5** | 33M | 384 | Very fast, tiny | Not code-specific, short context |
| **gte-large-en-v1.5** | 305M | 1024 | High quality | Too large for CPU, too many dims |
| **all-MiniLM-L6-v2** | 22M | 384 | Fast, popular | General-purpose, not code-tuned |
| **Nomic Embed Code** | 7B | variable | Strong performance | Too large for CPU-first use case |
| **CodeSage Large** | 1.3B | variable | Code-specific | Too large, overkill for local use |

### Performance Expectations

- **Speed:** ~100-500 chunks/sec on M4 CPU (estimated)
- **Memory:** ~600MB model size + ~1GB working memory
- **Quality:** Code-aware embeddings better than general-purpose models for code search

---

## Consequences

### Positive

- ✅ CPU-friendly inference (no GPU required)
- ✅ Code-aware embeddings improve search quality
- ✅ 768 dims provide good semantic resolution
- ✅ Long context (8192 tokens) prevents truncation
- ✅ Apache 2.0 license allows commercial use
- ✅ Easy integration via sentence-transformers
- ✅ Multi-language support covers most popular languages

### Negative

- ⚠️ First-time download is ~600MB (cached thereafter)
- ⚠️ Larger than smallest models (161M vs 33M for bge-small)
- ⚠️ Requires `trust_remote_code=True` (model uses custom BERT variant)
- ⚠️ Model updates could change embeddings (mitigated by fingerprinting)

### Mitigations

1. **Fingerprinting:** Generate deterministic fingerprint including model name, version, config to detect incompatible indexes
2. **Lazy loading:** Only load model when actually needed (not at CLI startup)
3. **Batch processing:** Use batch encoding to amortize model overhead
4. **Caching:** HuggingFace cache ensures one-time download

---

## Implementation Notes

### Fingerprint Format

```
jinaai/jina-embeddings-v2-base-code:v2:{config_hash}
```

Config hash includes:
- Model name
- Dimensions (768)
- Max sequence length
- Pooling strategy (mean)
- Normalization (L2)

### Default Configuration

- **Max sequence length:** 512 tokens (conservative, adjustable)
- **Batch size:** 32 (balance between speed and memory)
- **Device:** Auto-detect (CPU by default, GPU if available)
- **Normalization:** Always enabled (for cosine similarity)

### Future Considerations

1. **Model swapping:** Clean architecture allows swapping models via Embedder protocol
2. **Quantization:** Could add ONNX/quantized version for even faster inference
3. **Model updates:** May evaluate newer models (e.g., Jina v3) in future releases
4. **Custom fine-tuning:** Could fine-tune on specific codebases if needed

---

## References

- [Jina Embeddings v2 announcement](https://jina.ai/news/jina-embeddings-2-the-best-solution-for-embedding-long-documents/)
- [Model card on HuggingFace](https://huggingface.co/jinaai/jina-embeddings-v2-base-code)
- [Sentence-transformers documentation](https://www.sbert.net/)
- [PRD §8: Embedding Models & Performance](../prd.md#8-embedding-models--performance)

---

**Status:** Implemented in `ember/adapters/local_models/jina_embedder.py`
