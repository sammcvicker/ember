#!/usr/bin/env python3
"""Test daemon performance vs direct mode."""

import time

from ember.adapters.daemon.client import DaemonEmbedderClient
from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder


def time_embeddings(embedder, name: str, num_runs: int = 3):
    """Time embedding performance."""
    texts = [
        "def authenticate(user: str, password: str) -> bool:",
        "class UserRepository:",
        "async def fetch_data(id: int):",
    ]

    times = []
    for i in range(num_runs):
        start = time.perf_counter()
        _ = embedder.embed_texts(texts)  # Result not used, just timing
        duration = time.perf_counter() - start
        times.append(duration)
        print(f"  Run {i+1}: {duration*1000:.1f}ms")

    avg_time = sum(times) / len(times)
    print(f"  Average: {avg_time*1000:.1f}ms\n")
    return avg_time


print("=" * 70)
print("DAEMON PERFORMANCE TEST")
print("=" * 70)

# Test 1: Daemon mode (model already loaded)
print("\n1. DAEMON MODE (model pre-loaded)")
print("-" * 70)
daemon_client = DaemonEmbedderClient(fallback=False)
daemon_time = time_embeddings(daemon_client, "Daemon")

# Test 2: Direct mode (model loads on first call)
print("2. DIRECT MODE (cold start)")
print("-" * 70)
direct_embedder = JinaCodeEmbedder()
direct_time = time_embeddings(direct_embedder, "Direct")

# Summary
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Daemon mode:  {daemon_time*1000:.1f}ms")
print(f"  Direct mode:  {direct_time*1000:.1f}ms")
print(f"  Speedup:      {direct_time/daemon_time:.1f}x faster")
print(f"\n  ✓ Daemon eliminates {(direct_time - daemon_time)*1000:.0f}ms of overhead!")
print("=" * 70)
