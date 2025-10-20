# Code Quality Review and Issue Generation

You are performing a comprehensive code quality review for the Ember codebase. Your goal is to **create GitHub issues** that identify technical debt, improvements, and quality concerns - NOT to fix them immediately.

## Phase 1: Cyclomatic Complexity Analysis

First, run a cyclomatic complexity analysis:

```bash
uv run radon cc ember/ -s -a
```

Analyze the output and note any functions/classes with:
- Complexity > 10 (moderate complexity, consider refactoring)
- Complexity > 15 (high complexity, should refactor)

## Phase 2: Codebase Exploration

Use **sub-agents** (Task tool with subagent_type=Explore) to systematically review different areas:

1. **Core logic** (`ember/core/`): Check use case implementations for:
   - Single Responsibility Principle violations
   - Complex business logic that needs simplification
   - Missing error handling or edge cases

2. **Adapters** (`ember/adapters/`): Review infrastructure code for:
   - Proper error handling and recovery
   - Resource cleanup (connections, file handles)
   - Performance bottlenecks
   - Configuration hardcoding

3. **Domain models** (`ember/domain/`): Check entities for:
   - Missing validation
   - Anemic domain models (too much logic elsewhere)
   - Value objects that could improve type safety

4. **Tests** (`tests/`): Review test coverage and quality:
   - Missing test cases for edge cases
   - Test brittleness or slow tests
   - Integration vs unit test balance

5. **CLI interface** (`ember/entrypoints/`): Check for:
   - User experience issues
   - Missing helpful error messages
   - Inconsistent command patterns

## Phase 3: Architectural Reflection

Consider the **principles from `prd.md` and `CLAUDE.md`**:
- Is the Clean Architecture dependency rule maintained?
- Are ports/adapters properly abstracted?
- Are there any leaky abstractions?
- Is dependency injection used consistently?

## Phase 4: Issue Creation

For each concern identified, create a GitHub issue using:

```bash
gh issue create --label "<appropriate-label>" --title "<clear title>" --body "<detailed description>"
```

### Issue Guidelines

**Labels to use:**
- `tech-debt` - Code that works but needs refactoring
- `enhancement` - New capability or improvement
- `bug` - Actual defects
- `architecture` - Structural or design improvements
- `performance` - Speed or resource optimization
- `dx` - Developer experience improvements
- `testing` - Test coverage or quality

**Issue format:**
```markdown
## Problem

[Clear description of what's wrong/could be better]

## Context

[Why this matters - impact on maintainability, performance, UX, etc.]

## Code Reference

`<file_path>:<line_number>`

```python
# Include relevant code snippet
# So context is preserved even if code moves
```

## Proposed Direction

[High-level approach or options to consider]

## Success Criteria

- [ ] Measurable outcome 1
- [ ] Measurable outcome 2
```

## Phase 5: Reflection and Prioritization

After creating issues:
1. Summarize what you found (categories, counts)
2. Suggest which issues are highest priority
3. Note any patterns (e.g., "error handling inconsistent across adapters")

## Important Constraints

- **DO NOT** attempt to fix issues during this review
- **DO** include code snippets in issues for context preservation
- **DO** be specific with file paths and line numbers
- **DO** be reflective about *why* current code is the way it is
- **DO** consider trade-offs (not everything needs changing)
- **AVOID** creating issues for style preferences if code follows existing patterns
- **PRIORITIZE** issues that impact:
  - Correctness and reliability
  - Performance at scale
  - Maintainability and tech debt
  - User experience

## Tools and Resources

- Use `radon cc` for complexity metrics
- Use `Grep` to find patterns across the codebase
- Use `Task` with Explore agent for systematic codebase crawling
- Reference `CLAUDE.md`, `prd.md`, and `docs/decisions/` for architectural principles
- Check `MAINTAINER_GUIDE.md` for quality standards

## Success Metrics

A successful review session produces:
- 5-15 well-defined, actionable issues
- Clear prioritization based on impact
- Preserved context (code snippets, line numbers)
- Reflection on architectural patterns and decisions
- A roadmap for improving code quality

---

**Remember:** The goal is to exit with a clear backlog of improvements, not to fix everything now. Be thorough, be reflective, and be specific.
