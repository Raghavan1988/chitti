# The spawn_agent tool: delegate a task to a fresh, depth-limited sub-agent.
"""Day 4 — subagent: delegation to a fresh agent with a clean context.

Concept: some tasks are self-contained and would only clutter the parent's
context. spawn_agent hands such a task to a child harness that starts empty,
cannot see this conversation, and reports back only its final answer — context
isolation as a tool. A depth limit stops an agent from recursing forever.

Design rule: the child is ephemeral. It shares the workspace and policy but not
the message history, so delegation buys focus without leaking the parent's state.
"""

from .tools import tool


def subagent_tool(make_harness, depth=0, max_depth=2):
    """Build the spawn_agent tool, refusing to recurse past max_depth.

    make_harness(child_depth) constructs a fresh child harness over the same
    workspace; the tool runs the delegated task on it and returns the child's
    final report. At or past the depth limit it refuses so the agent does the
    work inline instead of spawning an unbounded tower of sub-agents.
    """
    @tool(
        "Delegate a self-contained task to a fresh sub-agent with its own clean "
        "context. The child cannot see this conversation; it returns only its "
        "final report. Use it to keep focused work out of your own context.",
        task="a complete, self-contained description of what the sub-agent must do",
    )
    def spawn_agent(task):
        if depth >= max_depth:
            return "ERROR: sub-agent depth limit reached; do this task yourself"
        child = make_harness(depth + 1)
        return child.run(task)

    return spawn_agent
