#!/usr/bin/env python3
"""Profile what gets imported when running the installed ember command.

This mimics what happens when you run 'ember --version' after pipx install.
"""

import time


def profile_imports():
    """Profile imports as they happen."""
    import_times = {}
    original_import = __builtins__.__import__

    def timed_import(name, *args, **kwargs):
        start = time.perf_counter()
        result = original_import(name, *args, **kwargs)
        duration = time.perf_counter() - start

        # Only track top-level imports (not sub-imports)
        if duration > 0.001 and name not in import_times:  # > 1ms
            import_times[name] = duration

        return result

    __builtins__.__import__ = timed_import

    # Now import and run the CLI main function (simulating installed command)
    print("Simulating: ember --version")
    print("=" * 60)

    total_start = time.perf_counter()

    # This is what happens when you run the installed 'ember' command

    # Restore original import
    __builtins__.__import__ = original_import

    total_duration = time.perf_counter() - total_start

    # Sort by duration
    sorted_imports = sorted(import_times.items(), key=lambda x: x[1], reverse=True)

    print("\nTop imports by time:")
    print("-" * 60)
    for module, duration in sorted_imports[:20]:
        print(f"{module:50} {duration * 1000:>8.1f} ms")

    print("=" * 60)
    print(f"{'Total import time':50} {total_duration * 1000:>8.1f} ms")

    return import_times, total_duration


if __name__ == "__main__":
    import_times, total = profile_imports()

    print(f"\nTotal modules imported: {len(import_times)}")
    print(f"Heavy modules (>100ms): {sum(1 for t in import_times.values() if t > 0.1)}")
