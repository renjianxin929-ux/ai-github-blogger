"""Tests for scorer.py — repo_selection_score (v4) + classification/filtering.

Tests cover: 7-dimension repo_selection_score, content classification,
AI eligibility gate, high-risk detection, evergreen demotion, pool routing.
"""
from datetime import datetime, timedelta, timezone

import pytest


def _make_repo(
    full_name="test/repo",
    stars=1000,
    updated_at=None,
    topics=None,
    readme="",
    description="A test repo for scoring.",
    forks=100,
    contributors=5,
    license_str="MIT",
    dedup_penalty=1.0,
):
    from src.enricher import EnrichedRepo

    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat()
    if topics is None:
        topics = ["AI", "LLM"]

    return EnrichedRepo(
        full_name=full_name,
        name=full_name.split("/")[-1],
        description=description,
        url=f"https://github.com/{full_name}",
        language="Python",
        stars=stars,
        forks=forks,
        open_issues=5,
        updated_at=updated_at,
        created_at="2025-01-01T00:00:00Z",
        topics=topics,
        license=license_str,
        readme=readme,
        contributors_count=contributors,
        _dedup_penalty=dedup_penalty,
    )


def _make_scored(
    full_name="test/repo",
    stars=5000,
    score=85.0,
    topics=None,
    readme="# Test\n\nSome content here for testing.",
    description="An awesome AI tool for testing.",
    content_type="runnable_project",
    ai_evidence=None,
    risk_level="none",
):
    from src.scorer import ScoredRepo

    if topics is None:
        topics = ["AI", "LLM", "agent"]
    if ai_evidence is None:
        ai_evidence = ["ai", "agent", "llm"]

    return ScoredRepo(
        full_name=full_name,
        name=full_name.split("/")[-1],
        description=description,
        url=f"https://github.com/{full_name}",
        language="Python",
        stars=stars,
        forks=300,
        updated_at=datetime.now(timezone.utc).isoformat(),
        topics=topics,
        license="MIT",
        readme=readme,
        contributors_count=5,
        score=score,
        subscores={
            "ai_relevance": 18, "recency": 12, "clarity": 12,
            "runnability": 12, "tellability": 12, "community": 7,
            "risk_controllable": 8,
        },
        content_type=content_type,
        ai_evidence=ai_evidence,
        risk_level=risk_level,
    )


# ═════════════════════════════════════════════════════════════════════════════
# v4 — repo_selection_score dimensions
# ═════════════════════════════════════════════════════════════════════════════

class TestSelectionScore:
    def test_score_returns_0_to_100_range(self):
        from src.scorer import score_repo
        repo = _make_repo(stars=5000, readme="# Awesome\n\n" + "x" * 1000)
        scored = score_repo(repo)
        assert 0 <= scored.score <= 100

    def test_dedup_penalty_reduces_score(self):
        from src.scorer import score_repo
        normal = score_repo(_make_repo(full_name="a/b", dedup_penalty=1.0))
        penalized = score_repo(_make_repo(full_name="a/b", dedup_penalty=0.5))
        assert abs(penalized.score - normal.score * 0.5) < 0.01

    def test_new_dimension_names(self):
        """v4 uses new 7-dimension names."""
        from src.scorer import score_repo
        repo = _make_repo(full_name="test/agent-app", topics=["agent", "rag", "mcp"],
                          description="An AI agent with RAG and MCP support")
        scored = score_repo(repo)
        assert "ai_relevance" in scored.subscores
        assert "recency" in scored.subscores
        assert "clarity" in scored.subscores
        assert "runnability" in scored.subscores
        assert "tellability" in scored.subscores
        assert "community" in scored.subscores
        assert "risk_controllable" in scored.subscores

    def test_ai_agent_gets_high_ai_relevance(self):
        from src.scorer import score_repo
        repo = _make_repo(
            full_name="test/browser-use",
            description="Browser automation for AI agents",
            topics=["agent", "browser-use", "automation", "ai"],
        )
        scored = score_repo(repo)
        assert scored.subscores["ai_relevance"] >= 12

    def test_recency_scores_high_for_recent(self):
        from src.scorer import score_repo
        recent = datetime.now(timezone.utc).isoformat()
        repo = _make_repo(full_name="a/b", updated_at=recent)
        scored = score_repo(repo)
        assert scored.subscores["recency"] >= 12

    def test_recency_scores_zero_for_stale(self):
        from src.scorer import score_repo
        stale = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        repo = _make_repo(full_name="a/b", updated_at=stale)
        scored = score_repo(repo)
        assert scored.subscores["recency"] == 0

    def test_browser_use_gets_high_score(self):
        """Requirement: browser-use should get high selection score."""
        from src.scorer import score_repo
        readme = "## Installation\n\n```\npip install browser-use\n```\n\n## Quick Start\n\n```python\nfrom browser_use import Agent\n```\n\n## Demo\n\nCheck out the live demo at demo.browser-use.com"
        repo = _make_repo(
            full_name="browser-use/browser-use",
            description="Make websites accessible for AI agents. Automate tasks online with ease.",
            stars=96000,
            topics=["ai-agents", "browser-automation", "browser-use", "llm", "playwright"],
            readme=readme,
            contributors=5,
            forks=10000,
        )
        scored = score_repo(repo)
        assert scored.score >= 60, f"browser-use should get high score, got {scored.score}"


# ═════════════════════════════════════════════════════════════════════════════
# v3/v4 — High-risk detection (unchanged logic)
# ═════════════════════════════════════════════════════════════════════════════

class TestCheckHighRisk:
    def test_detects_deepfake(self):
        from src.scorer import check_high_risk
        repo = _make_repo(
            full_name="hacksider/deep-live-cam",
            description="Real-time face swap and deepfake webcam",
            topics=["deepfake", "face-swap"],
        )
        is_risk, hits = check_high_risk(repo)
        assert is_risk
        assert "deepfake" in hits

    def test_detects_phishing(self):
        from src.scorer import check_high_risk
        repo = _make_repo(
            full_name="evil/phishing-tool",
            description="A phishing toolkit for credential harvesting",
        )
        is_risk, hits = check_high_risk(repo)
        assert is_risk
        assert "phishing" in hits or "credential" in hits

    def test_normal_repo_is_not_high_risk(self):
        from src.scorer import check_high_risk
        repo = _make_repo(
            full_name="good/ai-agent",
            description="A helpful AI agent framework",
            topics=["ai", "agent"],
        )
        is_risk, hits = check_high_risk(repo)
        assert not is_risk

    def test_detects_high_risk_in_readme(self):
        from src.scorer import check_high_risk
        repo = _make_repo(
            full_name="test/tool",
            description="A useful tool",
            topics=["automation"],
            readme="This tool can be used for deepfake detection bypass...",
        )
        is_risk, _ = check_high_risk(repo)
        assert is_risk


# ═════════════════════════════════════════════════════════════════════════════
# AI eligibility gate
# ═════════════════════════════════════════════════════════════════════════════

class TestCheckAIEligibility:
    def test_ai_repo_passes(self):
        from src.scorer import check_ai_eligibility
        repo = _make_repo(
            full_name="test/ai-agent",
            description="An AI-powered agent framework with RAG support",
            topics=["ai", "llm", "agent"],
        )
        is_ai, evidence = check_ai_eligibility(repo)
        assert is_ai
        assert len(evidence) >= 2

    def test_non_ai_repo_fails(self):
        from src.scorer import check_ai_eligibility
        repo = _make_repo(
            full_name="Snailclimb/JavaGuide",
            description="Java 面试 & 后端通用面试指南",
            topics=["java", "interview"],
        )
        is_ai, evidence = check_ai_eligibility(repo)
        assert not is_ai

    def test_java_interview_disqualifies(self):
        from src.scorer import check_ai_eligibility
        repo = _make_repo(
            full_name="test/java面试宝典",
            description="Java 面试题库和算法题",
            topics=["java", "leetcode"],
        )
        is_ai, evidence = check_ai_eligibility(repo)
        assert not is_ai


# ═════════════════════════════════════════════════════════════════════════════
# Content type classification
# ═════════════════════════════════════════════════════════════════════════════

class TestClassifyContentType:
    def test_classifies_deepfake_as_high_risk(self):
        from src.scorer import classify_content_type
        repo = _make_repo(
            full_name="hacksider/deep-live-cam",
            description="Real-time face swap and deepfake webcam",
            topics=["deepfake"],
        )
        assert classify_content_type(repo) == "high_risk"

    def test_classifies_awesome_list(self):
        from src.scorer import classify_content_type
        repo = _make_repo(
            full_name="Shubhamsaboo/awesome-llm-apps",
            description="A curated list of awesome LLM apps",
            topics=["awesome-list", "llm"],
        )
        ct = classify_content_type(repo)
        assert ct in ("awesome_list", "runnable_project")

    def test_classifies_known_evergreen_as_framework(self):
        from src.scorer import classify_content_type
        repo = _make_repo(
            full_name="langgenius/dify",
            description="Production-ready platform for agentic workflow development",
            topics=["ai", "low-code", "orchestration", "workflow"],
        )
        ct = classify_content_type(repo)
        assert ct == "framework_tool"

    def test_classifies_runnable_project(self):
        from src.scorer import classify_content_type
        readme = "## Installation\n\n```\nnpm install my-tool\n```\n\n## Quick Start\n\n```\nnpm start\n```"
        repo = _make_repo(
            full_name="test/cool-app",
            description="A cool AI application",
            topics=["ai", "agent", "rag"],
            readme=readme,
        )
        ct = classify_content_type(repo)
        assert ct == "runnable_project"


# ═════════════════════════════════════════════════════════════════════════════
# Evergreen demotion
# ═════════════════════════════════════════════════════════════════════════════

class TestCheckEvergreenDemotion:
    def test_under_50k_not_demoted(self):
        from src.scorer import check_evergreen_demotion
        repo = _make_scored(stars=30000)
        should, reason = check_evergreen_demotion(repo)
        assert not should

    def test_known_evergreen_always_demoted(self):
        """Requirement: Dify/n8n/LangChain should go to evergreen pool."""
        from src.scorer import check_evergreen_demotion
        # Dify
        dify = _make_scored(full_name="langgenius/dify", stars=150000)
        should, _ = check_evergreen_demotion(dify)
        assert should
        # n8n
        n8n = _make_scored(full_name="n8n-io/n8n", stars=80000)
        should, _ = check_evergreen_demotion(n8n)
        assert should
        # LangChain
        lc = _make_scored(full_name="langchain-ai/langchain", stars=110000)
        should, _ = check_evergreen_demotion(lc)
        assert should

    def test_dify_goes_to_evergreen_pool(self):
        """Requirement: Dify should be in evergreen pool."""
        from src.scorer import apply_classification_and_filters
        repo = _make_scored(
            full_name="langgenius/dify", stars=150000, score=49,
            description="Production-ready platform for agentic workflow",
            topics=["ai", "low-code", "workflow", "orchestration"],
            content_type="framework_tool", ai_evidence=["ai", "workflow"],
        )
        repo.updated_at = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        result = apply_classification_and_filters([repo])
        assert len(result["evergreen_candidates"]) >= 1, f"Dify should go to evergreen pool, got: {result}"
        assert result["runnable_top5"] == []


# ═════════════════════════════════════════════════════════════════════════════
# Pool routing (v4)
# ═════════════════════════════════════════════════════════════════════════════

class TestApplyClassificationAndFilters:
    def test_high_risk_goes_to_blocked(self):
        """Requirement: Deep-Live-Cam should be blocked."""
        from src.scorer import apply_classification_and_filters
        repo = _make_scored(
            full_name="hacksider/deep-live-cam",
            score=90,
            description="deepfake face swap webcam",
            topics=["deepfake"],
            content_type="high_risk",
        )
        result = apply_classification_and_filters([repo])
        assert len(result["high_risk_skipped"]) >= 1
        assert result["high_risk_skipped"][0].pool == "blocked"
        assert result["runnable_top5"] == []

    def test_runnable_goes_to_top5_pool(self):
        from src.scorer import apply_classification_and_filters
        readme = "## Installation\n\npip install\n\n## Quick Start"
        repo = _make_scored(
            full_name="good/ai-app", score=85,
            description="An AI agent for automation",
            topics=["ai", "agent", "rag"],
            content_type="runnable_project",
            ai_evidence=["ai", "agent", "rag"],
            readme=readme,
        )
        result = apply_classification_and_filters([repo])
        assert len(result["runnable_top5"]) >= 1

    def test_awesome_list_goes_to_resource(self):
        """Requirement: awesome-llm-apps should go to resource pool."""
        from src.scorer import apply_classification_and_filters
        repo = _make_scored(
            full_name="Shubhamsaboo/awesome-llm-apps", score=70,
            description="A curated list of awesome LLM apps",
            topics=["awesome-list", "ai"],
            content_type="awesome_list", ai_evidence=["ai"],
        )
        result = apply_classification_and_filters([repo])
        assert len(result["resource_candidates"]) >= 1
        assert result["runnable_top5"] == []

    def test_java_guide_not_in_top5(self):
        """Requirement: JavaGuide should not enter Top 5."""
        from src.scorer import apply_classification_and_filters
        repo = _make_scored(
            full_name="Snailclimb/JavaGuide", score=75,
            description="Java 面试指南",
            topics=["java", "interview"],
            content_type="tutorial_guide", ai_evidence=[],
        )
        result = apply_classification_and_filters([repo])
        assert repo.full_name not in [r.full_name for r in result["runnable_top5"]]

    def test_empty_input(self):
        from src.scorer import apply_classification_and_filters
        result = apply_classification_and_filters([])
        assert result["runnable_top5"] == []
        assert result["high_risk_skipped"] == []


# ═════════════════════════════════════════════════════════════════════════════
# Rank repos
# ═════════════════════════════════════════════════════════════════════════════

class TestRankRepos:
    def test_rank_sorts_descending_by_score(self):
        from src.scorer import rank_repos, score_repo
        recent = datetime.now(timezone.utc).isoformat()
        repos = [
            score_repo(_make_repo(full_name="a/low", stars=10, updated_at=recent)),
            score_repo(_make_repo(full_name="b/high", stars=5000, updated_at=recent)),
            score_repo(_make_repo(full_name="c/mid", stars=1000, updated_at=recent)),
        ]
        ranked = rank_repos(repos)
        assert ranked[0].full_name == "b/high"
        assert ranked[-1].full_name == "a/low"

    def test_rank_empty_returns_empty(self):
        from src.scorer import rank_repos
        assert rank_repos([]) == []
