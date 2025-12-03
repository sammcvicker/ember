---
description: Default Ember development workflow - pick issue, implement, test, PR, merge
---

# Ember Default Development Workflow

You are working on the Ember project. Follow the complete development workflow from issue selection through PR merge.

## Workflow

Execute the following steps autonomously, only asking for user confirmation at major decision points:

### 1. Pick Next Issue

```bash
# Check milestone issues first (highest priority)
gh issue list --state open --milestone "1.3.0" --json number,title,labels

# Then check all open issues
gh issue list --state open --json number,title,labels --limit 20
```

**Priority Order:**
1. **Milestone issues** (#124-#129) - Active sprint, highest priority
2. **Tech debt Priority 1** (#185, #184, #180, #173, #183, #170) - Bugs and architecture violations
3. **Tech debt Priority 2** (#171, #172, #176, #179, #174, #182) - Complexity reduction
4. **Tech debt Priority 3** (#181, #177, #175, #178) - Nice to have improvements

Within each priority level: prefer bugs over enhancements, then lowest numbered issue.

- If unclear which issue to work on, ask the user
- See `CLAUDE.md` section "🔧 TECH DEBT BACKLOG" for full context on tech debt issues

### 2. Start Issue

- Fetch full issue details: `gh issue view <N> --json title,body,milestone,labels`
- Create feature branch from current branch: `git checkout -b feat/issue-N-short-description`
- Display:
  - Issue title and description
  - Acceptance criteria
  - Estimated effort
  - Any dependencies

### 3. Implement with TDD

- **Write tests first** - Create test files in `tests/` directory
- **Implement code** - Make tests pass
- **Follow clean architecture**:
  - No `adapters/` imports in `core/`
  - Use dependency injection
  - Type hints on all functions
  - Comprehensive docstrings
- **Run tests frequently**: `uv run pytest -v`
- **Check linter**: `uv run ruff check .` and auto-fix with `--fix`
- **Verify architecture**: Ensure core/ only depends on ports/, never adapters/

### 4. Commit Work

- Stage changes: `git add .`
- Create conventional commit with:
  - Proper commit message format
  - Reference to issue number
  - List of changes
  - Acceptance criteria checklist
  - Claude Code footer

### 5. Update Documentation

- Update `CHANGELOG.md` with changes (add to Unreleased section)
- Update `CLAUDE.md` current state if significant milestone reached
- Update any other relevant docs

### 6. Create Pull Request

- Push branch: `git push -u origin feat/issue-N-description`
- Create PR against `develop`:
  ```bash
  gh pr create --base develop --title "feat: <description>" --body "<summary>"
  ```
- PR body should include:
  - Summary of changes
  - Reference to issue: "Implements #N"
  - Acceptance criteria checklist
  - Test coverage info
  - Claude Code footer

### 7. Merge and Close

- Merge with squash: `gh pr merge <N> --squash --delete-branch`
- Switch back to develop: `git checkout develop && git pull`
- Verify issue is closed, if not: `gh issue close <N> --comment "Completed in PR #<N>"`

### 8. Report Completion

Report to the user:
- Issue number and title completed
- PR link
- Test coverage stats
- Next issue number
- Ask if they want to continue with next issue or stop

## Important Notes

- **Read CLAUDE.md first** to understand current project state
- **Follow the critical path** - issues are ordered with dependencies in mind
- **Don't skip steps** - tests, linting, documentation are all required
- **Commit frequently** during implementation (not just at the end)
- **Only stop for confirmation** when:
  - Unclear which issue to work on
  - Multiple valid implementation approaches exist
  - Encountering blocking errors
  - After completing the full workflow (ask about next issue)

## Quality Standards

Before moving to PR creation, verify:
- [ ] All tests pass: `uv run pytest`
- [ ] Linter passes: `uv run ruff check .`
- [ ] Coverage maintained (check with `pytest --cov`)
- [ ] Architecture principles followed (core/ only imports from ports/)
- [ ] All acceptance criteria met
- [ ] Documentation updated

**Known Test Issues (don't block on these):**
- 2 slow tests fail (daemon end-to-end) - tracked in #185
- 466 ResourceWarning about unclosed DB connections - tracked in #184
- Run `uv run pytest -m slow` separately to check slow tests

## Reference Documents

- `CLAUDE.md` - Current state, workflow guide, and **tech debt backlog**
- `MAINTAINER_GUIDE.md` - Detailed operational procedures
- `prd.md` - Product requirements and architecture
- `docs/decisions/` - Architecture Decision Records

**Tech Debt Context:** See CLAUDE.md "🔧 TECH DEBT BACKLOG" section for:
- 16 issues from Dec 2025 code quality audit
- Priority rankings (P1: bugs/arch, P2: complexity, P3: nice-to-have)
- Issue descriptions with code references

Ready to start the workflow!

