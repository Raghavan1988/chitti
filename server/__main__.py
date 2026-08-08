# python3 -m server
"""Entry point: start the Chitti mobile harness HTTP server."""

import sys
from pathlib import Path

# Allow `python3 -m server` from repo root without installing packages.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server.app import serve_forever  # noqa: E402
from server.config import config  # noqa: E402


def main():
    config.ensure_workdir()
    serve_forever()


if __name__ == "__main__":
    main()
