"""Tests for report.py — daily report generation (v4 4-layer scoring structure)."""
import re
from datetime import datetime

import pytest


def _make_scored_repo(full_name="test/repo", stars=5000, score=85.0, readme="# Test\n\nContent here",
                      content_type="runnable_project", ai_evidence=None, risk_level="none"):
    from src.scorer import ScoredRepo

    if ai_evidence is None:
        ai_evidence = ["ai", "agent"]

    return ScoredRepo(
        full_name=full_name,
        name=full_name.split("/")[-1],
        description="An awesome AI tool",
        url=f"https://github.com/{full_name}",
        language="Python",
        stars=stars,
        forks=300,
        updated_at=datetime.now().isoformat(),
        topics=["AI", "LLM", "agent"],
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


def _make_fde_analysis(F="创新功能分析", D="差异化分析", E="生态价值分析", overall_score=8):
    from src.analyzer import FDEAnalysis
    return FDEAnalysis(F=F, D=D, E=E, overall_score=overall_score)


def _make_skip_record(full_name="old/repo", reason="已生成过内容包"):
    from src.report import SkippedRecord
    return SkippedRecord(full_name=full_name, reason=reason)


class TestGenerateDailyReportV4:
    """Test v4 daily report with 4-layer scoring and pool assignments."""

    def test_report_contains_v4_sections(self):
        from src.report import generate_daily_report

        top5 = [_make_scored_repo(f"test/r{i}", score=90 - i * 5) for i in range(5)]
        analyses = {r.full_name: _make_fde_analysis() for r in top5}
        top20 = top5[:]
        evergreen = [_make_scored_repo("langgenius/dify", stars=150000, score=49, content_type="framework_tool")]
        resource = [_make_scored_repo("test/awesome-list", stars=10000, score=60, content_type="awesome_list")]
        high_risk = [_make_scored_repo("evil/deepfake", stars=5000, score=80, content_type="high_risk")]

        report = generate_daily_report(top5, analyses, top20, [], evergreen, resource, high_risk)

        expected_sections = [
            "今日最适合做主选题",
            "常青基础设施候选",
            "资料库/合集候选",
            "高风险跳过项目",
            "候选列表",
            "平台方向推荐",
            "数据来源与时间",
        ]
        for section in expected_sections:
            assert section in report, f"Missing section: {section}"

    def test_report_shows_layered_scores(self):
        """v4 report should show 选题分 and 商业价值."""
        from src.report import generate_daily_report

        top5 = [_make_scored_repo("test/app", ai_evidence=["ai", "agent", "rag"])]
        analyses = {}

        report = generate_daily_report(top5, analyses, top5, [])

        assert "选题分" in report or "选题维度" in report
        assert "商业价值" in report
        assert "最佳平台" in report

    def test_report_includes_ai_relevance(self):
        from src.report import generate_daily_report

        top5 = [_make_scored_repo("test/app", ai_evidence=["ai", "agent", "rag"])]
        analyses = {}

        report = generate_daily_report(top5, analyses, top5, [])

        assert "AI 相关性" in report
        assert "agent" in report

    def test_report_handles_empty_top5(self):
        from src.report import generate_daily_report

        report = generate_daily_report([], {}, [], [], [], [], [])

        assert len(report) > 100
        assert "暂无满足条件" in report or "Top" in report

    def test_report_handles_missing_analysis(self):
        from src.report import generate_daily_report

        top5 = [_make_scored_repo("test/r1")]
        analyses = {}

        report = generate_daily_report(top5, analyses, top5, [])

        assert len(report) > 100

    def test_high_risk_section_shows_blocked_repos(self):
        from src.report import generate_daily_report

        high_risk = [_make_scored_repo(
            "evil/deepfake",
            score=90,
            content_type="high_risk",
            risk_level="high",
        )]
        high_risk[0].filter_reason = "高风险关键词: deepfake"

        report = generate_daily_report([], {}, [], [], [], [], high_risk)

        assert "deepfake" in report
        assert "高风险" in report

    def test_evergreen_section_shows_demoted_repos(self):
        from src.report import generate_daily_report

        evergreen = [_make_scored_repo(
            "langgenius/dify",
            stars=150000,
            score=49,
            content_type="framework_tool",
        )]
        evergreen[0].demotion_reason = "常青项目（150K stars），进入常青基础设施候选池"

        report = generate_daily_report([], {}, [], [], evergreen, [], [])

        assert "dify" in report
        assert "常青" in report

    def test_report_has_timestamp(self):
        from src.report import generate_daily_report

        report = generate_daily_report([], {}, [], [], [], [], [])
        assert re.search(r"\d{4}-\d{2}-\d{2}", report)

    def test_resource_section_shows_awesome_lists(self):
        from src.report import generate_daily_report

        resource = [_make_scored_repo(
            "test/awesome-llm-apps",
            stars=10000,
            score=60,
            content_type="awesome_list",
        )]
        resource[0].demotion_reason = "项目合集/awesome list，进入资料库候选"

        report = generate_daily_report([], {}, [], [], [], resource, [])

        assert "awesome-llm-apps" in report


class TestGenerateCandidateReport:
    def test_candidate_report_includes_all_repos(self):
        from src.report import generate_candidate_report

        repos = [_make_scored_repo(f"test/r{i}", score=80 - i * 3) for i in range(10)]
        report = generate_candidate_report(repos)

        for repo in repos:
            assert repo.full_name in report

    def test_candidate_report_handles_empty_list(self):
        from src.report import generate_candidate_report

        report = generate_candidate_report([])
        assert len(report) > 0
