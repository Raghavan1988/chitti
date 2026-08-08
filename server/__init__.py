# Chitti mobile harness server: HTTP API over an Odysseus-shaped agent loop.
"""Server package for the iPhone harness.

The phone is a rich client (chat, voice, approvals). This package is the brain:
sessions, tools, policy, and a streaming event API. Run with:

    python3 -m server
"""

__all__ = ["create_app", "config"]
