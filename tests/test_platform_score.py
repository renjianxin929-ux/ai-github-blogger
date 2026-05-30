"""Tests for platform_score.py — per-platform fit scoring (v4)."""
from datetime import datetime, timezone

import pytest


def _make_scored(**kwargs):
    from src.scorer import ScoredRepo

    defaults = dict(
        full_name="test/repo",
        name="repo",
        description="An AI agent tool.",
        url="https://github.com/test/repo",
        language="Python",
        stars=5000,
        forks=300,
        updated_at=datetime.now(timezone.utc).isoformat(),
        topics=["AI", "LLM", "agent"],
        license="MIT",
        readme="## Overview\n\nAn AI agent tool.\n",
        contributors_count=5,
        score=80.0,
        subscores={},
        content_type="runnable_project",
        ai_evidence=["ai"],
        risk_level="none",
    )
    defaults.update(kwargs)
    return ScoredRepo(**defaults)


class TestPlatformFitScore:
    def test_all_five_platforms_present(self):
        from src.platform_score import score_platform_fit
        repo = _make_scored()
        pf = score_platform_fit(repo)
        assert 0 <= pf.xiaohongshu <= 100
        assert 0 <= pf.douyin <= 100
        assert 0 <= pf.videohao <= 100
        assert 0 <= pf.wechat <= 100
        assert 0 <= pf.geo_trade <= 100

    def test_best_platform_is_set(self):
        from src.platform_score import score_platform_fit
        repo = _make_scored()
        pf = score_platform_fit(repo)
        assert pf.best_platform in ("小红书", "抖音", "视频号", "公众号", "外贸/GEO")
        assert pf.best_platform_score > 0

    def test_geo_repo_scores_high_on_geo(self):
        from src.platform_score import score_platform_fit
        repo = _make_scored(
            description="AI search engine optimization and GEO automation tool for cross-border ecommerce",
            topics=["geo", "seo", "ai-search", "automation"],
        )
        pf = score_platform_fit(repo)
        assert pf.geo_trade >= 70, f"GEO repo should score high on geo, got {pf.geo_trade}"

    def test_non_geo_repo_gets_cant_hard_rub_verdict(self):
        from src.platform_score import score_platform_fit
        repo = _make_scored(
            description="A generic markdown parser",
            topics=["markdown", "parser"],
            readme="Parses markdown to HTML.",
        )
        pf = score_platform_fit(repo)
        assert "不能硬蹭" in pf.geo_verdict

    def test_visual_demo_boosts_xiaohongshu(self):
        from src.platform_score import score_platform_fit
        repo = _make_scored(
            description="A visual AI dashboard with demo and screenshots",
            readme="## Demo\n\nTry our live demo!\n\n![screenshot](img.png)\n\n## Video Tutorial",
            topics=["ai", "dashboard", "visual"],
        )
        pf = score_platform_fit(repo)
        assert pf.xhs_visual >= 7, f"Visual demo should boost XHS visual score, got {pf.xhs_visual}"

    def test_hook_signals_boost_douyin(self):
        from src.platform_score import score_platform_fit
        repo = _make_scored(
            description="One-click AI agent browser automation tool for real-time web scraping",
            topics=["agent", "browser-use", "automation"],
        )
        pf = score_platform_fit(repo)
        assert pf.dy_hook >= 7, f"Hook signals should boost Douyin, got {pf.dy_hook}"

    def test_enterprise_signals_boost_videohao(self):
        from src.platform_score import score_platform_fit
        repo = _make_scored(
            description="Enterprise business automation SaaS with API integration",
            topics=["automation", "business", "api", "saas"],
            readme="## Enterprise Features\n\n- Workflow automation\n- API integration",
        )
        pf = score_platform_fit(repo)
        assert pf.vh_business >= 7, f"Enterprise signals should boost VideoHao, got {pf.vh_business}"

    def test_deep_readme_boosts_wechat(self):
        from src.platform_score import score_platform_fit
        long_readme = "# Architecture\n\n" + "Design patterns and methodology.\n" * 50
        repo = _make_scored(
            description="RAG agent framework with deep architecture design",
            topics=["rag", "agent", "mcp"],
            readme=long_readme,
        )
        pf = score_platform_fit(repo)
        assert pf.wx_depth >= 7, f"Deep README should boost WeChat, got {pf.wx_depth}"

    def test_browser_use_gets_good_platform_scores(self):
        """browser-use should have reasonable platform scores across all platforms."""
        from src.platform_score import score_platform_fit
        repo = _make_scored(
            full_name="browser-use/browser-use",
            description="Make websites accessible for AI agents. Automate tasks online with ease.",
            stars=96000,
            topics=["ai-agents", "browser-automation", "browser-use", "llm", "playwright"],
            readme="## Demo\n\n![demo](demo.gif)\n\n## Quick Start\n\npip install browser-use\n",
        )
        pf = score_platform_fit(repo)
        # Should have decent scores on at least some platforms
        assert max(pf.xiaohongshu, pf.douyin, pf.videohao, pf.wechat, pf.geo_trade) >= 50
