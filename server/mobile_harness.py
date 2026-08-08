# Mobile harness: Odysseus loop + life-ops tools + approval policy.
"""Day M1–M4 — the phone-facing agent assembly.

Unlike odysseus.Harness, this does not ship bash/file coding tools. It wires
mobile tools, a personal-ops system prompt, CHITTI.md memory, skills, session
persistence, and an ApprovalGate for confirm-before-write.
"""

from __future__ import annotations

import os
import platform
from typing import Callable

from odysseus import context, provider, session, skills
from odysseus.loop import run_loop
from odysseus.tools import tool

from .approvals import ApprovalGate
from .config import DATA_DIR, config
from .tools_mobile import MEMORY_FILE, mobile_tools

# Tools that never need a human (reads, drafts, memory).
AUTO_ALLOW = {
    "calendar_list",
    "calendar_propose_event",
    "draft_message",
    "remember",
    "use_skill",
}
# Tools that self-gate via ApprovalGate inside run().
SELF_GATED = {"calendar_commit_event", "notes_append"}

MOBILE_BASE_PROMPT = (
    "You are Chitti, a personal ops agent for the user's phone. You help with "
    "day planning, calendar, drafts, and notes — not coding. Act, don't narrate: "
    "use tools. Inspect calendar before proposing changes. Prefer "
    "calendar_propose_event then calendar_commit_event (the user must approve "
    "commits). Never claim you sent a message — draft_message only stores a "
    "draft for the user. Load the morning_prep skill when the user asks to prep "
    "their day. When done, give a short spoken-friendly summary and stop."
)


def build_mobile_system_prompt(workdir: str, extra: str = "") -> str:
    """Character + environment + CHITTI.md memory + optional extras."""
    root = os.path.realpath(workdir)
    sections = [
        MOBILE_BASE_PROMPT,
        f"Platform: {platform.system()}. Workspace: {root}",
    ]
    memory_path = os.path.join(root, MEMORY_FILE)
    if os.path.isfile(memory_path):
        with open(memory_path, encoding="utf-8") as f:
            body = f.read().strip()
        if body:
            sections.append(f"User memory ({MEMORY_FILE}):\n{body}")
    if extra:
        sections.append(extra)
    return "\n\n".join(sections)


class MobileHarness:
    """A fully wired phone agent over one workspace directory."""

    def __init__(
        self,
        workdir: str | None = None,
        model: str | None = None,
        policy_mode: str | None = None,
        on_event: Callable | None = None,
        gate: ApprovalGate | None = None,
        session_path: str | None = None,
        persist: bool = True,
        max_turns: int | None = None,
        budget_tokens: int | None = None,
    ):
        self.workdir = os.path.realpath(workdir or str(config.workdir))
        os.makedirs(self.workdir, exist_ok=True)
        self.model = model or config.model or provider.DEFAULT_MODEL
        self.budget_tokens = budget_tokens if budget_tokens is not None else config.budget_tokens
        self.max_turns = max_turns if max_turns is not None else config.max_turns
        self.persist = persist
        self._on_event = on_event or (lambda kind, payload: None)

        self.messages: list = []
        self.session_path = session_path
        self._recorded = 0

        self.policy_mode = policy_mode or config.policy_mode
        self.gate = gate or ApprovalGate(
            timeout_s=config.approval_timeout_s,
            on_request=self._emit_approval,
        )
        # yolo: short-circuit the gate so commits never wait on a human.
        if self.policy_mode == "yolo":
            self.gate.request = lambda call, reason: "approved"  # type: ignore

        fixture = DATA_DIR / "calendar_fixture.json"
        tools_list = mobile_tools(self.workdir, self.gate, fixture)
        self.tools = {t.name: t for t in tools_list}

        if skills.catalog(self.workdir):
            @tool("Load a skill's full instructions by name", name="the skill to load")
            def use_skill(name):
                return skills.read_skill(self.workdir, name)

            self.tools[use_skill.name] = use_skill

        if self.policy_mode == "read-only":
            for name in list(self.tools):
                if name in SELF_GATED:
                    del self.tools[name]

        extra = skills.catalog_prompt(self.workdir)
        self.system = build_mobile_system_prompt(self.workdir, extra)

    def policy_check(self, call):
        """Return None to allow, or a reason string to block (loop before_tool)."""
        name = call.get("name", "")
        if name in {"bash", "write_file", "edit_file", "read_file", "list_files", "grep"}:
            return "mobile harness does not allow coding tools"
        if name in AUTO_ALLOW or name in SELF_GATED:
            return None
        if self.policy_mode == "yolo":
            return None
        if self.policy_mode == "read-only":
            return f"read-only mode: {name} is not allowed"
        # Unknown write-like tools: ask the user once via the gate.
        decision = self.gate.request(call, f"run {name}")
        if decision == "approved":
            return None
        return f"not approved: {decision}"

    def _emit_approval(self, req):
        self._on_event(
            "approval_required",
            {
                "id": req.id,
                "call": req.call,
                "reason": req.reason,
            },
        )

    def _event(self, kind, payload):
        # Serialize tool payloads for JSON clients.
        safe = payload
        if kind in ("assistant",):
            safe = {
                "text": payload.get("text", ""),
                "tool_calls": payload.get("tool_calls") or [],
                "usage": payload.get("usage"),
            }
        elif kind == "tool_end":
            safe = {
                "call": payload.get("call"),
                "result": str(payload.get("result", "")),
            }
        self._on_event(kind, safe)
        self._flush()

    def _flush(self):
        if not self.persist or not self.session_path:
            return
        while self._recorded < len(self.messages):
            session.append(self.session_path, self.messages[self._recorded])
            self._recorded += 1

    def _before_turn(self, messages):
        compacted = context.compact(self.model, messages, self.budget_tokens)
        self._recorded = min(self._recorded, len(compacted))
        self.messages = compacted
        return compacted

    def resume(self, path: str | None = None) -> bool:
        path = path or session.latest(self.workdir)
        if not path:
            return False
        self.messages = session.load(path)
        self.session_path = path
        self._recorded = len(self.messages)
        return bool(self.messages)

    def ensure_session(self, label: str = "mobile"):
        if self.persist and not self.session_path:
            self.session_path = session.new_session(self.workdir, label)
        return self.session_path

    def run(self, task: str) -> str:
        """Run one user turn to a final text answer."""
        self.ensure_session(task[:32] or "mobile")
        # Refresh system prompt so new memory is visible mid-day.
        self.system = build_mobile_system_prompt(
            self.workdir, skills.catalog_prompt(self.workdir)
        )
        self.messages.append({"role": "user", "text": task})
        self._flush()
        self._on_event("user", {"text": task})

        answer = run_loop(
            self.model,
            self.system,
            self.messages,
            self.tools,
            self._event,
            self.policy_check,
            max_turns=self.max_turns,
            before_turn=self._before_turn,
        )
        self._flush()
        self._on_event("done", {"text": answer})
        return answer
