# The Policy and deny rules that gate every tool call before it runs.
"""Day 2 — security: the policy the loop consults before every tool.

Concept: the loop already has a before_tool socket. This file fills it with a
Policy that decides — per call — allow, block, or ask a human. The agent gains
hands today; this is the leash that keeps them inside what the operator agreed
to run.

Design rules:
  - Some commands are never negotiable. DENY_PATTERNS are refused in every mode,
    even yolo, because no legitimate agent turn needs to wipe a home directory.
  - Mode is a spectrum, not a switch. read-only observes, safe asks, yolo trusts
    — one dimension the operator dials to fit the task.
  - Blocking is data, not death. check() returns a reason string; the loop turns
    it into a "BLOCKED: ..." tool result the model reads and works around.
"""

import re

READ_TOOLS = {"read_file", "list_files", "grep"}

# Commands refused in every mode: catastrophic, irreversible, or exfiltrating.
DENY_PATTERNS = [
    r"\brm\s+-rf?\s+(/|~|\$HOME)",       # wiping root, home, or $HOME
    r"\bsudo\b",                          # privilege escalation
    r"\bmkfs\b",                          # formatting a filesystem
    r"\bdd\s+if=",                        # raw disk imaging
    r"curl\s+.*\|\s*sh",                  # curl | sh remote execution
    r"git\s+push\s+.*--force",            # force-pushing over history
    r">\s*/dev/sd",                       # redirecting onto a raw disk
]


class Policy:
    """Decide allow / block / ask for each tool call, per the chosen mode."""

    def __init__(self, mode="safe", approver=None):
        """mode is 'read-only', 'safe', or 'yolo'; approver(call, reason) -> bool
        is asked in safe mode and defaults to refusing when none is given."""
        self.mode = mode
        self.approver = approver or (lambda call, reason: False)

    def check(self, call):
        """Return None to allow the call, or a reason string to block it.

        Order matters: a denied bash command loses in every mode, then reads and
        yolo pass freely, read-only stops everything else, and safe defers to the
        approver — a no answer becomes the block reason.
        """
        name, args = call["name"], call.get("args", {})

        if name == "bash":
            command = args.get("command", "")
            for pattern in DENY_PATTERNS:
                if re.search(pattern, command):
                    return f"command matches a denied pattern: {pattern}"

        if name in READ_TOOLS or self.mode == "yolo":
            return None

        if self.mode == "read-only":
            return "read-only mode: only read_file, list_files, grep are allowed"

        # safe mode: a write or command runs only with explicit approval.
        if self.approver(call, f"run {name}"):
            return None
        return f"not approved by policy in safe mode: {name}"
