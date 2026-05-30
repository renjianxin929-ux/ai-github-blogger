"""Deduplication and state management for repo recommendations.

State files:
  - data/state/seen_repos.json  — repos that have been recommended before
  - data/state/generated_repos.json — repos that already have content packs

These files are git-tracked (NOT in .gitignore) so that GitHub Actions
can persist state across runs by committing changes back.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .config import DAYS_TO_DEDUP


@dataclass
class SeenReposState:
    """In-memory representation of dedup state."""
    seen: dict = field(default_factory=dict)
    generated: dict = field(default_factory=dict)


# ── Repo name sanitization ──────────────────────────────────────────────

def slugify_repo_name(full_name: str) -> str:
    """Convert owner/repo to owner__repo for use as directory name."""
    return full_name.replace("/", "__")


# ── State file I/O ──────────────────────────────────────────────────────

def load_state(state_dir: Optional[Path] = None) -> SeenReposState:
    """Load dedup state from JSON files. Auto-creates files and dirs if missing."""
    if state_dir is None:
        from .config import STATE_DIR
        state_dir = STATE_DIR

    state_dir.mkdir(parents=True, exist_ok=True)

    seen_file = state_dir / "seen_repos.json"
    generated_file = state_dir / "generated_repos.json"

    seen = {}
    generated = {}

    if seen_file.exists():
        seen = json.loads(seen_file.read_text(encoding="utf-8"))
    else:
        seen_file.write_text("{}", encoding="utf-8")

    if generated_file.exists():
        generated = json.loads(generated_file.read_text(encoding="utf-8"))
    else:
        generated_file.write_text("{}", encoding="utf-8")

    return SeenReposState(seen=seen, generated=generated)


def _save_state(state: SeenReposState, state_dir: Optional[Path] = None):
    """Persist state to disk."""
    if state_dir is None:
        from .config import STATE_DIR
        state_dir = STATE_DIR

    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "seen_repos.json").write_text(
        json.dumps(state.seen, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (state_dir / "generated_repos.json").write_text(
        json.dumps(state.generated, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Dedup logic ─────────────────────────────────────────────────────────

def apply_dedup(repos: list, state: SeenReposState) -> list:
    """Filter and flag repos based on dedup state.

    - Generated repos (have content pack): REMOVED entirely.
    - Seen repos within DAYS_TO_DEDUP: kept but flagged with _dedup_penalty=0.5.
    - Old seen repos (beyond DAYS_TO_DEDUP): kept with no penalty.
    - Never-seen repos: kept with no penalty.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DAYS_TO_DEDUP)

    result = []
    for repo in repos:
        full_name = repo.full_name

        # Already generated? Skip entirely
        if full_name in state.generated:
            continue

        # Recently seen? Apply penalty
        if full_name in state.seen:
            last_seen_str = state.seen[full_name].get("last_seen", "")
            try:
                last_seen = datetime.fromisoformat(last_seen_str)
                # Make timezone-aware if naive (for correct comparison)
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                if last_seen > cutoff:
                    repo._dedup_penalty = 0.5
            except (ValueError, TypeError):
                pass

        result.append(repo)

    return result


# ── State mutation ──────────────────────────────────────────────────────

def mark_as_recommended(full_names: list[str], state_dir: Optional[Path] = None):
    """Record that these repos have been recommended today."""
    state = load_state(state_dir)
    now = datetime.now(timezone.utc).isoformat()

    for name in full_names:
        if name in state.seen:
            state.seen[name]["last_seen"] = now
            state.seen[name]["times_recommended"] += 1
        else:
            state.seen[name] = {
                "first_seen": now,
                "last_seen": now,
                "times_recommended": 1,
            }

    _save_state(state, state_dir)


def mark_as_generated(full_name: str, content_types: list[str], state_dir: Optional[Path] = None):
    """Record that a content pack was generated for this repo."""
    state = load_state(state_dir)
    now = datetime.now(timezone.utc).isoformat()

    state.generated[full_name] = {
        "generated_at": now,
        "content_types": content_types,
    }

    _save_state(state, state_dir)
