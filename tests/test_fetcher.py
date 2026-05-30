"""Tests for fetcher.py — GitHub Trending RSS + API search."""
from unittest import mock

import pytest


RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>owner1/repo1</title>
    <id>https://github.com/owner1/repo1</id>
    <link href="https://github.com/owner1/repo1"/>
    <content type="html">An AI agent framework</content>
  </entry>
  <entry>
    <title>owner2/repo2</title>
    <id>https://github.com/owner2/repo2</id>
    <link href="https://github.com/owner2/repo2"/>
    <content type="html">LLM orchestration toolkit</content>
  </entry>
</feed>"""


class TestRawRepo:
    """Test the RawRepo dataclass."""

    def test_raw_repo_creation(self):
        from src.fetcher import RawRepo

        r = RawRepo(
            full_name="test/repo",
            name="repo",
            url="https://github.com/test/repo",
            description="A test repo",
            language="Python",
            stars_today=42,
        )
        assert r.full_name == "test/repo"
        assert r.stars_today == 42


class TestFetchTrendingRSS:
    """Test RSS-based trending repo fetching."""

    def test_parses_entries(self):
        """Should parse RSS XML and extract RawRepo objects."""
        from src.fetcher import _parse_rss_entries

        repos = _parse_rss_entries(RSS_FIXTURE)
        assert len(repos) == 2
        assert repos[0].full_name == "owner1/repo1"
        assert repos[1].full_name == "owner2/repo2"


class TestSearchRepos:
    """Test GitHub REST API search."""

    def test_search_builds_correct_url(self):
        """Should construct the correct API URL with query params."""
        from src.fetcher import _build_search_url

        url = _build_search_url("AI agent", 1)
        assert "search/repositories" in url
        assert "AI+agent" in url or "AI%20agent" in url
        assert "sort=stars" in url
        assert "per_page=30" in url

    @mock.patch("src.fetcher.requests.get")
    def test_search_returns_repos(self, mock_get):
        """Should parse API response into RawRepo list."""
        from src.fetcher import search_repos

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "items": [
                {
                    "full_name": "test/awesome-ai",
                    "name": "awesome-ai",
                    "html_url": "https://github.com/test/awesome-ai",
                    "description": "An awesome AI list",
                    "language": "Python",
                    "stargazers_count": 5000,
                }
            ]
        }
        mock_get.return_value.raise_for_status = lambda: None

        repos = search_repos(["AI"])
        assert len(repos) >= 1
        # At least one repo should match
        found = any(r.full_name == "test/awesome-ai" for r in repos)
        assert found, f"Expected 'test/awesome-ai' in results, got: {[r.full_name for r in repos]}"

    @mock.patch("src.fetcher.requests.get")
    def test_search_handles_empty_results(self, mock_get):
        """Empty search results should return empty list."""
        from src.fetcher import search_repos

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"items": []}
        mock_get.return_value.raise_for_status = lambda: None

        repos = search_repos(["nonexistent-xyz-123"])
        assert repos == []

    @mock.patch("src.fetcher.requests.get")
    def test_search_deduplicates_across_keywords(self, mock_get):
        """Same repo returned for multiple keywords should be deduplicated."""
        from src.fetcher import search_repos

        same_item = {
            "full_name": "test/dup-repo",
            "name": "dup-repo",
            "html_url": "https://github.com/test/dup-repo",
            "description": "test",
            "language": "Python",
            "stargazers_count": 100,
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"items": [same_item]}
        mock_get.return_value.raise_for_status = lambda: None

        repos = search_repos(["AI", "LLM"])
        # Should be deduplicated
        names = [r.full_name for r in repos]
        assert names.count("test/dup-repo") == 1
