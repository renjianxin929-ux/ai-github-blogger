"""Repository enrichment — fetch metadata, README, license from GitHub API."""
import logging
from dataclasses import dataclass, field
from typing import Optional

from .config import GITHUB_TOKEN, MAX_README_CHARS
from .error_handler import (
    github_repo_meta,
    github_readme,
    github_contributors,
    FailureSummary,
)

logger = logging.getLogger(__name__)


@dataclass
class EnrichedRepo:
    """A repository with full metadata fetched from GitHub API."""

    full_name: str
    name: str
    description: str
    url: str
    language: str
    stars: int
    forks: int
    open_issues: int
    updated_at: str
    created_at: str
    topics: list[str] = field(default_factory=list)
    license: str = ""
    readme: str = ""
    contributors_count: int = 0
    # Set by dedup.py — not part of GitHub data
    _dedup_penalty: float = 1.0


# ── GitHub API helpers ──────────────────────────────────────────────────

def _build_headers() -> dict:
    """Build request headers with optional auth."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ai-github-blogger/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def enrich_repo(full_name: str, failure_summary: FailureSummary | None = None) -> Optional[EnrichedRepo]:
    """Fetch full metadata for a single GitHub repo.

    Uses retry-enabled wrappers from error_handler for exponential backoff
    on transient failures (SSL EOF, timeout, connection reset, rate limit).
    Max 2 retries per repo, logs skipped/retry_failed on exhaustion.

    Returns None if repo metadata can't be fetched after all retries.
    """
    headers = _build_headers()

    # 1. Repo metadata (with retry)
    repo_data = github_repo_meta(full_name, headers, failure_summary=failure_summary)
    if repo_data is None:
        logger.warning("Skipped %s: repo_meta retry_failed", full_name)
        return None

    # 2. README (with retry; None is expected for repos without README)
    readme_raw = github_readme(full_name, headers, failure_summary=failure_summary)
    readme = (readme_raw or "")[:MAX_README_CHARS]

    # 3. Contributors count (with retry; returns 0 on failure)
    contributors_count = github_contributors(full_name, headers, failure_summary=failure_summary)

    # Extract license
    license_str = ""
    lic = repo_data.get("license")
    if lic and isinstance(lic, dict):
        license_str = lic.get("spdx_id", "")

    return EnrichedRepo(
        full_name=repo_data.get("full_name", full_name),
        name=repo_data.get("name", full_name.split("/")[-1]),
        description=repo_data.get("description", "") or "",
        url=repo_data.get("html_url", ""),
        language=repo_data.get("language", "") or "",
        stars=repo_data.get("stargazers_count", 0),
        forks=repo_data.get("forks_count", 0),
        open_issues=repo_data.get("open_issues_count", 0),
        updated_at=repo_data.get("updated_at", ""),
        created_at=repo_data.get("created_at", ""),
        topics=repo_data.get("topics", []),
        license=license_str,
        readme=readme,
        contributors_count=contributors_count,
    )
