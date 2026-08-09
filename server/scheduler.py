# SignalLoop daily suggestion scheduler — a dev *sketch* of the cloud wake plane.
"""Daily loop-suggestion scheduler (cloud-wake sketch).

AGENTS.md is explicit: reliable multi-day cadence belongs to the approved
**cloud wake plane**, and the developer Mac is NOT a product "desktop agent
node." This module is therefore a *local sketch* of that plane, for development
only — **off by default**, enabled with ``CHITTI_SUGGEST_ENABLED=1``.

When enabled it wakes once per day (``CHITTI_SUGGEST_HOUR``, local time) and asks
the suggester to draft today's next action(s) for every active loop. It only
produces **drafts** (through the command bus) and never externalizes anything.
In production this exact call is what a scheduled cloud job would invoke; the
phone learns about the results by polling ``GET /v1/suggestions/today`` (until
real APNs push lands).

Env:
  CHITTI_SUGGEST_ENABLED   "1" to run the scheduler (default off)
  CHITTI_SUGGEST_HOUR      local hour-of-day to run, 0-23 (default 7)
  CHITTI_SUGGEST_ON_START  "1" to also run once immediately (dev/test hook)
"""

from __future__ import annotations

import os
import threading
from datetime import datetime

from . import suggester


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
    ):
        self.hour = (
            int(os.environ.get("CHITTI_SUGGEST_HOUR", "7")) if hour is None else hour
        )
        self.enabled = _flag("CHITTI_SUGGEST_ENABLED") if enabled is None else enabled
        self.on_start = _flag("CHITTI_SUGGEST_ON_START") if on_start is None else on_start
        self.interval_s = interval_s
        self._last_run_date: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not self.enabled:
            print(
                "  suggest scheduler: disabled "
                "(set CHITTI_SUGGEST_ENABLED=1 to enable the cloud-wake sketch)"
            )
            return
        print(f"  suggest scheduler: enabled (daily ~{self.hour:02d}:00 local)")
        self._thread = threading.Thread(
            target=self._run, name="suggest-scheduler", daemon=True
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
            result = suggester.suggest_active()
            self._last_run_date = today
            print(
                f"[suggest-scheduler] {today}: suggested "
                f"{result.get('count', 0)} active loop(s)"
            )
            return result
        except Exception as e:
            # A model/provider hiccup must never kill the scheduler thread.
            print(f"[suggest-scheduler] {today}: FAILED: {e}")
            return {"error": str(e), "date": today}


_default = SuggestScheduler()


def start() -> None:
    """Start the process-wide scheduler (no-op unless enabled by env)."""
    _default.start()


def run_now() -> dict:
    """Run one suggestion batch immediately, regardless of hour."""
    return _default.run_now()
