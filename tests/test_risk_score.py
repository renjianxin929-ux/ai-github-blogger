"""Tests for risk_score.py — 8-dimension risk assessment (v4)."""
from datetime import datetime, timezone

import pytest


def _make_scored(**kwargs):
    from src.scorer import ScoredRepo

    defaults = dict(
        full_name="test/repo",
        name="repo",
        description="A useful AI tool.",
        url="https://github.com/test/repo",
        language="Python",
        stars=5000,
        forks=300,
        updated_at=datetime.now(timezone.utc).isoformat(),
        topics=["AI", "LLM"],
        license="MIT",
        readme="## Overview\n\nA helpful tool.\n",
        contributors_count=5,
        score=80.0,
        subscores={},
        content_type="runnable_project",
        ai_evidence=["ai"],
        risk_level="none",
    )
    defaults.update(kwargs)
    return ScoredRepo(**defaults)


class TestRiskProfile:
    def test_normal_repo_is_low_risk(self):
        from src.risk_score import assess_risk
        repo = _make_scored()
        profile = assess_risk(repo)
        assert profile.overall == "low"
        assert not profile.blocked

    def test_deepfake_is_blocked(self):
        """Requirement: Deep-Live-Cam should be blocked."""
        from src.risk_score import assess_risk
        repo = _make_scored(
            full_name="hacksider/deep-live-cam",
            description="Real-time face swap and deepfake webcam",
            topics=["deepfake", "face-swap"],
            readme="Deepfake webcam for real-time face swap.",
        )
        profile = assess_risk(repo)
        assert profile.blocked
        assert profile.overall == "blocked"

    def test_browser_use_gets_medium_automation_risk(self):
        """Requirement: browser-use should get specific risk warnings."""
        from src.risk_score import assess_risk
        repo = _make_scored(
            full_name="browser-use/browser-use",
            description="Make websites accessible for AI agents. Browser automation.",
            topics=["browser-use", "browser-automation", "ai-agents"],
            readme="## Overview\n\nAutomate browser tasks with AI agents.\n\nSupports login, session, cookie management.",
        )
        profile = assess_risk(repo)
        assert profile.account_automation_risk == "medium"
        assert len(profile.warnings) >= 1
        assert any("浏览器自动化" in w for w in profile.warnings)
        assert len(profile.must_include_disclaimers) >= 1

    def test_no_license_is_medium_risk(self):
        from src.risk_score import assess_risk
        repo = _make_scored(license="")
        profile = assess_risk(repo)
        assert profile.license_risk == "medium"

    def test_mit_license_is_low_risk(self):
        from src.risk_score import assess_risk
        repo = _make_scored(license="MIT")
        profile = assess_risk(repo)
        assert profile.license_risk == "low"

    def test_gpl_license_is_medium_risk(self):
        from src.risk_score import assess_risk
        repo = _make_scored(license="GPL-3.0")
        profile = assess_risk(repo)
        assert profile.license_risk == "medium"

    def test_hype_description_is_medium_risk(self):
        from src.risk_score import assess_risk
        repo = _make_scored(
            description="The revolutionary game-changer that will disrupt everything",
        )
        profile = assess_risk(repo)
        assert profile.hype_risk == "medium"

    def test_blocked_returns_selection_penalty_zero(self):
        from src.risk_score import assess_risk
        repo = _make_scored(
            description="deepfake face swap tool",
            topics=["deepfake"],
        )
        profile = assess_risk(repo)
        assert profile.to_selection_penalty() == 0.0

    def test_low_risk_returns_selection_penalty_one(self):
        from src.risk_score import assess_risk
        repo = _make_scored()
        profile = assess_risk(repo)
        assert profile.to_selection_penalty() == 1.0

    def test_risk_outputs_specific_reasons(self):
        """Requirement: risk_score must output specific risk reasons."""
        from src.risk_score import assess_risk
        repo = _make_scored(
            full_name="browser-use/browser-use",
            description="AI agent browser automation with login support",
            topics=["browser-use", "automation"],
            readme="Automate browser tasks. Supports login and session.",
        )
        profile = assess_risk(repo)
        # Should have specific warnings, not just "no risk"
        assert len(profile.warnings) >= 1 or profile.overall != "low"

    def test_all_eight_dimensions_present(self):
        from src.risk_score import assess_risk
        repo = _make_scored()
        profile = assess_risk(repo)
        # All 8 dimensions should be set
        assert profile.license_risk in ("low", "medium", "high")
        assert profile.data_privacy_risk in ("low", "medium", "high")
        assert profile.account_automation_risk in ("low", "medium", "high")
        assert profile.scraping_platform_risk in ("low", "medium", "high")
        assert profile.deepfake_impersonation_risk in ("low", "medium", "high")
        assert profile.spam_phishing_malware_risk in ("low", "medium", "high")
        assert profile.hype_risk in ("low", "medium", "high")
        assert profile.client_misuse_risk in ("low", "medium", "high")
