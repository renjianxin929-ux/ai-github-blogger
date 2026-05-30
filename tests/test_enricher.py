"""Tests for enricher.py — GitHub API metadata fetching."""
import base64
import json
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

README_FIXTURE = {
    "content": base64.b64encode(b"# Awesome Repo\n\nThis is a comprehensive AI framework.\n" * 50).decode(),
    "encoding": "base64",
}

CONTRIBUTORS_FIXTURE = [{}, {}, {}, {}, {}]  # 5 contributors


class TestEnrichRepo:
    """Test the enrich_repo function."""

    @mock.patch("src.enricher.requests.get")
    def test_enrich_repo_returns_full_data(self, mock_get):
        """Should fetch and combine repo metadata, README, and contributors."""
        from src.enricher import enrich_repo

        # Set up three mock responses: repo info, readme, contributors
        mock_repo_resp = mock.MagicMock()
        mock_repo_resp.status_code = 200
        mock_repo_resp.json.return_value = REPO_API_FIXTURE
        mock_repo_resp.raise_for_status = lambda: None

        mock_readme_resp = mock.MagicMock()
        mock_readme_resp.status_code = 200
        mock_readme_resp.json.return_value = README_FIXTURE
        mock_readme_resp.raise_for_status = lambda: None

        mock_contrib_resp = mock.MagicMock()
        mock_contrib_resp.status_code = 200
        mock_contrib_resp.json.return_value = CONTRIBUTORS_FIXTURE
        mock_contrib_resp.raise_for_status = lambda: None

        mock_get.side_effect = [mock_repo_resp, mock_readme_resp, mock_contrib_resp]

        repo = enrich_repo("test/awesome-repo")

        assert repo.full_name == "test/awesome-repo"
        assert repo.stars == 5000
        assert repo.forks == 300
        assert repo.license == "MIT"
        assert repo.topics == ["AI", "LLM", "agent"]
        assert len(repo.readme) > 200
        assert repo.contributors_count == 5

    @mock.patch("src.enricher.requests.get")
    def test_enrich_repo_handles_missing_license(self, mock_get):
        """REPOS with no license should have empty string."""
        from src.enricher import enrich_repo

        no_license = dict(REPO_API_FIXTURE)
        no_license["license"] = None

        mock_repo = mock.MagicMock()
        mock_repo.status_code = 200
        mock_repo.json.return_value = no_license
        mock_repo.raise_for_status = lambda: None

        mock_readme = mock.MagicMock()
        mock_readme.status_code = 200
        mock_readme.json.return_value = README_FIXTURE
        mock_readme.raise_for_status = lambda: None

        mock_contrib = mock.MagicMock()
        mock_contrib.status_code = 200
        mock_contrib.json.return_value = CONTRIBUTORS_FIXTURE
        mock_contrib.raise_for_status = lambda: None

        mock_get.side_effect = [mock_repo, mock_readme, mock_contrib]

        repo = enrich_repo("test/no-license")
        assert repo.license == ""

    @mock.patch("src.enricher.requests.get")
    def test_readme_truncated_to_max_chars(self, mock_get):
        """README content should be truncated to MAX_README_CHARS."""
        from src.enricher import enrich_repo

        long_readme = base64.b64encode(b"x" * 20000).decode()
        readme_fix = {"content": long_readme, "encoding": "base64"}

        mock_repo = mock.MagicMock()
        mock_repo.status_code = 200
        mock_repo.json.return_value = REPO_API_FIXTURE
        mock_repo.raise_for_status = lambda: None

        mock_readme = mock.MagicMock()
        mock_readme.status_code = 200
        mock_readme.json.return_value = readme_fix
        mock_readme.raise_for_status = lambda: None

        mock_contrib = mock.MagicMock()
        mock_contrib.status_code = 200
        mock_contrib.json.return_value = CONTRIBUTORS_FIXTURE
        mock_contrib.raise_for_status = lambda: None

        mock_get.side_effect = [mock_repo, mock_readme, mock_contrib]

        repo = enrich_repo("test/big-readme")
        # MAX_README_CHARS is 8000, so content should be ≤ 8000
        assert len(repo.readme) <= 8000
