# Ember Development Guide for Claude

**Purpose:** Quick context for AI maintainer to pick up work immediately

---

## 📍 CURRENT STATE

**Status:** Post-v0.2.0 release, working towards v1.0.0
**Branch:** `develop` (for ongoing work)
**Last Release:** v0.2.0 (2025-10-20)
**Active Milestone:** 1.0.0
**Theme:** "Be like water" - Remove all friction, make ember feel invisible and natural

**What's Working:**
- Core indexing and search functionality ✅
- Auto-sync on search (zero-friction workflow) ✅
- Functional config system (.ember/config.toml) ✅
- sqlite-vec for fast vector search (100x speedup) ✅
- Batch embedding optimization (2-6x faster indexing) ✅
- Fast test suite (<10s) ✅
- Clean, refactored CLI (29% complexity reduction) ✅
- 125 automated tests passing ✅
- Clean architecture with ports/adapters ✅

**Current Focus:** Removing friction for 1.0.0 - make ember instant, effortless, and complete

---

## 🎯 NEXT MILESTONE: v1.0.0 "Be Like Water"

See [GitHub milestone](https://github.com/sammcvicker/ember/milestone/4) for all issues.

**Philosophy:** Remove every snag. Make ember feel instant, effortless, and natural - like water flowing through a streambed.

**Critical Path (High Priority):**
1. **#46** - Reduce model initialization time (2+ seconds → instant) ⚡ `[performance]`
   - *Biggest friction point - investigate daemon architecture*
2. **#43** - Support subdirectories and path-scoped search 📁 `[enhancement]`
   - *Work from anywhere, like git*
3. **#47** - Index untracked/unstaged files 📝 `[enhancement]`
   - *Search what you see, not what's committed*

**Polish & Visibility (Medium Priority):**
4. **#44** - Fix progress bar jumping 🎨 `[dx, performance]`
   - *Quick visual win - stable progress display*
5. **#45** - Add `ember status` command 📊 `[dx, enhancement]`
   - *Observability: show index state and config*

**Total:** 5 issues, ~25-38 hours effort
**Outcome:** A tool that feels invisible - fast, complete, and friction-free

**Completed in v0.2.0:**
- All 11 milestone issues closed ✅
- All 7 tech debt issues from audit closed ✅
- Zero open issues at release (clean slate!) ✅

---

## 🚦 OPERATIONAL WORKFLOW

**For detailed maintainer procedures**, see **[MAINTAINER_GUIDE.md](MAINTAINER_GUIDE.md)**

### Quick Session Start

```bash
# 1. Check context
cat CLAUDE.md | head -30

# 2. See what needs doing
gh issue list --state open --milestone "1.0.0"

# 3. Check branch status
git status
git log --oneline -5

# 4. Pick highest priority issue and work it
```

### Work Pattern

1. **Pick issue** from milestone
2. **Create branch** from `develop`: `git checkout -b fix/issue-N-description`
3. **Work with tests**: Write tests, implement, verify
4. **Update CHANGELOG.md** under "Unreleased" section
5. **PR to `develop`** (NOT main!)
6. **Merge and close issue**

**See MAINTAINER_GUIDE.md for full details on releases, PRs, commits, etc.**

---

## 🏗️ ARCHITECTURE QUICK REFERENCE

### Clean Architecture Layers (PRD §3)

```
ember/
  core/        # Use cases - pure Python, NO infra imports
  domain/      # Entities & value objects
  ports/       # Abstract interfaces (Protocols)
  adapters/    # Infrastructure (SQLite, git, embedders)
  app/         # CLI commands - thin layer, no logic
```

### Key Principles

- **Dependency Rule:** `core/` depends ONLY on `ports/`, never `adapters/`
- **Injection:** Dependencies via `__init__`, never global
- **Types:** Type hints everywhere, use `Protocol` for ports
- **Paths:** Always absolute (`pathlib.Path`)

### Storage

- SQLite at `.ember/index.db`
- FTS5 for text search
- sqlite-vec for fast vector similarity search
- Metadata stored in same database

---

## ✅ QUALITY STANDARDS (Never Break These)

Before every commit:
- [ ] **Tests pass:** `uv run pytest`
- [ ] **Linter passes:** `uv run ruff check .`
- [ ] **Architecture:** No `core/` imports from `adapters/`
- [ ] **Types:** All public functions have type hints
- [ ] **Docs:** Update CHANGELOG.md for user-facing changes
- [ ] **Conventions:** Conventional commit messages

---

## 🧭 COMMON COMMANDS

```bash
# Development
uv sync                    # Install/update dependencies
uv run pytest              # Run all tests
uv run pytest -v           # Verbose test output
uv run ruff check .        # Lint code

# Git workflow
git checkout develop       # Work from develop branch
git checkout -b feat/...   # Create feature branch
git log --oneline -10      # Recent commits

# GitHub CLI
gh issue list --milestone "1.0.0"  # Current milestone issues
gh pr create --base develop        # PR to develop (NOT main!)
gh pr merge --squash               # Merge and squash commits

# Ember testing
cd /tmp && rm -rf test-repo
mkdir test-repo && cd test-repo && git init
uv run /path/to/ember init
```

---

## 📖 KEY DOCUMENTS

**For Users:**
- `README.md` - Installation and quick start
- `CHANGELOG.md` - Version history and changes

**For Maintainers:**
- `CLAUDE.md` (this file) - Quick context and current state
- `MAINTAINER_GUIDE.md` - Detailed operational procedures
- `prd.md` - Product requirements and vision

**Technical:**
- `docs/decisions/` - Architecture Decision Records
- `docs/PERFORMANCE.md` - Benchmarks and optimization notes

---

## 📝 SESSION END CHECKLIST

Before finishing a session:
- [ ] All changes committed to feature branch
- [ ] PR created (if work is complete)
- [ ] Tests passing
- [ ] CLAUDE.md updated if significant state change
- [ ] CHANGELOG.md updated for user-facing changes

---

## 🔍 DECISION LOG (Quick Reference)

See `docs/decisions/` for full ADRs:

- **001**: Clean Architecture with ports/adapters
- **002**: SQLite + FTS5 + VSS for storage
- **003**: Jina Embeddings v2 Code model

---

**Last Updated:** 2025-10-21 (v1.0.0 milestone planned - "be like water")
**Format Version:** 2.0 (Simplified)
