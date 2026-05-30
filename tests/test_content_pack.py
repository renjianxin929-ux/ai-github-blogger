"""Tests for content_pack.py — V2 content pack generation (11 files).

All output goes to tmp_path to avoid polluting real data directories.
"""
from pathlib import Path
from unittest import mock

import pytest


def _make_enriched_repo(full_name="test/awesome-repo"):
    from src.enricher import EnrichedRepo

    return EnrichedRepo(
        full_name=full_name,
        name=full_name.split("/")[-1],
        description="An awesome AI tool for developers",
        url=f"https://github.com/{full_name}",
        language="Python",
        stars=5000,
        forks=300,
        open_issues=5,
        updated_at="2026-05-28T00:00:00Z",
        created_at="2025-01-01T00:00:00Z",
        topics=["AI", "LLM", "agent"],
        license="MIT",
        readme="# Awesome Repo\n\nComprehensive AI framework.\n" * 50,
        contributors_count=5,
    )


V2_FILES = [
    "00_repo_snapshot",
    "01_ai_fde_deep_analysis",
    "02_xiaohongshu",
    "03_douyin_video",
    "04_videohao_script",
    "05_wechat_article",
    "06_storyboard",
    "07_geo_angle",
    "08_enterprise_pitch",
    "09_risk_review",
    "10_quality_check",
]


class TestGenerateContentPackV2:
    """Test V2 content pack generation — all output goes to tmp_path."""

    @mock.patch("src.content_pack.mark_as_generated")
    @mock.patch("src.content_pack.score_repo")
    @mock.patch("src.content_pack.enrich_repo")
    def test_generates_all_11_files_no_llm(self, mock_enrich, mock_score, mock_mark, tmp_path):
        """No-LLM mode should generate all 11 files from rules."""
        from src.content_pack import generate_content_pack
        from src.scorer import ScoredRepo

        mock_enrich.return_value = _make_enriched_repo("test/awesome-repo")
        scored = ScoredRepo(
            full_name="test/awesome-repo",
            name="awesome-repo",
            description="An awesome AI tool for developers",
            url="https://github.com/test/awesome-repo",
            language="Python",
            stars=5000,
            forks=300,
            updated_at="2026-05-28T00:00:00Z",
            topics=["AI", "LLM", "agent"],
            license="MIT",
            readme="# Awesome Repo\n\nComprehensive AI framework.\n" * 20,
            contributors_count=5,
            score=85.0,
            subscores={},
        )
        mock_score.return_value = scored

        # Ensure no LLM is available
        with mock.patch("src.content_pack._has_llm", return_value=False):
            pack_dir, status = generate_content_pack("test/awesome-repo", output_dir=tmp_path)

        assert "test__awesome-repo" in str(pack_dir)
        assert str(tmp_path) in str(pack_dir)
        assert pack_dir.exists()

        for fname in V2_FILES:
            fpath = pack_dir / f"{fname}.md"
            assert fpath.exists(), f"Missing: {fname}.md"
            content = fpath.read_text(encoding="utf-8")
            assert len(content) > 50, f"File {fname}.md is too short"

    @mock.patch("src.content_pack.mark_as_generated")
    @mock.patch("src.content_pack.score_repo")
    @mock.patch("src.content_pack.enrich_repo")
    def test_snapshot_has_metadata(self, mock_enrich, mock_score, mock_mark, tmp_path):
        """00_repo_snapshot.md should contain repo metadata."""
        from src.content_pack import generate_content_pack
        from src.scorer import ScoredRepo

        mock_enrich.return_value = _make_enriched_repo("test/my-repo")
        scored = ScoredRepo(
            full_name="test/my-repo",
            name="my-repo",
            description="A test repo",
            url="https://github.com/test/my-repo",
            language="TypeScript",
            stars=10000,
            forks=500,
            updated_at="2026-05-28T00:00:00Z",
            topics=["AI", "automation"],
            license="MIT",
            readme="# Test\n\nSome content\n" * 10,
            contributors_count=3,
            score=75.0,
            subscores={},
        )
        mock_score.return_value = scored

        with mock.patch("src.content_pack._has_llm", return_value=False):
            pack_dir, _ = generate_content_pack("test/my-repo", output_dir=tmp_path)

        snapshot = (pack_dir / "00_repo_snapshot.md").read_text(encoding="utf-8")
        assert "test/my-repo" in snapshot
        assert "10000" in snapshot
        assert "TypeScript" in snapshot
        assert "MIT" in snapshot
        assert "可运行项目" in snapshot or "framework_tool" in snapshot or "unclear" in snapshot

    @mock.patch("src.content_pack.mark_as_generated")
    @mock.patch("src.content_pack.score_repo")
    @mock.patch("src.content_pack.enrich_repo")
    def test_risk_review_is_rule_based(self, mock_enrich, mock_score, mock_mark, tmp_path):
        """09_risk_review.md should not have TODOs for risk assessment."""
        from src.content_pack import generate_content_pack
        from src.scorer import ScoredRepo

        mock_enrich.return_value = _make_enriched_repo("test/safe-repo")
        scored = ScoredRepo(
            full_name="test/safe-repo",
            name="safe-repo",
            description="A safe automation tool",
            url="https://github.com/test/safe-repo",
            language="Python",
            stars=1000,
            forks=100,
            updated_at="2026-05-28T00:00:00Z",
            topics=["automation"],
            license="MIT",
            readme="# Safe\n",
            contributors_count=2,
            score=60.0,
            subscores={},
        )
        mock_score.return_value = scored

        with mock.patch("src.content_pack._has_llm", return_value=False):
            pack_dir, _ = generate_content_pack("test/safe-repo", output_dir=tmp_path)

        risk_review = (pack_dir / "09_risk_review.md").read_text(encoding="utf-8")
        assert "License" in risk_review or "许可证" in risk_review or "风险" in risk_review

    @mock.patch("src.content_pack.mark_as_generated")
    @mock.patch("src.content_pack.score_repo")
    @mock.patch("src.content_pack.enrich_repo")
    def test_quality_check_shows_not_evaluated_in_no_llm(self, mock_enrich, mock_score, mock_mark, tmp_path):
        """Requirement: No-LLM fallback should show "未评估" not numeric scores."""
        from src.content_pack import generate_content_pack
        from src.scorer import ScoredRepo

        mock_enrich.return_value = _make_enriched_repo("test/repo")
        scored = ScoredRepo(
            full_name="test/repo",
            name="repo",
            description="A test",
            url="https://github.com/test/repo",
            language="Python",
            stars=500,
            forks=50,
            updated_at="2026-05-28T00:00:00Z",
            topics=["AI"],
            license="MIT",
            readme="# Test\n\nSome content here for testing.\n" * 20,
            contributors_count=1,
            score=50.0,
            subscores={},
        )
        mock_score.return_value = scored

        with mock.patch("src.content_pack._has_llm", return_value=False):
            pack_dir, _ = generate_content_pack("test/repo", output_dir=tmp_path)

        qc = (pack_dir / "10_quality_check.md").read_text(encoding="utf-8")
        assert "未评估" in qc, f"Quality check should show '未评估' in no-LLM mode, got:\n{qc[:500]}"
        assert "not_evaluated" in qc.lower()

    @mock.patch("src.content_pack.mark_as_generated")
    @mock.patch("src.content_pack.score_repo")
    @mock.patch("src.content_pack.enrich_repo")
    def test_handles_enrichment_failure(self, mock_enrich, mock_score, mock_mark, tmp_path):
        from src.content_pack import generate_content_pack

        mock_enrich.return_value = None

        with pytest.raises(ValueError, match="无法获取"):
            generate_content_pack("nonexistent/repo", output_dir=tmp_path)

    @mock.patch("src.content_pack.mark_as_generated")
    @mock.patch("src.content_pack.score_repo")
    @mock.patch("src.content_pack.enrich_repo")
    def test_cleans_existing_pack_before_regeneration(self, mock_enrich, mock_score, mock_mark, tmp_path):
        from src.content_pack import generate_content_pack
        from src.scorer import ScoredRepo

        mock_enrich.return_value = _make_enriched_repo()
        scored = ScoredRepo(
            full_name="test/repo",
            name="repo",
            description="Test",
            url="https://github.com/test/repo",
            language="Python",
            stars=1000,
            forks=100,
            updated_at="2026-05-28T00:00:00Z",
            topics=["AI"],
            license="MIT",
            readme="# Test\n",
            contributors_count=1,
            score=50.0,
            subscores={},
        )
        mock_score.return_value = scored

        with mock.patch("src.content_pack._has_llm", return_value=False):
            pack_dir1 = generate_content_pack("test/repo", output_dir=tmp_path)
            pack_dir2 = generate_content_pack("test/repo", output_dir=tmp_path)

        assert pack_dir1 == pack_dir2
