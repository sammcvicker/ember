---
description: Default Ember development workflow - pick issue, implement, test, PR, merge
---

# Ember Default Development Workflow

You are working on the Ember project. Follow the complete development workflow from issue selection through PR merge.

## Workflow

Execute the following steps autonomously, only asking for user confirmation at major decision points:

### 1. Pick Next Issue

```bash
# Check for open issues
gh issue list --state open --json number,title,labels --limit 20
```

**Priority Order:**
1. **Bug fixes** - Issues labeled `bug`
2. **Enhancements** - Issues labeled `enhancement`
3. **Tech debt** - Issues labeled `tech-debt`

Within each priority level: prefer lowest numbered issue.

- If no open issues exist, inform the user and ask what they'd like to work on
- If unclear which issue to work on, ask the user

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
- Next issue number (if any)
- Ask if they want to continue with next issue or stop

## Important Notes

- **Read CLAUDE.md first** to understand current project state
- **Don't skip steps** - tests, linting, documentation are all required
- **Commit frequently** during implementation (not just at the end)
- **Only stop for confirmation** when:
  - No open issues exist
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

## Reference Documents

- `CLAUDE.md` - Current state and workflow guide
- `MAINTAINER_GUIDE.md` - Detailed operational procedures
- `prd.md` - Product requirements and architecture
- `docs/decisions/` - Architecture Decision Records

Ready to start the workflow!
