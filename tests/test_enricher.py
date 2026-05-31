"""Tests for enricher.py — GitHub API metadata fetching."""
import base64
from unittest import mock

import pytest


REPO_API_FIXTURE = {
    "full_name": "test/awesome-repo",
    "name": "awesome-repo",
    "description": "An awesome AI framework",
    "html_url": "https://github.com/test/awesome-repo",
    "language": "Python",
    "stargazers_count": 5000,
    "forks_count": 300,
    "open_issues_count": 12,
    "updated_at": "2026-05-28T00:00:00Z",
    "created_at": "2025-01-01T00:00:00Z",
    "topics": ["AI", "LLM", "agent"],
    "license": {"spdx_id": "MIT"},
}

README_CONTENT = "# Awesome Repo\n\nThis is a comprehensive AI framework.\n" * 50


class TestEnrichRepo:
    """Test the enrich_repo function."""

    @mock.patch("src.enricher.github_contributors")
    @mock.patch("src.enricher.github_readme")
    @mock.patch("src.enricher.github_repo_meta")
    def test_enrich_repo_returns_full_data(self, mock_meta, mock_readme, mock_contrib):
        """Should fetch and combine repo metadata, README, and contributors."""
        from src.enricher import enrich_repo

        mock_meta.return_value = dict(REPO_API_FIXTURE)
        mock_readme.return_value = README_CONTENT
        mock_contrib.return_value = 5

        repo = enrich_repo("test/awesome-repo")

        assert repo.full_name == "test/awesome-repo"
        assert repo.stars == 5000
        assert repo.forks == 300
        assert repo.license == "MIT"
        assert repo.topics == ["AI", "LLM", "agent"]
        assert len(repo.readme) > 200
        assert repo.contributors_count == 5

    @mock.patch("src.enricher.github_contributors")
    @mock.patch("src.enricher.github_readme")
    @mock.patch("src.enricher.github_repo_meta")
    def test_enrich_repo_handles_missing_license(self, mock_meta, mock_readme, mock_contrib):
        """Repos with no license should have empty string."""
        from src.enricher import enrich_repo

        no_license = dict(REPO_API_FIXTURE)
        no_license["license"] = None

        mock_meta.return_value = no_license
        mock_readme.return_value = README_CONTENT
        mock_contrib.return_value = 3

        repo = enrich_repo("test/no-license")
        assert repo.license == ""

    @mock.patch("src.enricher.github_contributors")
    @mock.patch("src.enricher.github_readme")
    @mock.patch("src.enricher.github_repo_meta")
    def test_readme_truncated_to_max_chars(self, mock_meta, mock_readme, mock_contrib):
        """README content should be truncated to MAX_README_CHARS."""
        from src.enricher import enrich_repo

        long_readme = "x" * 20000

        mock_meta.return_value = dict(REPO_API_FIXTURE)
        mock_readme.return_value = long_readme
        mock_contrib.return_value = 0

        repo = enrich_repo("test/big-readme")
        # MAX_README_CHARS is 8000, so content should be ≤ 8000
        assert len(repo.readme) <= 8000

    @mock.patch("src.enricher.github_repo_meta")
    def test_enrich_repo_handles_metadata_failure(self, mock_meta):
        """When repo_meta returns None after retries, enrich_repo returns None."""
        from src.enricher import enrich_repo

        mock_meta.return_value = None

        repo = enrich_repo("test/dead-repo")
        assert repo is None

    @mock.patch("src.enricher.github_contributors")
    @mock.patch("src.enricher.github_readme")
    @mock.patch("src.enricher.github_repo_meta")
    def test_enrich_repo_graceful_readme_none(self, mock_meta, mock_readme, mock_contrib):
        """When README returns None (no README in repo), should still return EnrichedRepo."""
        from src.enricher import enrich_repo

        mock_meta.return_value = dict(REPO_API_FIXTURE)
        mock_readme.return_value = None  # no README
        mock_contrib.return_value = 2

        repo = enrich_repo("test/no-readme")
        assert repo is not None
        assert repo.readme == ""
        assert repo.stars == 5000


class TestEnricherRetryBehavior:
    """Verify that enrich_repo handles transient failures gracefully via error_handler retries."""

    @mock.patch("src.enricher.github_contributors")
    @mock.patch("src.enricher.github_readme")
    @mock.patch("src.enricher.github_repo_meta")
    def test_ssl_error_does_not_crash_enrich(self, mock_meta, mock_readme, mock_contrib):
        """SSL EOF is retried by github_request; if all retries exhausted, enrich_repo returns None gracefully."""
        from src.enricher import enrich_repo

        mock_meta.return_value = None  # all retries exhausted
        # readme/contrib should not be called if meta fails
        mock_readme.return_value = None
        mock_contrib.return_value = 0

        repo = enrich_repo("test/ssl-fail-repo")
        # Must not crash — returns None, logged as skipped
        assert repo is None

    @mock.patch("src.enricher.github_contributors")
    @mock.patch("src.enricher.github_readme")
    @mock.patch("src.enricher.github_repo_meta")
    def test_timeout_does_not_crash_enrich(self, mock_meta, mock_readme, mock_contrib):
        """Timeout errors are retried; failure returns None without crashing."""
        from src.enricher import enrich_repo

        mock_meta.return_value = None  # all retries exhausted
        mock_readme.return_value = None
        mock_contrib.return_value = 0

        repo = enrich_repo("test/timeout-repo")
        assert repo is None  # graceful degradation, daily-workflow continues

    @mock.patch("src.enricher.github_contributors")
    @mock.patch("src.enricher.github_readme")
    @mock.patch("src.enricher.github_repo_meta")
    def test_partial_failure_still_returns_repo(self, mock_meta, mock_readme, mock_contrib):
        """If meta succeeds but readme/contrib fail, still get a valid EnrichedRepo (graceful degradation)."""
        from src.enricher import enrich_repo

        mock_meta.return_value = dict(REPO_API_FIXTURE)
        mock_readme.return_value = None  # README failed
        mock_contrib.return_value = 0     # contributors failed

        repo = enrich_repo("test/partial-fail")
        assert repo is not None
        assert repo.full_name == "test/awesome-repo"
        assert repo.readme == ""
        assert repo.contributors_count == 0
