#!/usr/bin/env python3
"""Profile model loading time to identify bottlenecks in issue #46.

This script measures:
1. Import time for heavy dependencies
2. Model initialization time
3. First embedding time
4. Subsequent embedding time
5. End-to-end search time
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def time_it(label: str, fn):
    """Time a function and print results."""
    start = time.perf_counter()
    result = fn()
    duration = time.perf_counter() - start
    print(f"  {label:45} {duration * 1000:>8.1f} ms")
    return result, duration


print("=" * 70)
print("PROFILING MODEL LOADING PERFORMANCE (Issue #46)")
print("=" * 70)

# Phase 1: Import time
print("\n1. IMPORT TIME")
print("-" * 70)

total_import_time = 0

def import_sentence_transformers():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer

st_class, t = time_it("sentence_transformers import", import_sentence_transformers)
total_import_time += t

def import_torch():
    import torch
    return torch

torch_module, t = time_it("torch import", import_torch)
total_import_time += t

def import_jina_embedder():
    from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
    return JinaCodeEmbedder

embedder_class, t = time_it("JinaCodeEmbedder import", import_jina_embedder)
total_import_time += t

print(f"  {'TOTAL IMPORT TIME':45} {total_import_time * 1000:>8.1f} ms")

# Phase 2: Model loading
print("\n2. MODEL LOADING")
print("-" * 70)

embedder = embedder_class()
print("  Embedder instance created (no model loaded yet)")

def load_model():
    return embedder._ensure_model_loaded()

_, model_load_time = time_it("Model loading (_ensure_model_loaded)", load_model)

# Phase 3: Embedding time
print("\n3. EMBEDDING PERFORMANCE")
print("-" * 70)

test_texts = [
    "def authenticate(username: str, password: str) -> bool:",
    "class UserRepository:",
    "async def fetch_user_data(user_id: int):",
]

def first_embed():
    return embedder.embed_texts(test_texts)

embeddings1, t = time_it("First embed_texts() call (3 texts)", first_embed)

def second_embed():
    return embedder.embed_texts(test_texts)

embeddings2, t = time_it("Second embed_texts() call (cached model)", second_embed)

# Phase 4: End-to-end timing
print("\n4. SIMULATED SEARCH COMMAND")
print("-" * 70)

def simulate_fresh_search():
    """Simulate what happens on 'ember find' command."""
    # This is what happens now: fresh embedder instance each time
    fresh_embedder = embedder_class()
    # Model loads on first use
    _ = fresh_embedder.embed_texts(["authentication"])
    return fresh_embedder

_, search_time = time_it("Fresh embedder + first search", simulate_fresh_search)

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Total imports:                              {total_import_time * 1000:>8.1f} ms")
print(f"  Model loading (SentenceTransformer init):   {model_load_time * 1000:>8.1f} ms")
print("  First embedding:                            (included in model load)")
print(f"  End-to-end 'ember find' simulation:         {search_time * 1000:>8.1f} ms")
print()
print("  🎯 TARGET: <500ms (ideal: <200ms)")
print(f"  📊 CURRENT: {search_time * 1000:.0f}ms")
print(f"  ⚠️  GAP: {(search_time * 1000) - 200:.0f}ms slower than ideal")
print()
print("BOTTLENECK:")
print(f"  Model loading is the primary issue: {model_load_time * 1000:.0f}ms")
print("  This happens on EVERY 'ember find' command currently.")
print("=" * 70)
