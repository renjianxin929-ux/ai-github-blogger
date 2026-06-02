"""Post-publish metrics tracking — Phase 24.

Manually-entered performance data for published content.
Zero platform APIs, zero credentials, zero auto-publishing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import STATE_DIR

logger = logging.getLogger(__name__)

METRICS_HISTORY_FILE = STATE_DIR / "metrics_history.json"

VALID_PLATFORMS = {"wechat", "xiaohongshu", "douyin", "videohao", "geo"}


def normalize_repo(full_name: str) -> str:
    return full_name.strip().lower()


# ═══════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════

def load_metrics_history() -> dict:
    if not METRICS_HISTORY_FILE.exists():
        return {}
    try:
        data = json.loads(METRICS_HISTORY_FILE.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning("Failed to load metrics_history.json, returning empty")
        return {}


def save_metrics_history(data: dict) -> None:
    METRICS_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    METRICS_HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Core operations
# ═══════════════════════════════════════════════════════════════

def record_metrics(repo: str, platform: str,
                   views: int = 0, likes: int = 0, favorites: int = 0,
                   comments: int = 0, leads: int = 0,
                   note: str | None = None) -> dict:
    """Record performance metrics for a published repo on a platform.

    Returns:
        dict with status, repo, platform, engagement_rate, lead_rate, message.
    """
    platform = platform.strip().lower()
    if platform not in VALID_PLATFORMS:
        return {"status": "blocked",
                "reason": f"不支持的平台: {platform}，支持: {', '.join(sorted(VALID_PLATFORMS))}",
                "repo": repo, "platform": platform}

    repo_key = normalize_repo(repo)
    history = load_metrics_history()

    # Compute derived metrics
    engagement_rate = _compute_engagement_rate(views, likes, favorites, comments)
    lead_rate = _compute_lead_rate(views, leads)

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "platform": platform,
        "recorded_at": now,
        "views": views,
        "likes": likes,
        "favorites": favorites,
        "comments": comments,
        "leads": leads,
        "engagement_rate": round(engagement_rate, 4),
        "lead_rate": round(lead_rate, 4),
        "note": note,
    }

    if repo_key not in history:
        history[repo_key] = []
    history[repo_key].append(entry)
    save_metrics_history(history)

    return {"status": "ok", "repo": repo, "platform": platform,
            "engagement_rate": entry["engagement_rate"],
            "lead_rate": entry["lead_rate"],
            "message": f"已记录 {repo} → {platform} (views={views}, likes={likes})"}


def get_metrics_history(repo: str | None = None) -> list | dict:
    history = load_metrics_history()
    if repo is None:
        return history
    key = normalize_repo(repo)
    return history.get(key, [])


def summarize_metrics(repo: str | None = None) -> dict:
    """Aggregate summary of all recorded metrics.

    When repo is None, summarizes across all repos.
    When repo is provided, summarizes only that repo.

    Returns:
        dict with repo_count, entry_count, platform_count, best_views,
        best_engagement, best_lead, recent_entries, per_platform, per_type.
    """
    history = load_metrics_history()

    if repo:
        key = normalize_repo(repo)
        entries = history.get(key, [])
        repos = {key: entries}
    else:
        repos = history

    all_entries = []
    for rname, entries in repos.items():
        for e in entries:
            all_entries.append({**e, "_repo": rname})

    if not all_entries:
        return {
            "repo_count": 0, "entry_count": 0, "platform_count": 0,
            "best_views": None, "best_engagement": None, "best_lead": None,
            "recent_entries": [], "per_platform": {}, "per_type": {},
        }

    # Best by dimension
    best_views = max(all_entries, key=lambda e: e.get("views", 0))
    best_engagement = max(all_entries, key=lambda e: e.get("engagement_rate", 0))
    best_lead = max(all_entries, key=lambda e: e.get("lead_rate", 0))

    # Recent 5
    recent = sorted(all_entries, key=lambda e: e.get("recorded_at", ""), reverse=True)[:5]

    # Per platform aggregation
    per_platform: dict[str, dict] = {}
    for e in all_entries:
        p = e["platform"]
        if p not in per_platform:
            per_platform[p] = {"count": 0, "total_views": 0, "total_likes": 0,
                               "total_comments": 0, "total_leads": 0}
        per_platform[p]["count"] += 1
        per_platform[p]["total_views"] += e.get("views", 0)
        per_platform[p]["total_likes"] += e.get("likes", 0)
        per_platform[p]["total_comments"] += e.get("comments", 0)
        per_platform[p]["total_leads"] += e.get("leads", 0)

    # Per content_type aggregation (infer from publish_history)
    from .publish_history import get_publish_history
    pubhist = get_publish_history()
    per_type: dict[str, dict] = {}
    for e in all_entries:
        rname = e.get("_repo", "")
        pub_entries = pubhist.get(rname, [])
        content_type = "unknown"
        if pub_entries:
            content_type = pub_entries[0].get("source_mode", "unknown")
        if content_type not in per_type:
            per_type[content_type] = {"count": 0, "total_views": 0, "avg_engagement": 0}
        per_type[content_type]["count"] += 1
        per_type[content_type]["total_views"] += e.get("views", 0)

    for ct in per_type:
        entries_ct = [e for e in all_entries
                      if (pubhist.get(e.get("_repo", ""), [{}])[0].get("source_mode", "unknown")) == ct]
        if entries_ct:
            per_type[ct]["avg_engagement"] = round(
                sum(e.get("engagement_rate", 0) for e in entries_ct) / len(entries_ct), 4)

    unique_repos = len({e["_repo"] for e in all_entries})
    unique_platforms = len({e["platform"] for e in all_entries})

    return {
        "repo_count": unique_repos,
        "entry_count": len(all_entries),
        "platform_count": unique_platforms,
        "best_views": {"repo": best_views["_repo"], "platform": best_views["platform"],
                       "views": best_views["views"], "recorded_at": best_views.get("recorded_at", "")},
        "best_engagement": {"repo": best_engagement["_repo"], "platform": best_engagement["platform"],
                            "rate": best_engagement["engagement_rate"]},
        "best_lead": {"repo": best_lead["_repo"], "platform": best_lead["platform"],
                      "rate": best_lead["lead_rate"]},
        "recent_entries": recent,
        "per_platform": per_platform,
        "per_type": per_type,
    }


# ═══════════════════════════════════════════════════════════════
# Derived metric helpers
# ═══════════════════════════════════════════════════════════════

def _compute_engagement_rate(views: int, likes: int, favorites: int,
                             comments: int) -> float:
    if views <= 0:
        return 0.0
    return (likes + favorites + comments) / views


def _compute_lead_rate(views: int, leads: int) -> float:
    if views <= 0:
        return 0.0
    return leads / views
