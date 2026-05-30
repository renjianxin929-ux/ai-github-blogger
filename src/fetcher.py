"""Repository fetching — GitHub Trending RSS + REST API search."""
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import feedparser
import requests

from .config import GITHUB_API_BASE, GITHUB_TOKEN, HTTP_TIMEOUT, SEARCH_KEYWORDS

logger = logging.getLogger(__name__)


@dataclass
class RawRepo:
    """Minimal repo data before enrichment."""
    full_name: str
    name: str
    url: str
    description: str
    language: str
    stars_today: int = 0


# ── RSS parsing ─────────────────────────────────────────────────────────

def _parse_rss_entries(xml_content: str) -> list[RawRepo]:
    """Parse GitHub Trending RSS/Atom feed into RawRepo objects."""
    feed = feedparser.parse(xml_content)
    repos = []
    for entry in feed.entries:
        # title is usually "owner/repo"
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        summary = getattr(entry, "summary", "") or getattr(entry, "content", [{}])[0].get("value", "")

        if "/" not in title:
            continue

        full_name = title.strip()
        name = full_name.split("/")[-1]
        url = link if link else f"https://github.com/{full_name}"

        repos.append(RawRepo(
            full_name=full_name,
            name=name,
            url=url,
            description=summary[:300] if summary else "",
            language="",
            stars_today=0,
        ))
    return repos


def _fetch_trending_rss() -> list[RawRepo]:
    """Fetch today's trending repos from GitHub Trending RSS."""
    # GitHub Trending doesn't have an official RSS, but there are community mirrors.
    # We try the primary feed first, then fall back to alternatives.
    urls = [
        "https://github.com/trending.atom",
        "https://rsshub.app/github/trending/daily",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            repos = _parse_rss_entries(resp.text)
            if repos:
                logger.info("Fetched %d repos from RSS: %s", len(repos), url)
                return repos
        except Exception as e:
            logger.warning("RSS fetch failed for %s: %s", url, e)

    logger.warning("All RSS sources failed, returning empty list")
    return []


# ── GitHub API search ────────────────────────────────────────────────────

def _build_headers() -> dict:
    """Build request headers with optional auth."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ai-github-blogger/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _build_search_url(keyword: str, page: int = 1) -> str:
    """Build GitHub search API URL."""
    q = quote(keyword)
    return (
        f"{GITHUB_API_BASE}/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page=30&page={page}"
    )


def _parse_search_response(data: dict) -> list[RawRepo]:
    """Parse GitHub search API response into RawRepo list."""
    repos = []
    for item in data.get("items", []):
        repos.append(RawRepo(
            full_name=item.get("full_name", ""),
            name=item.get("name", ""),
            url=item.get("html_url", ""),
            description=item.get("description", "") or "",
            language=item.get("language", "") or "",
            stars_today=item.get("stargazers_count", 0),
        ))
    return repos


def search_repos(keywords: Optional[list[str]] = None) -> list[RawRepo]:
    """Search GitHub for repos matching keywords. Deduplicates by full_name."""
    if keywords is None:
        keywords = SEARCH_KEYWORDS

    seen: set[str] = set()
    all_repos: list[RawRepo] = []
    headers = _build_headers()

    for keyword in keywords:
        try:
            url = _build_search_url(keyword)
            resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            repos = _parse_search_response(data)

            for repo in repos:
                if repo.full_name and repo.full_name not in seen:
                    seen.add(repo.full_name)
                    all_repos.append(repo)

            logger.info("Keyword '%s': %d repos (total unique: %d)", keyword, len(repos), len(all_repos))
            time.sleep(0.1)  # Be gentle with the API
        except Exception as e:
            logger.warning("Search failed for '%s': %s", keyword, e)
            time.sleep(1)

    return all_repos
