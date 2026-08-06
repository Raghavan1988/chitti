# The Harness class: composes the whole week into one runnable agent.
"""Day 4 — harness: the object that assembles Odysseus into a working agent.

Concept: every earlier day built one organ — the provider, the loop, tools, the
policy, context, memory, skills, sessions, sub-agents. The Harness wires them
into a single class you construct and call. run(task) drives the loop with the
policy on the tool socket and compaction on the turn socket, persisting every
message as it lands so the run survives a crash.

Design rules:
  - Keep our message reference in sync. compaction may replace the list; because
    the harness owns the before_turn hook, it re-binds self.messages there so
    persistence and resume always see the live conversation.
  - Children never persist. A sub-agent runs with persist=False so its transcript
    can never masquerade as the newest session and hijack --resume.
"""

import os

from . import context, memory, provider, session, skills
from .loop import run_loop
from .security import Policy
from .subagent import subagent_tool
from .tools import Tool, core_tools, tool


class Harness:
    """A fully wired Odysseus agent over one working directory."""

    def __init__(self, workdir=".", model=None, policy=None, extra_tools=None,
                 system_extra="", on_event=None, budget_tokens=600_000,
                 max_turns=120, session_path=None, enable_subagents=True,
                 persist=True, _depth=0):
        """Compose the tools, prompt, and policy for a runnable agent.

        Defaults come from the environment where sensible: model from
        ODYSSEUS_MODEL then the provider default, policy from a permissive yolo.
        The tool set is core_tools plus remember, use_skill (when skills exist),
        and spawn_agent (when sub-agents are enabled).
        """
        self.workdir = os.path.realpath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.model = model or os.environ.get("ODYSSEUS_MODEL") or provider.DEFAULT_MODEL
        self.policy = policy or Policy("yolo")
        self.budget_tokens = budget_tokens
        self.max_turns = max_turns
        self.persist = persist
        self._depth = _depth
        self._on_event = on_event or (lambda kind, payload: None)

        self.messages = []
        self.session_path = session_path
        self._recorded = 0  # messages already written to the session log

        tools = {t.name: t for t in core_tools(self.workdir)}

        @tool("Save a durable fact to project memory (ODYSSEUS.md)",
              note="the fact to remember across future runs")
        def remember(note):
            return memory.remember(self.workdir, note)
        tools[remember.name] = remember

        if skills.catalog(self.workdir):
            @tool("Load a skill's full instructions by name",
                  name="the skill to load")
            def use_skill(name):
                return skills.read_skill(self.workdir, name)
            tools[use_skill.name] = use_skill

        if enable_subagents:
            def make_child(child_depth):
                # persist=False: a child's log must never hijack --resume.
                return Harness(
                    workdir=self.workdir, model=self.model, policy=self.policy,
                    system_extra=system_extra, on_event=self._on_event,
                    budget_tokens=self.budget_tokens, max_turns=self.max_turns,
                    enable_subagents=True, persist=False, _depth=child_depth,
                )
            spawn = subagent_tool(make_child, depth=self._depth)
            tools[spawn.name] = spawn

        if extra_tools:
            merged = extra_tools.values() if isinstance(extra_tools, dict) else extra_tools
            for t in merged:
                tools[t.name] = t
        self.tools = tools

        extra = "\n\n".join(x for x in [skills.catalog_prompt(self.workdir), system_extra] if x)
        self.system = memory.build_system_prompt(self.workdir, extra)

    def resume(self, path=None):
        """Load a prior session (the newest by default) into this harness.

        Returns True when messages were loaded, so the caller knows whether there
        is anything to continue.
        """
        path = path or session.latest(self.workdir)
        if not path:
            return False
        self.messages = session.load(path)
        self.session_path = path
        self._recorded = len(self.messages)  # already on disk; don't rewrite
        return bool(self.messages)

    def _flush(self):
        """Append any messages that have landed since the last write."""
        if not self.persist or not self.session_path:
            return
        while self._recorded < len(self.messages):
            session.append(self.session_path, self.messages[self._recorded])
            self._recorded += 1

    def _event(self, kind, payload):
        """Forward the event to the caller, then persist whatever it produced."""
        self._on_event(kind, payload)
        self._flush()

    def _before_turn(self, messages):
        """Compact the history to the token budget, keeping our reference live."""
        compacted = context.compact(self.model, messages, self.budget_tokens)
        # Compaction can shrink the list; clamp so we don't skip fresh messages.
        self._recorded = min(self._recorded, len(compacted))
        self.messages = compacted
        return compacted

    def run(self, task):
        """Run one task to a final text answer, persisting the whole exchange."""
        if self.persist and not self.session_path:
            self.session_path = session.new_session(self.workdir, task[:32])

        self.messages.append({"role": "user", "text": task})
        self._flush()

        answer = run_loop(
            self.model, self.system, self.messages, self.tools,
            self._event, self.policy.check,
            max_turns=self.max_turns, before_turn=self._before_turn,
        )
        self._flush()
        return answer
