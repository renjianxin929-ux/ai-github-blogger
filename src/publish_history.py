"""Publish history tracking & dedup — Phase 21.

Records when, where, and what was published. Enables:
  - mark-published: record a publish event (multi-platform per pack)
  - publish-history: query past publishes
  - is_published: dedup guard for candidate detection

State machine (extended from Phase 18):
  review -> approved -> published (terminal for approve/reject/revise,
                            but allows additional platform marks)
  review -> rejected (terminal)
  review -> revision_notes (repeatable)

No platform APIs, no credentials, no auto-publishing.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import STATE_DIR

logger = logging.getLogger(__name__)

PUBLISH_HISTORY_FILE = STATE_DIR / "publish_history.json"

VALID_PLATFORMS = {"wechat", "xiaohongshu", "douyin", "videohao", "geo"}

CONTENT_FILES_TO_HASH = [
    "01_wechat_ready.md",
    "02_xiaohongshu_ready.md",
    "03_video_script_ready.md",
]


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def normalize_repo(full_name: str) -> str:
    """Normalize a repo full_name: lowercase, strip whitespace."""
    return full_name.strip().lower()


def is_published(repo_full_name: str) -> bool:
    """Check if a repo has any published record.

    Used by daily/review-queue/publish-flow for dedup.
    """
    history = _load_publish_history()
    normalized = normalize_repo(repo_full_name)
    return normalized in history and len(history[normalized]) > 0


def get_publish_history(repo: str | None = None) -> list | dict:
    """Get publish history.

    Args:
        repo: If None, returns the full history dict keyed by repo name.
              If a repo full_name, returns a list of publish entries for that repo.

    Returns:
        dict (all repos) or list (single repo's entries).
    """
    history = _load_publish_history()
    if repo is None:
        return history
    normalized = normalize_repo(repo)
    return history.get(normalized, [])


def mark_published(pack_dir: str, platform: str, url: str | None = None,
                   note: str | None = None, force: bool = False) -> dict:
    """Record that a publish pack has been published to a platform.

    Gates:
      1. pack_dir must exist and contain 00_publish_manifest.json
      2. manifest.human_review_status must be "approved" or "published"
      3. Same (repo, platform) is idempotent — no duplicate entries

    On first mark: status changes approved -> published.
    On subsequent marks: status stays published, new platform appended.

    Returns:
        dict with keys: status, repo, platform, message
    """
    pack = Path(pack_dir)
    manifest_path = pack / "00_publish_manifest.json"

    # Gate 1: pack_dir + manifest must exist
    if not manifest_path.exists():
        return {"status": "blocked", "reason": f"不是有效的发布包目录: {pack_dir}",
                "repo": None, "platform": platform}

    manifest = _load_manifest(manifest_path)
    if manifest is None:
        return {"status": "blocked", "reason": "manifest 文件损坏或为空",
                "repo": None, "platform": platform}

    current_status = manifest.get("human_review_status", "")
    repo = normalize_repo(manifest.get("repo", ""))

    # Gate 2: status must be approved or published
    if current_status not in ("approved", "published"):
        return {"status": "blocked",
                "reason": f"发布包状态为 {current_status}，只有 approved/published 可以 mark-published",
                "repo": repo, "platform": platform}

    # Gate 3: validate platform
    platform = platform.strip().lower()
    if platform not in VALID_PLATFORMS:
        return {"status": "blocked",
                "reason": f"不支持的平台: {platform}，支持: {', '.join(sorted(VALID_PLATFORMS))}",
                "repo": repo, "platform": platform}

    # Load existing history
    history = _load_publish_history()
    repo_entries = history.get(repo, [])

    # Check for duplicate platform
    existing_idx = None
    for i, entry in enumerate(repo_entries):
        if entry["platform"] == platform:
            existing_idx = i
            break

    if existing_idx is not None:
        if not force:
            return {"status": "duplicate",
                    "reason": f"该平台 ({platform}) 已记录，使用 --force 覆盖 url/note",
                    "repo": repo, "platform": platform,
                    "existing": repo_entries[existing_idx]}
        # Force update: overwrite url/note
        repo_entries[existing_idx]["url"] = url
        repo_entries[existing_idx]["note"] = note
        repo_entries[existing_idx]["published_at"] = datetime.now(timezone.utc).isoformat()
        history[repo] = repo_entries
        _save_publish_history(history)
        return {"status": "ok", "repo": repo, "platform": platform,
                "message": f"已更新 {platform} 发布记录",
                "action": "updated"}

    # New platform entry
    now = datetime.now(timezone.utc).isoformat()
    content_hashes = _hash_content_files(pack)

    entry = {
        "published_at": now,
        "published_by": "human",
        "platform": platform,
        "url": url,
        "note": note,
        "pack_dir": str(pack),
        "source_mode": manifest.get("source_mode", "unknown"),
        "score": manifest.get("score"),
        "publishability_score": manifest.get("publishability_score"),
        "content_hashes": content_hashes,
    }

    if repo not in history:
        history[repo] = []
    history[repo].append(entry)
    _save_publish_history(history)

    # Update manifest
    published_platforms = manifest.get("published_platforms", [])
    if not isinstance(published_platforms, list):
        published_platforms = []
    if platform not in published_platforms:
        published_platforms.append(platform)

    manifest_updates = {
        "human_review_status": "published",
        "published_at": now,
        "published_by": "human",
        "published_platforms": published_platforms,
    }
    manifest.update(manifest_updates)

    # Append review history
    review_history = manifest.get("review_history", [])
    if not isinstance(review_history, list):
        review_history = []
    review_history.append({
        "action": "mark-published",
        "platform": platform,
        "url": url,
        "note": note,
        "timestamp": now,
    })
    manifest["review_history"] = review_history

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "ok", "repo": repo, "platform": platform,
            "message": f"已记录发布: {repo} → {platform}",
            "action": "created"}


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════


def _load_publish_history() -> dict:
    """Load publish history from JSON file. Returns empty dict if not found."""
    if not PUBLISH_HISTORY_FILE.exists():
        return {}
    try:
        data = json.loads(PUBLISH_HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        logger.warning("Failed to load publish_history.json, returning empty")
        return {}


def _save_publish_history(data: dict) -> None:
    """Persist publish history to JSON file."""
    PUBLISH_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH_HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_manifest(manifest_path: Path) -> dict | None:
    """Load a publish pack manifest JSON."""
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _hash_content_files(pack: Path) -> dict[str, str]:
    """Compute SHA256 hashes of content files in a publish pack.

    Only hashes files that exist — missing files are omitted from the result.
    """
    hashes = {}
    for fname in CONTENT_FILES_TO_HASH:
        fpath = pack / fname
        if fpath.exists():
            hashes[fname] = hashlib.sha256(fpath.read_bytes()).hexdigest()
    return hashes
