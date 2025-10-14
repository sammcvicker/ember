# ADR-001: Clean Architecture with Ports and Adapters

**Date:** 2025-10-14
**Status:** Accepted
**Deciders:** Sam @ KamiwazaAI
**References:** PRD §3 (Architecture)

## Context

Ember needs to support multiple potential implementations:
- Different embedding models (local vs remote, different formats)
- Different vector storage backends (sqlite-vss vs FAISS)
- Different VCS systems (git via subprocess vs libgit2)
- Potential future HTTP server or MCP integration

We need an architecture that:
- Keeps business logic independent of infrastructure
- Makes components easy to test in isolation
- Allows swapping implementations without touching core logic
- Maintains clarity as the codebase grows

## Decision

Adopt **Clean Architecture** with explicit **Ports and Adapters** pattern:

### Layer Structure
```
ember/
  app/                 # Presentation layer - CLI DTOs, no business logic
  core/                # Business logic - use cases and services
  domain/              # Pure domain entities and value objects
  ports/               # Abstract interfaces (using Protocol)
  adapters/            # Infrastructure implementations
  shared/              # Cross-cutting concerns (errors, logging)
  entrypoints/         # Application entry points (CLI, HTTP)
```

### Key Rules
1. **Dependency Direction**: `entrypoints → app → core → ports ← adapters`
   - `core/` depends ONLY on `ports/`, never on `adapters/`
   - Adapters implement port protocols
   - Dependencies injected via constructors

2. **Use Protocols, not ABC**: Structural typing for ports
   - More Pythonic
   - Easier to test with duck typing
   - No inheritance required

3. **Pure Domain**: `domain/` has no external dependencies
   - Just dataclasses, enums, value objects
   - Business rules at entity level

4. **Use Cases**: Each command is a use case in `core/`
   - `InitUseCase`, `SyncUseCase`, `FindUseCase`
   - Orchestrates domain logic
   - Returns domain types or DTOs

### Example Flow
```
CLI command → UseCase(injected_ports) → Domain logic → Port interface → Adapter impl
```

## Consequences

### Positive
- ✅ Can swap sqlite-vss for FAISS by changing adapter wiring
- ✅ Can test business logic without database
- ✅ Clear separation of concerns
- ✅ Easy to understand where code belongs
- ✅ Follows SOLID principles (especially D - dependency inversion)
- ✅ Adapters can be developed independently

### Negative
- ⚠️ More files and indirection than flat structure
- ⚠️ Requires discipline to maintain layer boundaries
- ⚠️ Initial setup time for folder structure and ports

### Mitigations
- Use type checking (pyright) to enforce layer boundaries
- Document layer rules in CLAUDE.md
- Review imports in pull requests
- Keep adapters thin (minimal logic)

## Alternatives Considered

### Flat MVC structure
- Simpler initially
- Hard to swap implementations later
- Business logic tends to leak into controllers

### Django-style apps
- More familiar to some developers
- Couples to web framework patterns
- Overkill for CLI tool

### Pure functional with modules
- Very testable
- Harder to manage state and dependencies
- Less familiar Python pattern

## References

- Clean Architecture by Robert C. Martin
- Ports and Adapters (Hexagonal Architecture) by Alistair Cockburn
- PRD §3: Architecture (Clean + SOLID)
- PRD §17: Implementation Sketches (port definitions)

## Notes

This decision aligns with the PRD's explicit requirement for:
- "Clean Architecture"
- "SOLID principles"
- "Replaceable infra"
- Future extensibility (PRD v0.3+: HTTP server, pluggable strategies)

The extra structure cost is worth it for a tool meant to grow and support multiple backends.
