"""Entry point for running daemon server as a module.

Usage:
    python -m ember.adapters.daemon.server [options]
"""

from ember.adapters.daemon.server import main

if __name__ == "__main__":
    main()
