# SignalLoop daily suggestion scheduler — a dev *sketch* of the cloud wake plane.
"""Daily loop-suggestion scheduler (cloud-wake sketch).

AGENTS.md is explicit: reliable multi-day cadence belongs to the approved
**cloud wake plane**, and the developer Mac is NOT a product "desktop agent
node." This module is therefore a *local sketch* of that plane, for development
only — **off by default**, enabled with ``CHITTI_SUGGEST_ENABLED=1``.

When enabled it wakes once per day (``CHITTI_BRIEFING_HOUR``, local time) and
generates today's **Daily Briefing** for every active loop — the audio-digest
transcript, an editable X post, and a person-to-know (PRD §4), each grounded in
a fresh web-research pass. It only produces **reviewable drafts/briefings**
(through the command bus and briefing sidecar) and never externalizes anything.
In production this exact call is what a scheduled cloud job would invoke; the
phone learns about the results by polling ``GET /v1/suggestions/today`` (until
real APNs push lands).

Env:
  CHITTI_SUGGEST_ENABLED   "1" to run the scheduler (default off)
  CHITTI_BRIEFING_HOUR     local hour-of-day to run, 0-23 (default 8;
                           falls back to CHITTI_SUGGEST_HOUR for compatibility)
  CHITTI_SUGGEST_ON_START  "1" to also run once immediately (dev/test hook)
  CHITTI_SCOUT_ENABLED     "1" to also draft engagement candidates
                           (connect/comment) per loop in the daily wake
                           (default off)
"""

from __future__ import annotations

import os
import threading
from datetime import datetime

from . import briefing, scout


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class SuggestScheduler:
    """A daemon thread that triggers the daily suggestion batch."""

    def __init__(
        self,
        hour: int | None = None,
        enabled: bool | None = None,
        on_start: bool | None = None,
        interval_s: int = 60,
        scout_enabled: bool | None = None,
    ):
        self.hour = (
            int(os.environ.get("CHITTI_BRIEFING_HOUR",
                               os.environ.get("CHITTI_SUGGEST_HOUR", "8")))
            if hour is None
            else hour
        )
        self.enabled = _flag("CHITTI_SUGGEST_ENABLED") if enabled is None else enabled
        self.on_start = _flag("CHITTI_SUGGEST_ON_START") if on_start is None else on_start
        self.scout_enabled = (
            _flag("CHITTI_SCOUT_ENABLED") if scout_enabled is None else scout_enabled
        )
        self.interval_s = interval_s
        self._last_run_date: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not self.enabled:
            print(
                "  briefing scheduler: disabled "
                "(set CHITTI_SUGGEST_ENABLED=1 to enable the cloud-wake sketch)"
            )
            return
        print(f"  briefing scheduler: enabled (daily ~{self.hour:02d}:00 local)")
        if self.scout_enabled:
            print("  engagement scout: enabled (drafts connect/comment per loop)")
        self._thread = threading.Thread(
            target=self._run, name="briefing-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_now(self) -> dict:
        """Trigger the batch immediately (used by the on-start hook/tests)."""
        return self._tick(force=True)

    def _run(self) -> None:
        if self.on_start:
            self._tick(force=True)
        while not self._stop.wait(self.interval_s):
            self._tick()

    def _tick(self, force: bool = False) -> dict:
        now = datetime.now()
        today = now.date().isoformat()
        if not force:
            if self._last_run_date == today:
                return {"skipped": "already-ran-today", "date": today}
            if now.hour < self.hour:
                return {"skipped": "before-hour", "date": today}
        try:
            result = briefing.run_active(force=force)
            if self.scout_enabled:
                try:
                    s = scout.scout_active(source="cloud_wake", force=force)
                    print(
                        f"[briefing-scheduler] {today}: scouted "
                        f"{s.get('count', 0)} active loop(s)"
                    )
                except Exception as e:
                    # Scouting is best-effort; never let it kill the wake.
                    print(f"[briefing-scheduler] {today}: scout FAILED: {e}")
            self._last_run_date = today
            print(
                f"[briefing-scheduler] {today}: briefed "
                f"{result.get('count', 0)} active loop(s)"
            )
            return result
        except Exception as e:
            # A model/provider hiccup must never kill the scheduler thread.
            print(f"[briefing-scheduler] {today}: FAILED: {e}")
            return {"error": str(e), "date": today}


_default = SuggestScheduler()


def start() -> None:
    """Start the process-wide scheduler (no-op unless enabled by env)."""
    _default.start()


def run_now() -> dict:
    """Run one suggestion batch immediately, regardless of hour."""
    return _default.run_now()
