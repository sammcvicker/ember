# Ember v0.2.0 Scope

**Release Theme:** *"Promises Delivered"*

**Target:** Ship a focused release that makes the core excellent and cuts the bloat.

---

## Mission Statement

**Ember is the definitive tool for semantic codebase search. Fast, local, trivial to use.**

Not a security scanner. Not a code analyzer. Not a deployment tool.
Just exceptionally good at one thing: helping developers and AI agents find code semantically.

---

## Release Scope

### 1. Config System That Works
**Issue:** v0.1.0 shipped `.ember/config.toml` but it's never loaded or used.

**Goal:** Deliver what we promised. Config should actually work.

**Scope:**
- Load and validate `.ember/config.toml` on all commands
- Respect user settings for:
  - Model selection (if alternate models added)
  - Chunk size/overlap settings
  - Search defaults (topk, etc.)
  - Include/ignore patterns (currently git-only)
- Graceful fallback to defaults if config missing/invalid
- Clear error messages for config issues

**Success criteria:**
- User can set `topk = 10` in config and it's respected
- User can configure `include`/`ignore` patterns
- All config options documented in README

---

### 2. Performance: Batch Embeddings
**Issue #14:** 2-6x indexing speedup potential

**Goal:** Make large repo indexing practical.

**Scope:**
- Implement batch embedding calls (current: 1 chunk = 1 API call)
- Tune batch size for optimal throughput vs memory
- Validate speedup on small/medium/large repos
- Update PERFORMANCE.md with new benchmarks

**Success criteria:**
- 2x+ speedup on medium repos (200+ files)
- No regression on small repos
- Memory usage stays reasonable (<2GB)

---

### 3. Auto-Sync on Search
**Goal:** Zero-friction workflow. Always search current code.

**Scope:**
- `ember find` auto-detects stale index before searching
- Auto-runs incremental sync if needed
- Shows progress: "Syncing 3 changed files... ✓ (1.2s)"
- Add `--no-sync` flag for power users who want speed

**Success criteria:**
- User never gets stale results
- <2s overhead for typical incremental sync
- Clear feedback about what's happening

**Non-goal:**
- Watch mode / daemon - premature complexity

---

### 4. Developer Experience
**Issue #20:** Test suite takes minutes, not seconds

**Goal:** Fast feedback loop for development.

**Scope:**
- Profile test suite to find bottlenecks
- Optimize or parallelize slow tests
- Target: <10s for full suite (currently minutes)

**Success criteria:**
- `uv run pytest` completes in <10s
- All tests still pass
- No reduction in coverage

---

## Explicitly Out of Scope

These features are deferred or permanently cut:

### Deferred to Future Releases
- **Import/Export commands** - Wait for real user demand, CI caching use case
- **Cross-encoder reranking** - Optimization, not core functionality
- **Watch mode** - Solved by auto-sync, daemon adds complexity
- **Custom embedding models** - Default works great, premature optimization

### Permanently Cut
- **`ember audit` command** - Wrong tool for the job. Use Trufflehog/Gitleaks.
- **HTTP server** - CLI-first is the right approach. Maybe post-1.0 if needed.
- **Secret redaction** - Security theater. Don't index secrets in the first place.

---

## Path to 1.0

```
v0.2.0 (Q4 2025): Promises delivered
  ├─ Config system works
  ├─ Performance (batch embeddings)
  ├─ Auto-sync on search
  └─ Fast tests

v0.3.0 (Q1 2026): Polish & gaps (TBD based on 0.2 feedback)
  ├─ User feedback from 0.2
  ├─ Edge case fixes
  └─ Any critical gaps

v1.0.0 (Q2 2026): "This is the semantic search tool"
  ├─ Stable API
  ├─ Production-ready performance
  └─ Comprehensive documentation
```

---

## Success Metrics for v0.2.0

1. **Functionality:** Config system fully works, all settings respected
2. **Performance:** 2x+ indexing speedup on medium repos
3. **UX:** Auto-sync makes stale results impossible
4. **DX:** Test suite <10s, fast development feedback
5. **Quality:** All 103+ tests passing, no regressions
6. **Documentation:** README updated, CHANGELOG complete

---

## What Makes This Release Special

**v0.2.0 is a manifesto.** It says:

> "We're not trying to be everything.
> We're the best at semantic search, period.
> Fast. Local. Trivial to use."

This release delivers on v0.1.0's promises and cuts everything that doesn't serve the core mission.

---

**Last Updated:** 2025-10-19
**Status:** Approved and locked for development
