"""Repository enrichment — fetch metadata, README, license from GitHub API."""
import base64
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

from .config import GITHUB_API_BASE, GITHUB_TOKEN, HTTP_TIMEOUT, MAX_README_CHARS

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


def enrich_repo(full_name: str) -> Optional[EnrichedRepo]:
    """Fetch full metadata for a single GitHub repo.

    Calls:
      - GET /repos/{owner}/{repo}  → stars, forks, topics, license, etc.
      - GET /repos/{owner}/{repo}/readme  → README (base64-decoded, truncated)
      - GET /repos/{owner}/{repo}/contributors?per_page=5  → count

    Returns None if the repo can't be fetched.
    """
    headers = _build_headers()
    base_url = f"{GITHUB_API_BASE}/repos/{full_name}"

    try:
        # 1. Repo metadata
        repo_resp = requests.get(base_url, headers=headers, timeout=HTTP_TIMEOUT)
        repo_resp.raise_for_status()
        repo_data = repo_resp.json()

        # 2. README
        readme = ""
        try:
            readme_resp = requests.get(
                f"{base_url}/readme", headers=headers, timeout=HTTP_TIMEOUT
            )
            readme_resp.raise_for_status()
            readme_data = readme_resp.json()
            if readme_data.get("encoding") == "base64" and readme_data.get("content"):
                readme = base64.b64decode(readme_data["content"]).decode("utf-8", errors="replace")
                readme = readme[:MAX_README_CHARS]
        except Exception:
            logger.debug("No README found for %s", full_name)

        # 3. Contributors count
        contributors_count = 0
        try:
            contrib_resp = requests.get(
                f"{base_url}/contributors?per_page=5",
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
            contrib_resp.raise_for_status()
            contributors_count = len(contrib_resp.json())
        except Exception:
            logger.debug("Could not fetch contributors for %s", full_name)

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
    except Exception as e:
        logger.warning("Failed to enrich %s: %s", full_name, e)
        return None
