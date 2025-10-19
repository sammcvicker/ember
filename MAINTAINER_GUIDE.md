# Ember Maintainer Guide

**For:** Claude (AI maintainer) and future contributors
**Purpose:** Operational framework for maintaining Ember efficiently

---

## Branch Strategy

### Permanent Branches
- **`main`** - Stable, released code only. Always deployable. Tagged with version numbers.
- **`develop`** - Integration branch for next release. All PRs merge here first.

### Temporary Branches
- `feat/issue-N-description` - New features
- `fix/issue-N-description` - Bug fixes
- `perf/issue-N-description` - Performance improvements
- `docs/issue-N-description` - Documentation work

### Workflow
1. Create feature branch from `develop`
2. Work on the feature/fix
3. Create PR to merge into `develop`
4. When ready for release: merge `develop` → `main` and tag

---

## Release Management

### Semantic Versioning
- `0.x.0` - Minor releases with new features
- `0.x.y` - Patch releases with bug fixes only
- `1.0.0` - When project is production-ready

### Release Process
1. Ensure all features for release are merged to `develop`
2. Update `CHANGELOG.md` (convert "Unreleased" section to version number with date)
3. Update version in `pyproject.toml`
4. Create PR: `develop` → `main` with title "Release vX.Y.Z"
5. After merge, create git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
6. Create GitHub release: `gh release create vX.Y.Z --title "vX.Y.Z" --notes-file RELEASE_NOTES.md`
7. Back-merge to develop if needed: `git checkout develop && git merge main`

### CHANGELOG Maintenance
- Keep `CHANGELOG.md` updated as each PR merges
- Add items under "## Unreleased" section
- When releasing, rename "Unreleased" to version number with date
- Add new "Unreleased" section for next version

---

## Issue Management

### Milestones
- **0.x.0** - Next minor release (active development)
- **Backlog** - Nice-to-have items without timeline
- **Future versions** - Create as needed for long-term planning

### Labels
- `bug` - Something broken
- `enhancement` - New feature request
- `documentation` - Docs improvements
- `performance` - Speed/efficiency improvements
- `good first issue` - For future contributors

### Issue Assignment
- Assign to yourself when picking up an issue
- Comment "Working on this" when starting
- Link PR when opening it
- Close with "Fixed in #PR" or "Resolved in #PR"

---

## Session Start Workflow

When starting a new session:

```bash
# 1. Read context
cat CLAUDE.md | head -50  # Check "Current State" section

# 2. Check open issues and prioritize
gh issue list --state open --milestone "0.2.0"

# 3. Check current branch and status
git status
git log --oneline -5

# 4. Priority order:
#    - Bugs/blockers first
#    - Issues in current milestone
#    - Documentation improvements
#    - New features
```

---

## Work Execution Pattern

### For Each Issue

```bash
# 1. Pick and assign issue
gh issue view N
# Assign to yourself via GitHub UI if not already assigned

# 2. Create feature branch
git checkout develop
git pull origin develop
git checkout -b fix/issue-N-description

# 3. Work on the issue
# - Write code
# - Add tests
# - Update docs if needed

# 4. Test thoroughly
uv run pytest
uv run ruff check .

# 5. Update CHANGELOG.md
# Add entry under "## Unreleased" section

# 6. Commit with conventional commit format
git add -A
git commit -m "fix(scope): description

Fixes #N

Detailed explanation if needed"

# 7. Push and create PR
git push -u origin fix/issue-N-description
gh pr create --base develop --title "Fix: description" --body "$(cat <<'EOF'
Fixes #N

## Changes
- Bullet points of what changed

## Testing
- How I tested it
- Which tests pass

## Notes
- Any caveats or follow-up needed
EOF
)"

# 8. Merge PR (if tests pass and looks good)
gh pr merge --squash --delete-branch

# 9. Update local develop
git checkout develop
git pull origin develop
```

---

## PR Guidelines

### Title Format
- `Fix: description` for bug fixes
- `Feature: description` for new features
- `Docs: description` for documentation
- `Perf: description` for performance improvements

### Description Template
```markdown
Fixes #N

## Changes
- Bullet point list of changes

## Testing
- How it was tested
- Which tests pass/added

## Notes
- Any important context
- Follow-up issues if needed
```

### Before Merging
- [ ] All tests pass
- [ ] Code reviewed (self-review for now)
- [ ] CHANGELOG.md updated
- [ ] No merge conflicts
- [ ] Squash merge to keep history clean

---

## Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation only
- `perf` - Performance improvement
- `refactor` - Code restructuring
- `test` - Adding/updating tests
- `chore` - Build/tooling changes

**Scopes:** `domain`, `core`, `ports`, `adapters`, `cli`, `deps`, `meta`

**Examples:**
```bash
feat(cli): add --format option to find command

Allows users to customize output format.

Fixes #42
```

```bash
fix(indexing): prevent duplicate chunks on re-index

Deletes old chunks for files before indexing new ones.

Fixes #13
```

---

## Quality Checklist

Before every commit:
- [ ] Tests pass: `uv run pytest`
- [ ] Linter passes: `uv run ruff check .`
- [ ] Type hints on all public functions
- [ ] Docstrings on public interfaces
- [ ] CHANGELOG.md updated
- [ ] No `core/` imports from `adapters/`
- [ ] Absolute paths (using `pathlib.Path`)

---

## Emergency Hotfix Process

For critical bugs in `main`:

```bash
# 1. Create hotfix branch from main
git checkout main
git pull origin main
git checkout -b hotfix/issue-N-description

# 2. Fix the bug
# ... work ...

# 3. Test thoroughly
uv run pytest

# 4. Update CHANGELOG with patch version
# Change version from X.Y.Z to X.Y.Z+1

# 5. Commit and PR to main
git commit -m "fix: critical bug description"
git push -u origin hotfix/issue-N-description
gh pr create --base main --title "Hotfix: description"

# 6. After merge, create tag
git checkout main
git pull origin main
git tag vX.Y.Z+1
git push origin vX.Y.Z+1

# 7. Back-merge to develop
git checkout develop
git merge main
git push origin develop
```

---

## Testing Strategy

### Test Levels
1. **Unit tests** - Pure functions, domain logic
2. **Integration tests** - Use cases with real adapters
3. **End-to-end tests** - CLI commands in temp directories

### Running Tests
```bash
# All tests
uv run pytest

# Verbose output
uv run pytest -v

# Specific test file
uv run pytest tests/unit/test_chunking.py

# With coverage
uv run pytest --cov=ember --cov-report=term-missing
```

### Writing Tests
- Test files mirror source structure: `tests/unit/core/test_indexing.py`
- Use fixtures for common setup
- Use temp directories for file operations
- Mock external dependencies (embedders, git, etc.)

---

## Documentation Maintenance

### What Lives Where

**`README.md`** - User-facing
- What is Ember?
- Installation
- Quick start
- Basic usage

**`CLAUDE.md`** - Maintainer context (simplified)
- Current state (1-2 sentences)
- Next milestone priorities
- Operational workflow reference
- Architecture quick reference

**`MAINTAINER_GUIDE.md`** (this file) - Operational procedures
- Branch strategy
- Release process
- Work patterns
- Quality standards

**`docs/ARCHITECTURE.md`** - Technical deep-dive
- Clean architecture explanation
- Layer responsibilities
- Design patterns used
- Dependency injection

**`docs/DEVELOPMENT.md`** - Contributor guide
- Setup instructions
- How to add features
- Testing guidelines
- Pull request process

**`CHANGELOG.md`** - Version history
- What changed in each version
- Migration notes if needed

---

## Common Scenarios

### Adding a New Feature
1. Create issue describing the feature
2. Assign to milestone (usually next version)
3. Create feature branch from `develop`
4. Implement with tests
5. Update CHANGELOG under "Unreleased"
6. PR to `develop`
7. Merge and close issue

### Fixing a Bug
1. Ensure bug is documented in an issue
2. Create fix branch from `develop`
3. Write failing test first (if possible)
4. Fix the bug
5. Verify test passes
6. Update CHANGELOG under "Unreleased"
7. PR to `develop` with "Fixes #N"

### Improving Documentation
1. Create docs branch from `develop`
2. Update relevant files
3. Check links and formatting
4. PR to `develop`
5. No CHANGELOG needed for minor doc tweaks

### Performance Optimization
1. Profile to identify bottleneck
2. Create perf branch from `develop`
3. Implement optimization
4. Benchmark before/after
5. Document results in PR and/or `docs/PERFORMANCE.md`
6. Update CHANGELOG under "Unreleased"
7. PR to `develop`

---

## Appendix: Useful Commands

### Git
```bash
git log --oneline -10              # Recent commits
git log --graph --oneline --all    # Branch visualization
git diff develop...main            # What's in develop but not main
```

### GitHub CLI
```bash
gh issue list --milestone "0.2.0"  # Issues for milestone
gh issue view 42                   # View issue details
gh pr list --state open            # Open PRs
gh pr checks                       # CI status for current PR
```

### Development
```bash
uv sync                            # Update dependencies
uv run pytest -x                   # Stop on first failure
uv run pytest -k test_name         # Run specific test
uv run ruff check . --fix          # Auto-fix linting issues
```

### Ember Testing
```bash
# Test in temp directory
cd /tmp
rm -rf ember-test
mkdir ember-test && cd ember-test
git init
uv run /path/to/ember/ember init
# ... test commands ...
```

---

**Last Updated:** 2025-10-19
**Version:** 1.0
