# Enable `python3 -m odysseus`, deferring to the CLI entry point.
"""Day 4 — the module entry point: `python3 -m odysseus` runs the CLI."""

from .cli import main

if __name__ == "__main__":
    main()
