"""Day 1 demo — the smallest complete agent: one tool, one loop, one answer.

Concept: a tool is just an object with two attributes — .spec, the schema the
model sees, and .run, the code it triggers. The loop needs nothing more. This
demo hand-writes both so the shape is visible before day 2's decorators hide
it, then runs a task that forces exactly one tool call and one text answer.

Design rule: the schema is the contract. `count` is declared a string because
that is how Gemini reliably returns function arguments here; .run coerces it.
"""

import random
import sys

sys.path.insert(0, __file__.rsplit("/demos/", 1)[0])

from odysseus.loop import run_loop  # noqa: E402
from odysseus.provider import DEFAULT_MODEL  # noqa: E402


class RollDice:
    """Roll `count` six-sided dice and report the individual results."""

    spec = {"schema": {
        "name": "roll_dice",
        "description": "Roll count six-sided dice",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "string", "description": "How many dice"},
            },
            "required": ["count"],
        },
    }}

    def run(self, count):
        """Return the list of rolls; coerce the string arg to an int first."""
        rolls = [random.randint(1, 6) for _ in range(int(count))]
        return f"rolls={rolls} total={sum(rolls)}"


def on_event(kind, payload):
    """Print a readable trace of the run as it happens."""
    if kind == "assistant":
        if payload["text"]:
            print(f"[assistant] {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"[assistant] -> tool {call['name']}({call['args']})")
    elif kind == "tool_end":
        print(f"[tool] {payload['call']['name']} => {payload['result']}")


def always_allow(call):
    """A before_tool that permits every call (returns None to allow)."""
    return None


def main():
    tools = {"roll_dice": RollDice()}
    messages = [{"role": "user", "text": "Roll 3 dice and tell me whether the total beats 10"}]
    answer = run_loop(
        DEFAULT_MODEL,
        "You are a helpful assistant. Use tools when they apply.",
        messages, tools, on_event, always_allow,
    )
    print(f"\nFINAL: {answer}")


if __name__ == "__main__":
    main()
