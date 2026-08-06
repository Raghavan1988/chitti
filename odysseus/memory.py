# The base system prompt and durable ODYSSEUS.md project memory.
"""Day 3 — memory: who the agent is, and what it must not forget.

Concept: two jobs live here. The base system prompt gives Odysseus its
character — act, don't narrate; verify before claiming done. And ODYSSEUS.md
gives it durable memory: a note written on one run is read back into the system
prompt on every future run over the same directory, surviving a fresh
conversation with no history at all.

Design rules:
  - The prompt is a contract, not a mood. Each line is a behavior the loop and
    tools actually reward — inspect first, prefer edit_file, never repeat a
    failing call unchanged.
  - Memory is a plain file. ODYSSEUS.md is human-readable and lives in the
    workspace, so the operator can read, edit, or delete what the agent knows.
"""

import platform

MEMORY_FILE = "ODYSSEUS.md"

BASE_PROMPT = (
    "You are Odysseus, a small sharp coding agent working inside one directory "
    "with the tools provided. Act, don't narrate — reach for a tool instead of "
    "describing what you would do. Inspect before assuming: read files and list "
    "the tree before you change anything. Prefer edit_file for small changes "
    "over rewriting a whole file. After building, verify by running or "
    "re-reading — never claim success you have not checked. Never repeat a "
    "failing call unchanged; change something or change approach. When the task "
    "is complete, reply with a short summary and stop calling tools."
)


def build_system_prompt(workdir, extra=""):
    """Assemble the system prompt: base character, environment, memory, extras.

    Adds a line naming the platform and the real working directory, folds in
    workdir/ODYSSEUS.md as a "Project memory" section when it exists, and
    appends `extra` (e.g. a skills catalog) when non-empty. Sections are joined
    by blank lines.
    """
    import os

    root = os.path.realpath(workdir)
    sections = [
        BASE_PROMPT,
        f"Platform: {platform.system()}. Working directory: {root}",
    ]

    memory_path = os.path.join(root, MEMORY_FILE)
    if os.path.exists(memory_path):
        with open(memory_path, encoding="utf-8") as f:
            sections.append(f"Project memory ({MEMORY_FILE}):\n{f.read().strip()}")

    if extra:
        sections.append(extra)

    return "\n\n".join(sections)


def remember(workdir, note):
    """Append a note to ODYSSEUS.md so it survives into future conversations."""
    import os

    path = os.path.join(os.path.realpath(workdir), MEMORY_FILE)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- {note}\n")
    return "Remembered in ODYSSEUS.md"
