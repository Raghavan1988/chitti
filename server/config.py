# Environment and path configuration for the mobile harness server.
"""Config loaded from environment variables.

CHITTI_API_KEY gates every request (solo-dev auth). ODYSSEUS_API_KEY /
OPENAI_API_KEY unlock the model via the existing Odysseus provider.
"""

import os
from pathlib import Path

# Repo root: server/ is one level down.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKDIR = REPO_ROOT / "server" / "workspace"
DATA_DIR = Path(__file__).resolve().parent / "data"


def _env(name, default=None):
    value = os.environ.get(name)
    return value if value not in (None, "") else default


class Config:
    """Runtime settings for one server process."""

    def __init__(self):
        self.host = _env("CHITTI_HOST", "0.0.0.0")
        self.port = int(_env("CHITTI_PORT", "8787"))
        self.api_key = _env("CHITTI_API_KEY", "dev-key-change-me")
        self.workdir = Path(_env("CHITTI_WORKDIR", str(DEFAULT_WORKDIR))).resolve()
        self.model = _env("ODYSSEUS_MODEL")  # None → provider default
        self.policy_mode = _env("CHITTI_POLICY", "safe")  # read-only | safe | yolo
        self.approval_timeout_s = float(_env("CHITTI_APPROVAL_TIMEOUT", "300"))
        self.max_turns = int(_env("CHITTI_MAX_TURNS", "40"))
        self.budget_tokens = int(_env("CHITTI_BUDGET_TOKENS", "200000"))

    def ensure_workdir(self):
        """Create workspace dirs and symlink skills from the repo if needed."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        skills_dst = self.workdir / "skills"
        skills_src = REPO_ROOT / "skills"
        # Heal a stale or broken skills symlink (e.g. one left over from a
        # different host, where the old absolute target no longer resolves).
        if skills_dst.is_symlink():
            points_elsewhere = skills_dst.resolve(strict=False) != skills_src.resolve(strict=False)
            if points_elsewhere or not skills_dst.exists():
                skills_dst.unlink()
        if not skills_dst.exists() and skills_src.is_dir():
            try:
                skills_dst.symlink_to(skills_src, target_is_directory=True)
            except OSError:
                # Fall back to a note file if symlinks are blocked.
                skills_dst.mkdir(exist_ok=True)
        (self.workdir / ".chitti").mkdir(exist_ok=True)
        return self.workdir


config = Config()
