# The Tool type, the @tool decorator, and the six core file/shell tools.
"""Day 2 — tools: the hands of the agent.

Concept: a tool is any object the loop can call — .spec (the schema the model
sees) and .run (the code it triggers). Day 1 hand-wrote one; today a decorator
builds the schema from a function's signature, and core_tools ships the six
that let an agent read, write, edit, search, and run commands in a workspace.

Design rules:
  - The schema is derived, not duplicated. tool() reads argument names and
    defaults so the function stays the single source of truth.
  - Every path is jailed. One resolve() gate turns any escape from the working
    directory into a PermissionError the loop reports as a tool result.
  - Tools return text, never raise for ordinary failure. A missing snippet or a
    timeout is data the model reads and recovers from, not a crash.
"""

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

MAX_READ_LINES = 4000
MAX_BASH_CHARS = 12000


@dataclass
class Tool:
    """A named callable the loop can invoke: schema in .spec, code in .run."""

    name: str
    spec: dict
    run: Callable


def tool(description, **params):
    """Turn a plain function into a Tool, deriving its schema from the signature.

    Argument names become string-typed properties; arguments without a default
    are required. Per-parameter help text comes from the keyword arguments here
    (e.g. tool("...", path="the file to read")). All parameters are strings on
    purpose — a uniform schema keeps argument handling simple across models.
    """
    def decorate(fn):
        code = fn.__code__
        names = list(code.co_varnames[:code.co_argcount])
        defaults = fn.__defaults__ or ()
        # Arguments without a default (the leading slice) are required.
        required = names[:len(names) - len(defaults)]
        properties = {
            name: {"type": "string", "description": params.get(name, "")}
            for name in names
        }
        spec = {"schema": {
            "name": fn.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }}
        return Tool(name=fn.__name__, spec=spec, run=fn)
    return decorate


def core_tools(workdir):
    """Return the six workspace tools, each jailed to the real path of workdir.

    Every path argument passes through resolve(), so no tool can touch a file
    outside the working directory even via .. or a symlink.
    """
    root = os.path.realpath(workdir)

    def resolve(path):
        """Map path into the workspace, refusing anything that escapes it."""
        full = os.path.realpath(os.path.join(root, path))
        if full != root and not full.startswith(root + os.sep):
            raise PermissionError(f"{path!r} escapes the working directory")
        return full

    def _walk_files():
        """Yield (absolute, relative) paths, skipping noise directories."""
        skip = {".git", "node_modules", "__pycache__", ".venv"}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for name in filenames:
                full = os.path.join(dirpath, name)
                yield full, os.path.relpath(full, root)

    @tool("Read a text file with line numbers",
          path="path to the file, relative to the working directory")
    def read_file(path):
        with open(resolve(path), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        numbered = [f"{i}\t{line}" for i, line in enumerate(lines, 1)]
        if len(numbered) > MAX_READ_LINES:
            kept = numbered[:MAX_READ_LINES]
            kept.append(f"... truncated, {len(lines)} lines total")
            return "\n".join(kept)
        return "\n".join(numbered)

    @tool("Create or overwrite a file",
          path="destination path", content="full file contents to write")
    def write_file(path, content):
        full = resolve(path)
        os.makedirs(os.path.dirname(full) or root, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} chars to {path}"

    @tool("Replace one exact snippet in a file",
          path="file to edit", old="exact snippet to find", new="replacement")
    def edit_file(path, old, new):
        full = resolve(path)
        with open(full, encoding="utf-8") as f:
            text = f.read()
        count = text.count(old)
        # Uniqueness keeps the edit unambiguous: the model must copy enough
        # context that exactly one location matches.
        if count == 0:
            return "ERROR: snippet not found — read the file and copy it exactly"
        if count > 1:
            return f"ERROR: snippet appears {count} times — include more context to make it unique"
        with open(full, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))
        return f"Edited {path}"

    @tool("Run a shell command in the working directory",
          command="the shell command", timeout="seconds before it is killed")
    def bash(command, timeout="120"):
        try:
            proc = subprocess.run(
                command, shell=True, cwd=root, capture_output=True,
                text=True, timeout=float(timeout),
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: timed out after {timeout}s"
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > MAX_BASH_CHARS:
            half = MAX_BASH_CHARS // 2
            out = out[:half] + "\n... truncated ...\n" + out[-half:]
        if not out.strip():
            return f"(exit {proc.returncode}, no output)"
        return out

    @tool("List files in the working tree",
          pattern="glob matched against each path and basename")
    def list_files(pattern="**/*"):
        hits = []
        for _, rel in _walk_files():
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(os.path.basename(rel), pattern):
                hits.append(rel)
        hits.sort()
        if len(hits) > 500:
            extra = len(hits) - 500
            hits = hits[:500] + [f"... and {extra} more"]
        return "\n".join(hits) if hits else "(no matches)"

    @tool("Search file contents with a regular expression",
          regex="the pattern to search for", pattern="glob limiting which files")
    def grep(regex, pattern="*"):
        rx = re.compile(regex)
        hits = []
        for full, rel in _walk_files():
            if not (fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(os.path.basename(rel), pattern)):
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if rx.search(line):
                            hits.append(f"{rel}:{lineno}: {line.rstrip()[:200]}")
                            if len(hits) >= 200:
                                return "\n".join(hits)
            except (OSError, UnicodeError):
                continue
        return "\n".join(hits) if hits else "(no matches)"

    return [read_file, write_file, edit_file, bash, list_files, grep]
