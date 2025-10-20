# Ember Development Guide for Claude

**Purpose:** Quick context for AI maintainer to pick up work immediately

---

## 📍 CURRENT STATE

**Status:** Post-v0.1.0 release, working towards v0.2.0
**Branch:** `develop` (for ongoing work)
**Last Release:** v0.1.0 (2025-10-15)
**Active Milestone:** 0.2.0

**What's Working:**
- Core indexing and search functionality ✅
- 103 automated tests passing ✅
- Clean architecture with ports/adapters ✅

**Current Focus:** Implementing v0.2.0 features (see `docs/SCOPE_v0.2.0.md`)

---

## 🎯 NEXT MILESTONE: v0.2.0

See [GitHub milestone](https://github.com/sammcvicker/ember/milestone/1) for all issues.

**Scope:** See `docs/SCOPE_v0.2.0.md` for full roadmap

**Priority Issues:**
1. **#25** - Implement functional config system (enhancement)
2. **#26** - Auto-sync on search for zero-friction workflow (enhancement)
3. **#14** - Batch embedding optimization (2-6x speedup)
4. **#20** - Fast test suite (<10s target)

---

## 🚦 OPERATIONAL WORKFLOW

**For detailed maintainer procedures**, see **[MAINTAINER_GUIDE.md](MAINTAINER_GUIDE.md)**

### Quick Session Start

```bash
# 1. Check context
cat CLAUDE.md | head -30

# 2. See what needs doing
gh issue list --state open --milestone "0.2.0"

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
- Simple vector search (BLOB-based)
- State file at `.ember/state.json`

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
gh issue list --milestone "0.2.0"  # Current milestone issues
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

**Last Updated:** 2025-10-19 (v0.2.0 scope finalized, ready for implementation)
**Format Version:** 2.0 (Simplified)
