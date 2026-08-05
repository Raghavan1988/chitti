"""Day 3 demo — context, memory, and skills, on the same day-1 loop.

Concept: three seams light up at once. compact() rides the before_turn socket to
keep a long run inside a token budget; build_system_prompt folds ODYSSEUS.md
into the prompt so a fact learned once survives a fresh conversation; and a
use_skill tool pulls a SKILL.md in on demand to change behavior with no code
change. The loop itself is untouched from day 1.

Design rule: the demo builds the system prompt fresh for every task, so
scenario 2 genuinely proves durability — the second agent shares no message
history with the first, only the file on disk.
"""

import os
import sys
import tempfile

sys.path.insert(0, __file__.rsplit("/demos/", 1)[0])

from odysseus import context, memory, skills  # noqa: E402
from odysseus.loop import run_loop  # noqa: E402
from odysseus.provider import DEFAULT_MODEL  # noqa: E402
from odysseus.security import Policy  # noqa: E402
from odysseus.tools import core_tools, tool  # noqa: E402

BUDGET_TOKENS = 1500


def on_event(kind, payload):
    """Print a readable trace, flagging when compaction fires between turns."""
    if kind == "assistant":
        if payload["text"]:
            print(f"[assistant] {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"[assistant] -> tool {call['name']}({call['args']})")
    elif kind == "tool_end":
        result = str(payload["result"])
        clipped = result if len(result) <= 300 else result[:300] + " ..."
        print(f"[tool] {payload['call']['name']} => {clipped}")


def build_tools(workdir):
    """Core tools plus a use_skill tool that reads a SKILL.md on demand."""
    tools = {t.name: t for t in core_tools(workdir)}

    @tool("Load a skill's full instructions by name", name="the skill to load")
    def use_skill(name):
        return skills.read_skill(workdir, name)

    tools[use_skill.name] = use_skill
    return tools


def run_task(task, workdir, compacting=False):
    """Run one task with a fresh, memory- and skill-aware system prompt."""
    tools = build_tools(workdir)
    policy = Policy("yolo")
    system = memory.build_system_prompt(workdir, extra=skills.catalog_prompt(workdir))
    before_turn = None
    if compacting:
        # The day-3 wiring: compaction rides the before_turn socket the loop
        # already threads, folding old turns into a summary within budget.
        before_turn = lambda msgs: context.compact(DEFAULT_MODEL, msgs, BUDGET_TOKENS)

    print(f"\n=== TASK: {task} ===")
    answer = run_loop(
        DEFAULT_MODEL, system, [{"role": "user", "text": task}],
        tools, on_event, policy.check, before_turn=before_turn,
    )
    print(f"\nFINAL: {answer}")
    return answer


def scenario_compaction(workdir):
    """(1) A long, repetitive task that must trip the token budget mid-run."""
    run_task(
        "Create five files one.txt through five.txt, each with 20 lines of the "
        "word ping, one write_file at a time with a read back after each; then "
        "MANIFEST.md listing each file and its line count verified with wc -l",
        workdir, compacting=True,
    )


def scenario_memory(workdir):
    """(2) Remember a fact, then answer about it from a fresh conversation."""
    print("\n=== remember a fact, then start a brand-new conversation ===")
    print(memory.remember(workdir, "The project ships as 'Odysseus 1.0' on 2026-09-01."))
    run_task("What is the project's ship name and date? Answer from memory.", workdir)


def scenario_skill(workdir):
    """(3) A skill that changes voice with zero code changes."""
    skill_dir = os.path.join(workdir, "skills", "brand-voice")
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: Write all prose in exaggerated pirate speak.\n---\n\n"
                "# Brand voice\n\nEvery sentence you write for the user must be in "
                "loud pirate speak: 'Arrr', 'matey', 'ye', 'the seven seas'. Never "
                "break character.\n")
    run_task(
        "Load the brand-voice skill, then write a two-sentence welcome message "
        "for our website. Do not write or change any files.",
        workdir,
    )


def main():
    workdir = tempfile.mkdtemp(prefix="odysseus_day3_")
    print(f"workspace: {workdir}")
    scenario_compaction(workdir)
    scenario_memory(workdir)
    scenario_skill(workdir)


if __name__ == "__main__":
    main()
