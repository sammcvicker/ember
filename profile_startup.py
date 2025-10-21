#!/usr/bin/env python3
"""Profile CLI startup time to identify bottlenecks."""

import time


def time_import(module_name: str) -> float:
    """Time how long it takes to import a module."""
    start = time.perf_counter()
    __import__(module_name)
    duration = time.perf_counter() - start
    return duration


print("Profiling ember CLI startup...")
print("=" * 60)

# Time individual heavy imports
modules_to_test = [
    "click",
    "rich.progress",
    "blake3",
    "ember.adapters.local_models.jina_embedder",
    "ember.adapters.parsers.tree_sitter_chunker",
    "ember.adapters.sqlite.chunk_repository",
    "ember.entrypoints.cli",
]

results = []
for module in modules_to_test:
    try:
        duration = time_import(module)
        results.append((module, duration))
        print(f"{module:50} {duration * 1000:>8.1f} ms")
    except ImportError as e:
        print(f"{module:50} FAILED: {e}")

print("=" * 60)
print(f"{'TOTAL':50} {sum(d for _, d in results) * 1000:>8.1f} ms")

# Now time the full CLI import
print("\nFull CLI module import:")
start = time.perf_counter()
duration = time.perf_counter() - start
print(f"{'ember.entrypoints.cli':50} {duration * 1000:>8.1f} ms")
