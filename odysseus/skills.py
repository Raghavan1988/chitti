"""Day 3 — skills: procedural knowledge the agent loads on demand.

Concept: a skill is a folder under skills/<name>/ holding a SKILL.md — a written
procedure the agent can pull in when a task calls for it. The catalog advertises
what exists in the system prompt; the use_skill tool (wired by the harness)
reads the full text only when relevant, so knowledge scales without bloating
every prompt.

Design rule: skills are files, not code. Anyone can add one by dropping a
SKILL.md in place — no registration, no import, no restart.
"""

import os

SKILLS_DIR = "skills"


def _description(text):
    """Pull a `description:` value from a SKILL.md front-matter line, if any."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def catalog(workdir):
    """Map each skill name to its description and SKILL.md path.

    Scans workdir/skills/<name>/SKILL.md; a skill with no description line is
    still listed with an empty one.
    """
    base = os.path.join(os.path.realpath(workdir), SKILLS_DIR)
    found = {}
    if not os.path.isdir(base):
        return found
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "SKILL.md")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                found[name] = {"description": _description(f.read()), "path": path}
    return found


def catalog_prompt(workdir):
    """Render the skill catalog as a system-prompt section, or "" when empty."""
    found = catalog(workdir)
    if not found:
        return ""
    lines = ["Skills available (load one with the use_skill tool when relevant):"]
    for name, meta in found.items():
        lines.append(f"- {name}: {meta['description']}")
    return "\n".join(lines)


def read_skill(workdir, name):
    """Return the full SKILL.md text for `name`, or an error naming what exists."""
    found = catalog(workdir)
    if name not in found:
        available = ", ".join(found) or "(none)"
        return f"ERROR: no skill named {name}. Available: {available}"
    with open(found[name]["path"], encoding="utf-8") as f:
        return f.read()
