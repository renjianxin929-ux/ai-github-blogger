"""Tests for dedup.py — deduplication and state management."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest


class TestSlugify:
    """Test repo name sanitization."""

    def test_simple_repo(self):
        """owner/repo → owner__repo."""
        from src.dedup import slugify_repo_name

        assert slugify_repo_name("owner/repo") == "owner__repo"

    def test_nested_org_repo(self):
        """org/repo format works."""
        from src.dedup import slugify_repo_name

        assert slugify_repo_name("browser-use/browser-use") == "browser-use__browser-use"

    def test_hyphenated_names(self):
        """Names with hyphens and dots."""
        from src.dedup import slugify_repo_name

        assert slugify_repo_name("Lum1104/Understand-Anything") == "Lum1104__Understand-Anything"

    def test_no_slash_returns_as_is(self):
        """If no slash, return unchanged."""
        from src.dedup import slugify_repo_name

        assert slugify_repo_name("single-repo") == "single-repo"


class TestLoadState:
    """Test state loading and auto-creation."""

    def test_load_state_creates_empty_when_files_missing(self, tmp_path):
        """When state files don't exist, returns empty state and creates files."""
        from src.dedup import load_state

        state_dir = tmp_path / "state"
        state = load_state(state_dir)

        assert state.seen == {}
        assert state.generated == {}
        assert (state_dir / "seen_repos.json").exists()
        assert (state_dir / "generated_repos.json").exists()

    def test_load_state_reads_existing_files(self, tmp_path):
        """Existing state files should be read correctly."""
        from src.dedup import load_state

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        seen_data = {
            "owner/repo": {
                "first_seen": "2026-05-01T00:00:00",
                "last_seen": "2026-05-20T00:00:00",
                "times_recommended": 3,
            }
        }
        generated_data = {
            "other/repo": {
                "generated_at": "2026-05-19T00:00:00",
                "content_types": ["deep_analysis", "xiaohongshu"],
            }
        }
        (state_dir / "seen_repos.json").write_text(json.dumps(seen_data))
        (state_dir / "generated_repos.json").write_text(json.dumps(generated_data))

        state = load_state(state_dir)

        assert "owner/repo" in state.seen
        assert state.seen["owner/repo"]["times_recommended"] == 3
        assert "other/repo" in state.generated
        assert "deep_analysis" in state.generated["other/repo"]["content_types"]


class TestApplyDedup:
    """Test dedup logic."""

    def _make_repo(self, full_name):
        """Helper to create a minimal EnrichedRepo."""
        from src.enricher import EnrichedRepo
        return EnrichedRepo(
            full_name=full_name,
            name=full_name.split("/")[-1],
            description="test",
            url=f"https://github.com/{full_name}",
            language="Python",
            stars=1000,
            forks=100,
            open_issues=10,
            updated_at="2026-05-29T00:00:00Z",
            created_at="2026-01-01T00:00:00Z",
            topics=["AI", "LLM"],
            license="MIT",
            readme="A test repo README with enough content for scoring.",
            contributors_count=5,
        )

    def _make_state(self, seen=None, generated=None):
        """Helper to create SeenReposState."""
        from src.dedup import SeenReposState
        return SeenReposState(seen=seen or {}, generated=generated or {})

    def test_new_repo_passes_through(self):
        """A repo not in seen or generated should pass through unchanged."""
        from src.dedup import apply_dedup

        repos = [self._make_repo("new/project")]
        state = self._make_state()

        result = apply_dedup(repos, state)
        assert len(result) == 1
        assert result[0].full_name == "new/project"

    def test_generated_repo_is_skipped(self):
        """A repo that already has a content pack should be removed entirely."""
        from src.dedup import apply_dedup

        repos = [self._make_repo("done/project")]
        state = self._make_state(
            generated={"done/project": {"generated_at": "2026-05-29T00:00:00", "content_types": ["deep_analysis"]}}
        )

        result = apply_dedup(repos, state)
        assert len(result) == 0

    def test_recently_seen_repo_is_kept_with_penalty_flag(self):
        """A repo seen within DAYS_TO_DEDUP should be flagged for penalty."""
        from src.dedup import apply_dedup

        today = datetime.now(timezone.utc).isoformat()
        repos = [self._make_repo("seen/repo")]
        state = self._make_state(
            seen={"seen/repo": {"first_seen": today, "last_seen": today, "times_recommended": 1}}
        )

        result = apply_dedup(repos, state)
        assert len(result) == 1
        # Should be marked for penalty (dedup_penalty attribute)
        assert getattr(result[0], "_dedup_penalty", 1.0) == 0.5

    def test_old_seen_repo_no_penalty(self):
        """A repo seen more than DAYS_TO_DEDUP ago should have no penalty."""
        from src.dedup import apply_dedup

        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        repos = [self._make_repo("old/repo")]
        state = self._make_state(
            seen={"old/repo": {"first_seen": old_date, "last_seen": old_date, "times_recommended": 1}}
        )

        result = apply_dedup(repos, state)
        assert len(result) == 1
        assert getattr(result[0], "_dedup_penalty", 1.0) == 1.0


class TestMarkFunctions:
    """Test mark_as_recommended and mark_as_generated."""

    def test_mark_as_recommended_updates_file(self, tmp_path):
        """mark_as_recommended should add entries to seen_repos.json."""
        from src.dedup import mark_as_recommended, load_state

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "seen_repos.json").write_text("{}")
        (state_dir / "generated_repos.json").write_text("{}")

        mark_as_recommended(["test/repo"], state_dir)

        state = load_state(state_dir)
        assert "test/repo" in state.seen
        assert state.seen["test/repo"]["times_recommended"] == 1

    def test_mark_as_recommended_increments_count(self, tmp_path):
        """Second recommendation increments times_recommended."""
        from src.dedup import mark_as_recommended, load_state

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "seen_repos.json").write_text("{}")
        (state_dir / "generated_repos.json").write_text("{}")

        mark_as_recommended(["test/repo"], state_dir)
        mark_as_recommended(["test/repo"], state_dir)

        state = load_state(state_dir)
        assert state.seen["test/repo"]["times_recommended"] == 2

    def test_mark_as_generated_updates_file(self, tmp_path):
        """mark_as_generated should add entries to generated_repos.json."""
        from src.dedup import mark_as_generated, load_state

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "seen_repos.json").write_text("{}")
        (state_dir / "generated_repos.json").write_text("{}")

        mark_as_generated("done/repo", ["deep_analysis", "xiaohongshu"], state_dir)

        state = load_state(state_dir)
        assert "done/repo" in state.generated
        assert state.generated["done/repo"]["content_types"] == ["deep_analysis", "xiaohongshu"]
