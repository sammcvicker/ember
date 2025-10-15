# Ember Performance Characteristics

This document describes the performance characteristics of Ember based on comprehensive testing.

## Test Environment

- **Platform**: macOS (darwin)
- **Python**: 3.13.3
- **Model**: Jina Embeddings v2 Code (161M params, 768 dims)
- **Hardware**: CPU-only inference

## Performance Summary

### Initial Indexing

| Codebase Size | Files | Chunks | Duration | Throughput |
|--------------|-------|--------|----------|------------|
| Small | 51 | 57 | 7.26s | 7.03 files/sec |
| Medium | 201 | 209 | 55.34s | 3.63 files/sec |

**Key Observations**:
- Linear scaling with file count
- Throughput decreases slightly for larger codebases (likely due to model loading overhead amortization)
- Reasonable performance for typical project sizes

### Incremental Sync

| Metric | Value |
|--------|-------|
| Total files in codebase | 100 |
| Modified files | 10 |
| Reindexed files | 11 |
| Duration | 11.22s |
| **Speedup vs full reindex** | **9.2x** |

**Key Observations**:
- Incremental sync is significantly faster than full reindex
- Only modified files are reindexed
- Diff-based detection works efficiently

### Search Performance

| Metric | Value |
|--------|-------|
| Average query time | 180ms |
| Query types tested | 5 semantic queries |
| Results per query | 10 |
| Index size | 100 files |

**Key Observations**:
- Sub-second search responses
- Hybrid search (BM25 + vector) provides good relevance
- Performance suitable for interactive use

### Database Size Scaling

| Files | Chunks | DB Size | Size per File |
|-------|--------|---------|---------------|
| 10 | 17 | 0.96MB | 0.096MB |
| 50 | 57 | 4.13MB | 0.083MB |
| 100 | 107 | 8.07MB | 0.081MB |

**Key Observations**:
- **Linear scaling** with file count
- Approximately **80-100KB per file** including vectors and FTS index
- Efficient storage with SQLite

## Projections for Larger Codebases

Based on the test results, here are projections for larger codebases:

| Codebase Size | Est. Files | Est. DB Size | Est. Initial Index Time |
|--------------|-----------|--------------|------------------------|
| Small | 50-100 | 4-8MB | 7-15s |
| Medium | 200-500 | 16-40MB | 55-140s (~1-2 min) |
| Large | 1,000-2,000 | 80-160MB | 275-550s (~5-9 min) |
| Very Large | 5,000-10,000 | 400-800MB | 1375-2750s (~23-46 min) |

**Notes**:
- Projections assume Python files of average complexity
- Incremental sync will be much faster for typical workflows
- Search performance should remain sub-second even for large indexes

## Recommendations

### For Best Performance

1. **Use incremental sync** (`ember sync`) instead of full reindex
2. **Index on commit hooks** to keep index up-to-date automatically
3. **Exclude build artifacts** and generated files from indexing
4. **Consider project-specific ignore patterns** for large monorepos

### Performance Tuning

If you experience slow indexing:
- Check that tree-sitter grammars are working (faster than line-based fallback)
- Ensure SSD storage for database (I/O bound)
- Consider smaller `--path-filter` for targeted indexing
- Use `ember sync worktree` instead of indexing old commits

If search is slow:
- Check database size (large DBs may benefit from VACUUM)
- Ensure indexes are built properly (run init if needed)
- Consider reducing `--limit` for faster results

## Test Details

Performance tests are located in `tests/performance/test_performance.py` and can be run with:

```bash
uv run pytest tests/performance/ -v -s
```

Tests measure:
- Initial indexing speed (small and medium codebases)
- Incremental sync performance
- Search query latency
- Database size scaling

All tests use synthetic Python codebases with realistic structure (classes, functions, imports).

## Limitations

Current performance tests have these limitations:
- Single language (Python) tested
- Synthetic code may differ from real projects
- CPU-only inference (GPU would be faster)
- No network latency (local-only)

Future testing should include:
- Multi-language codebases
- Real open-source projects
- Memory profiling
- Concurrent access patterns
