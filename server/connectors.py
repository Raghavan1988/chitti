# SignalLoop engagement connectors: the pluggable source of engagement candidates.
"""Engagement connectors — the seam between SignalLoop and a social source.

A *connector* turns a loop's topic into a list of engagement **candidates**:
people worth connecting to and posts worth commenting on. It is the one place a
real integration (the official X API, or a user-in-the-loop LinkedIn import)
will later plug in. Everything above this layer — the scout unit, scoring,
drafting, and the review gate — is platform-agnostic and works against any
connector.

Design rules (AGENTS.md):
  - **Read-only + draft-only.** A connector only *discovers* candidates; it never
    connects, comments, follows, or sends. Externalizing a drafted action stays
    gated behind an authenticated foreground review (LoopEngine ``externalize``).
  - **No scraping at scale.** Real connectors must use authorized reads (official
    APIs / explicit user import), never bulk scraping (an explicit product
    non-goal). The default :class:`StubConnector` is fully offline and
    deterministic so the whole pipeline is testable without any network or key.
  - **Stdlib only**, like the rest of ``server/``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    """One discovered engagement target.

    ``kind`` is ``"person"`` (draft a connect note) or ``"post"`` (draft a
    comment). ``text`` is the person's bio or the post's body; ``topics`` are
    coarse tags the scout scores against the loop. Nothing here is an action —
    only a candidate the scout may draft, and the user may later review.
    """

    id: str
    kind: str  # "person" | "post"
    platform: str  # "x" | "linkedin" | ...
    handle: str
    name: str
    text: str
    topics: tuple[str, ...] = ()
    url: str = ""


class Connector:
    """Base connector: return engagement candidates for a topic query."""

    name = "base"

    def find_candidates(
        self, query: str, *, platform: str | None = None, limit: int = 12
    ) -> list[Candidate]:
        """Return candidates relevant to ``query``.

        Implementations are read-only and side-effect-free. ``platform``, when
        given, restricts results to a single platform; ``limit`` is an upper
        bound the caller may further trim after scoring.
        """
        raise NotImplementedError


# A small, deterministic, offline pool. Realistic enough to exercise scoring and
# drafting end to end without any network or API key. Real connectors replace
# this with authorized reads from X / an imported LinkedIn list.
_POOL: tuple[Candidate, ...] = (
    Candidate(
        id="person_infra",
        kind="person",
        platform="linkedin",
        handle="@aishak",
        name="Aisha Khan",
        text="Builds large-scale ML inference systems.",
        topics=("ml", "infrastructure", "inference", "gpu"),
        url="https://www.linkedin.com/in/aishak",
    ),
    Candidate(
        id="person_founder",
        kind="person",
        platform="x",
        handle="@marcoreyes",
        name="Marco Reyes",
        text="Founder building AI agents for developers.",
        topics=("ai", "startups", "agents", "product"),
        url="https://x.com/marcoreyes",
    ),
    Candidate(
        id="person_research",
        kind="person",
        platform="x",
        handle="@lenaf",
        name="Lena Fischer",
        text="LLM evaluation researcher.",
        topics=("research", "llm", "evaluation", "safety"),
        url="https://x.com/lenaf",
    ),
    Candidate(
        id="person_devrel",
        kind="person",
        platform="linkedin",
        handle="@samokoro",
        name="Sam Okoro",
        text="Developer community and open-source devtools.",
        topics=("developer", "community", "devtools", "open source"),
        url="https://www.linkedin.com/in/samokoro",
    ),
    Candidate(
        id="person_climate",
        kind="person",
        platform="linkedin",
        handle="@priyan",
        name="Priya Nair",
        text="Grid-scale energy and climate policy.",
        topics=("climate", "energy", "policy"),
        url="https://www.linkedin.com/in/priyan",
    ),
    Candidate(
        id="person_design",
        kind="person",
        platform="x",
        handle="@noahk",
        name="Noah Kim",
        text="Product design and onboarding UX.",
        topics=("design", "ux", "product"),
        url="https://x.com/noahk",
    ),
    Candidate(
        id="post_agents",
        kind="post",
        platform="x",
        handle="@marcoreyes",
        name="Marco Reyes",
        text="Shipping an agent loop that survives multi-day tasks — here is what we learned.",
        topics=("agents", "ai", "loops", "reliability"),
        url="https://x.com/marcoreyes/status/1",
    ),
    Candidate(
        id="post_infra",
        kind="post",
        platform="linkedin",
        handle="@aishak",
        name="Aisha Khan",
        text="Cut inference latency 40% with a new batching scheme.",
        topics=("inference", "gpu", "infrastructure"),
        url="https://www.linkedin.com/posts/aishak-1",
    ),
    Candidate(
        id="post_hiring",
        kind="post",
        platform="x",
        handle="@marcoreyes",
        name="Marco Reyes",
        text="We are hiring engineers who have shipped real agent products.",
        topics=("hiring", "agents", "careers"),
        url="https://x.com/marcoreyes/status/2",
    ),
    Candidate(
        id="post_eval",
        kind="post",
        platform="x",
        handle="@lenaf",
        name="Lena Fischer",
        text="New eval harness for LLM tool use is live.",
        topics=("llm", "evaluation", "tools"),
        url="https://x.com/lenaf/status/1",
    ),
    Candidate(
        id="post_climate",
        kind="post",
        platform="linkedin",
        handle="@priyan",
        name="Priya Nair",
        text="Grid-scale battery costs fell again this quarter.",
        topics=("climate", "energy"),
        url="https://www.linkedin.com/posts/priyan-1",
    ),
    Candidate(
        id="post_design",
        kind="post",
        platform="x",
        handle="@noahk",
        name="Noah Kim",
        text="Redesigned our onboarding flow end to end.",
        topics=("design", "ux"),
        url="https://x.com/noahk/status/1",
    ),
)


class StubConnector(Connector):
    """Offline, deterministic connector used for dev and smoke tests.

    Returns a fixed candidate pool (optionally filtered by ``platform``). It
    intentionally ignores the ``query`` text — relevance scoring lives in the
    scout, so this stub stays a pure, stable data source. Swap it for a real
    connector by registering one in ``_REGISTRY``.
    """

    name = "stub"

    def __init__(self, pool: tuple[Candidate, ...] | None = None):
        self._pool = tuple(pool if pool is not None else _POOL)

    def find_candidates(
        self, query: str, *, platform: str | None = None, limit: int = 12
    ) -> list[Candidate]:
        pool = self._pool
        if platform:
            pool = tuple(c for c in pool if c.platform == platform)
        return list(pool)


# Connector registry. Add real connectors (e.g. "x", "linkedin_import") here as
# they are built; the scout and HTTP layer select one by name.
_REGISTRY: dict[str, type[Connector]] = {"stub": StubConnector}


def get_connector(name: str | None = None) -> Connector:
    """Return the configured connector (default: the offline stub).

    Selection order: explicit ``name`` → ``CHITTI_ENGAGEMENT_CONNECTOR`` env →
    ``"stub"``. Unknown names raise ``ValueError`` so a misconfiguration fails
    loudly rather than silently doing nothing.
    """
    name = (name or os.environ.get("CHITTI_ENGAGEMENT_CONNECTOR") or "stub").strip().lower()
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"unknown engagement connector: {name!r} (have: {sorted(_REGISTRY)})"
        )
    return factory()
