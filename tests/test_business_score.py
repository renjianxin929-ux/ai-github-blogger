"""Tests for business_score.py — 6-dimension business value scoring (v4).

New weights: 普通人理解成本15, 企业落地场景25, AI-FDE训练价值20,
             商业服务延展20, 业务流程结合度10, 风险可控性10
"""
from datetime import datetime, timezone

import pytest


def _make_scored(**kwargs):
    from src.scorer import ScoredRepo

    defaults = dict(
        full_name="test/repo",
        name="repo",
        description="An awesome AI tool for automation",
        url="https://github.com/test/repo",
        language="Python",
        stars=5000,
        forks=300,
        updated_at=datetime.now(timezone.utc).isoformat(),
        topics=["AI", "LLM", "agent"],
        license="MIT",
        readme="## Installation\n\n```\nnpm install\n```\n\n## Demo\n\nTry it at demo.example.com",
        contributors_count=5,
        score=85.0,
        subscores={},
        content_type="runnable_project",
        ai_evidence=["ai", "agent"],
        risk_level="none",
    )
    defaults.update(kwargs)
    return ScoredRepo(**defaults)


class TestBusinessScore:
    def test_returns_0_to_100_total(self):
        from src.business_score import score_business_value
        repo = _make_scored()
        result = score_business_value(repo)
        assert 0 <= result.total <= 100

    def test_new_v4_dimension_names(self):
        """v4 uses new dimension names with new weights."""
        from src.business_score import score_business_value
        repo = _make_scored()
        result = score_business_value(repo)
        expected_dims = [
            "understandability", "enterprise_fit",
            "fde_training", "service_extensibility",
            "workflow_integration", "risk_controllability",
        ]
        for dim in expected_dims:
            assert dim in result.subscores, f"Missing dimension: {dim}"
            assert 0 <= result.subscores[dim] <= 10

    def test_deepfake_gets_low_risk_score(self):
        """Requirement: Deep-Live-Cam risk should be reflected."""
        from src.business_score import score_business_value
        repo = _make_scored(
            full_name="hacksider/deep-live-cam",
            description="A deepfake face swap tool for fake webcam",
            topics=["deepfake", "face-swap"],
            readme="Real-time face swap for webcam.",
        )
        result = score_business_value(repo)
        assert result.subscores["risk_controllability"] <= 4, \
            f"Deepfake risk score should be low, got {result.subscores['risk_controllability']}"

    def test_browser_use_gets_high_business_score(self):
        """Requirement: browser-use should get high business value."""
        from src.business_score import score_business_value
        repo = _make_scored(
            full_name="browser-use/browser-use",
            description="Make websites accessible for AI agents. Automate tasks online with ease.",
            stars=96000,
            topics=["ai-agents", "browser-automation", "browser-use", "llm", "playwright"],
            readme="## Installation\n\npip install browser-use\n\n## Quick Start\n\n## Demo\n\nAutomate web tasks with AI agents.",
        )
        result = score_business_value(repo)
        assert result.total >= 50, f"browser-use business score should be high, got {result.total}"

    def test_simple_concept_gets_high_understandability(self):
        from src.business_score import score_business_value
        repo = _make_scored(
            description="一个简单的AI聊天机器人，可以用于客服自动化",
            readme="## 介绍\n\n这是一个AI聊天机器人\n\n## Demo\n\n试试看",
        )
        result = score_business_value(repo)
        assert result.subscores["understandability"] >= 6

    def test_enterprise_signals_boost_score(self):
        from src.business_score import score_business_value
        repo = _make_scored(
            description="RAG-based knowledge base for enterprise customer service automation with API and webhook support",
            topics=["rag", "knowledge-base", "automation", "customer-service"],
        )
        result = score_business_value(repo)
        assert result.subscores["enterprise_fit"] >= 6

    def test_workflow_integration_detected(self):
        from src.business_score import score_business_value
        repo = _make_scored(
            description="n8n workflow automation with webhook triggers and API orchestration",
            topics=["workflow", "automation", "n8n"],
        )
        result = score_business_value(repo)
        assert result.subscores["workflow_integration"] >= 5

    def test_summary_includes_key_phrases(self):
        from src.business_score import score_business_value
        repo = _make_scored()
        result = score_business_value(repo)
        assert len(result.summary) > 20

    def test_complex_concept_penalized(self):
        from src.business_score import score_business_value
        repo = _make_scored(
            description="Distributed consensus protocol with zero-knowledge cryptography and kernel-level compiler optimization",
            readme="## Overview\n\nA complex distributed system.\n\n## Build\n\n```make```\n",
        )
        result = score_business_value(repo)
        assert result.subscores["understandability"] <= 6.5, f"complex project should be penalized, got {result.subscores['understandability']}"
