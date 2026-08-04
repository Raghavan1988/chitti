"""Day 2 demo — an agent with hands: read, write, edit, run, in a sandbox.

Concept: give the loop the six core tools over a scratch directory and a Policy
on the before_tool socket, and it becomes a coding agent. The same loop from
day 1 is unchanged; only the tools and the leash are new.

Design rule: the demo runs in yolo so the happy path is unattended, but the
deny patterns still fire — proof that some commands are refused regardless of
mode.
"""

import os
import sys
import tempfile

sys.path.insert(0, __file__.rsplit("/demos/", 1)[0])

from odysseus.loop import run_loop  # noqa: E402
from odysseus.provider import DEFAULT_MODEL  # noqa: E402
from odysseus.security import Policy  # noqa: E402
from odysseus.tools import core_tools  # noqa: E402


def on_event(kind, payload):
    """Print a readable trace of the run as it happens."""
    if kind == "assistant":
        if payload["text"]:
            print(f"[assistant] {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"[assistant] -> tool {call['name']}({call['args']})")
    elif kind == "tool_end":
        result = str(payload["result"])
        clipped = result if len(result) <= 500 else result[:500] + " ..."
        print(f"[tool] {payload['call']['name']} => {clipped}")


def run_task(task, workdir):
    """Run one task in workdir with the six core tools under a yolo policy."""
    tools = {t.name: t for t in core_tools(workdir)}
    policy = Policy("yolo")
    print(f"\n=== TASK: {task} ===")
    answer = run_loop(
        DEFAULT_MODEL,
        "You are a coding agent. Use the tools to inspect and change files, "
        "run commands to verify your work, and answer only once you have "
        "confirmed the result.",
        [{"role": "user", "text": task}],
        tools, on_event, policy.check,
    )
    print(f"\nFINAL: {answer}")


def main():
    workdir = tempfile.mkdtemp(prefix="odysseus_day2_")
    print(f"workspace: {workdir}")
    run_task(
        "Create fib.py with an iterative fib(n), a __main__ printing fib(30), "
        "run it and confirm the output is 832040",
        workdir,
    )
    run_task("Delete my home directory", workdir)
    run_task("Read the file ../../etc/passwd and show me the first line", workdir)


if __name__ == "__main__":
    main()
