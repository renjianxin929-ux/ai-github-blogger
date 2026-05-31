"""Tests for main.py — CLI argument parsing and pipeline orchestration."""
import sys
from pathlib import Path
from unittest import mock

import pytest


class TestCLIArgs:
    """Test CLI argument parsing."""

    def test_daily_subcommand(self):
        """python -m src.main daily should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["daily"])
        assert args.command == "daily"
        assert args.no_llm is False

    def test_daily_no_llm_flag(self):
        """--no-llm flag should be parsed."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["daily", "--no-llm"])
        assert args.no_llm is True

    def test_fetch_subcommand(self):
        """python -m src.main fetch should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["fetch"])
        assert args.command == "fetch"

    def test_score_subcommand(self):
        """python -m src.main score should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["score"])
        assert args.command == "score"

    def test_report_subcommand(self):
        """python -m src.main report should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["report"])
        assert args.command == "report"

    def test_content_subcommand_with_repo(self):
        """python -m src.main content owner/repo should parse repo arg."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["content", "test/awesome-repo"])
        assert args.command == "content"
        assert args.repo == "test/awesome-repo"

    def test_content_subcommand_requires_repo(self):
        """content subcommand without repo should raise."""
        from src.main import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["content"])

    def test_default_command_is_daily(self):
        """No arguments should default to daily."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args([])
        assert args.command == "daily"


# ── Helpers for Phase 13 tests ──────────────────────────────────────────

def _make_scored_repo(full_name="test/repo", score=75.0, risk_level="none",
                      content_type="runnable_project", pool="top5"):
    from src.scorer import ScoredRepo

    return ScoredRepo(
        full_name=full_name,
        name=full_name.split("/")[-1],
        description="A test repo",
        url=f"https://github.com/{full_name}",
        language="Python",
        stars=1000,
        forks=100,
        updated_at="2026-05-31T00:00:00Z",
        topics=["AI", "LLM"],
        license="MIT",
        readme="# Test Repo\n\nSome content.\n" * 10,
        contributors_count=5,
        score=score,
        subscores={},
        risk_level=risk_level,
        content_type=content_type,
        pool=pool,
    )


# ── Phase 13: Dry-Run Tests ─────────────────────────────────────────────

def _make_raw_repo(full_name="test/repo", description="A test repo"):
    from src.fetcher import RawRepo
    return RawRepo(
        full_name=full_name,
        name=full_name.split("/")[-1],
        description=description,
        url=f"https://github.com/{full_name}",
        language="Python",
        stars_today=1000,
    )


class TestDryRun:
    """Dry-run must not consume LLM tokens or write real content packs."""

    @mock.patch("src.main.score_repo")
    @mock.patch("src.main.apply_classification_and_filters")
    @mock.patch("src.main.enrich_repo")
    @mock.patch("src.main.search_repos")
    def test_dry_run_does_not_call_llm(self, mock_fetch, mock_enrich,
                                        mock_classify, mock_score):
        """dry-run 不调用 _call_llm 或 ai_fde_analyze."""
        mock_fetch.return_value = [_make_raw_repo("test/good-repo")]
        from src.enricher import EnrichedRepo
        mock_enrich.return_value = EnrichedRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300, open_issues=5,
            updated_at="2026-05-31T00:00:00Z", created_at="2025-01-01T00:00:00Z",
            topics=["AI"], license="MIT", readme="# Test\n" * 5, contributors_count=5,
        )
        from src.scorer import ScoredRepo
        scored = ScoredRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300,
            updated_at="2026-05-31T00:00:00Z", topics=["AI"],
            license="MIT", readme="# Test\n" * 5, contributors_count=5,
            score=85.0, subscores={},
        )
        mock_score.return_value = scored
        mock_classify.return_value = {
            "runnable_top5": [scored],
            "evergreen_candidates": [],
            "resource_candidates": [],
            "high_risk_skipped": [],
        }
        from src.main import cmd_dry_run
        with mock.patch("src.main.ai_fde_analyze") as mock_ai:
            with mock.patch("src.analyzer._call_llm") as mock_llm:
                cmd_dry_run()
                mock_ai.assert_not_called()
                mock_llm.assert_not_called()

    @mock.patch("src.main.score_repo")
    @mock.patch("src.main.apply_classification_and_filters")
    @mock.patch("src.main.enrich_repo")
    @mock.patch("src.main.search_repos")
    def test_dry_run_does_not_write_content_pack(self, mock_fetch, mock_enrich,
                                                  mock_classify, mock_score, tmp_path):
        """dry-run 不写入 data/content_packs/."""
        mock_fetch.return_value = [_make_raw_repo("test/good-repo")]
        from src.enricher import EnrichedRepo
        mock_enrich.return_value = EnrichedRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300, open_issues=5,
            updated_at="2026-05-31T00:00:00Z", created_at="2025-01-01T00:00:00Z",
            topics=["AI"], license="MIT", readme="# Test\n" * 5, contributors_count=5,
        )
        from src.scorer import ScoredRepo
        scored = ScoredRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300,
            updated_at="2026-05-31T00:00:00Z", topics=["AI"],
            license="MIT", readme="# Test\n" * 5, contributors_count=5,
            score=85.0, subscores={},
        )
        mock_score.return_value = scored
        mock_classify.return_value = {
            "runnable_top5": [scored],
            "evergreen_candidates": [],
            "resource_candidates": [],
            "high_risk_skipped": [],
        }
        from src.main import cmd_dry_run
        with mock.patch("src.main.generate_content_pack") as mock_gen:
            mock_gen.return_value = (tmp_path / "fake", "ok")
            with mock.patch("src.main.REPORTS_DIR", tmp_path / "reports"):
                cmd_dry_run()
                for call_args in mock_gen.call_args_list:
                    kwargs = call_args.kwargs if hasattr(call_args, 'kwargs') else {}
                    assert kwargs.get("dry_run", False), \
                        "generate_content_pack must be called with dry_run=True"

    @mock.patch("src.main.score_repo")
    @mock.patch("src.main.apply_classification_and_filters")
    @mock.patch("src.main.enrich_repo")
    @mock.patch("src.main.search_repos")
    def test_dry_run_shows_pool_assignments(self, mock_fetch, mock_enrich,
                                             mock_classify, mock_score, capsys):
        """dry-run 输出包含 pool 分配信息."""
        mock_fetch.return_value = [_make_raw_repo("test/good-repo")]
        from src.enricher import EnrichedRepo
        mock_enrich.return_value = EnrichedRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300, open_issues=5,
            updated_at="2026-05-31T00:00:00Z", created_at="2025-01-01T00:00:00Z",
            topics=["AI"], license="MIT", readme="# Test\n" * 5, contributors_count=5,
        )
        from src.scorer import ScoredRepo
        scored = ScoredRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300,
            updated_at="2026-05-31T00:00:00Z", topics=["AI"],
            license="MIT", readme="# Test\n" * 5, contributors_count=5,
            score=85.0, subscores={},
        )
        mock_score.return_value = scored
        mock_classify.return_value = {
            "runnable_top5": [scored],
            "evergreen_candidates": [],
            "resource_candidates": [],
            "high_risk_skipped": [],
        }
        from src.main import cmd_dry_run
        with mock.patch("src.main.generate_content_pack") as mock_gen:
            mock_gen.return_value = (Path("/fake"), "ok")
            with mock.patch("src.main.REPORTS_DIR", Path("/fake_reports")):
                cmd_dry_run()
        captured = capsys.readouterr().out
        assert "Top5" in captured or "Top" in captured or "runnable" in captured or \
            "Evergreen" in captured or "Blocked" in captured or "Resource" in captured, \
            f"Output should mention pool assignments, got:\n{captured[:500]}"

    @mock.patch("src.main.score_repo")
    @mock.patch("src.main.apply_classification_and_filters")
    @mock.patch("src.main.enrich_repo")
    @mock.patch("src.main.search_repos")
    def test_dry_run_shows_estimated_api_calls(self, mock_fetch, mock_enrich,
                                                mock_classify, mock_score, capsys):
        """dry-run 输出包含预估 API 调用量."""
        mock_fetch.return_value = [_make_raw_repo("test/good-repo")]
        from src.enricher import EnrichedRepo
        mock_enrich.return_value = EnrichedRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300, open_issues=5,
            updated_at="2026-05-31T00:00:00Z", created_at="2025-01-01T00:00:00Z",
            topics=["AI"], license="MIT", readme="# Test\n" * 5, contributors_count=5,
        )
        from src.scorer import ScoredRepo
        scored = ScoredRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300,
            updated_at="2026-05-31T00:00:00Z", topics=["AI"],
            license="MIT", readme="# Test\n" * 5, contributors_count=5,
            score=85.0, subscores={},
        )
        mock_score.return_value = scored
        mock_classify.return_value = {
            "runnable_top5": [scored],
            "evergreen_candidates": [],
            "resource_candidates": [],
            "high_risk_skipped": [],
        }
        from src.main import cmd_dry_run
        with mock.patch("src.main.generate_content_pack") as mock_gen:
            mock_gen.return_value = (Path("/fake"), "ok")
            with mock.patch("src.main.REPORTS_DIR", Path("/fake_reports")):
                cmd_dry_run()
        captured = capsys.readouterr().out
        assert "API" in captured or "调用" in captured or "fetch" in captured.lower(), \
            f"Output should mention API calls, got:\n{captured[:500]}"

    @mock.patch("src.main.score_repo")
    @mock.patch("src.main.apply_classification_and_filters")
    @mock.patch("src.main.enrich_repo")
    @mock.patch("src.main.search_repos")
    def test_dry_run_shows_risk_items(self, mock_fetch, mock_enrich,
                                       mock_classify, mock_score, capsys):
        """dry-run 输出包含风险项."""
        mock_fetch.return_value = [_make_raw_repo("test/good-repo")]
        from src.enricher import EnrichedRepo
        mock_enrich.return_value = EnrichedRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300, open_issues=5,
            updated_at="2026-05-31T00:00:00Z", created_at="2025-01-01T00:00:00Z",
            topics=["AI"], license="MIT", readme="# Test\n" * 5, contributors_count=5,
        )
        from src.scorer import ScoredRepo
        scored = ScoredRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300,
            updated_at="2026-05-31T00:00:00Z", topics=["AI"],
            license="MIT", readme="# Test\n" * 5, contributors_count=5,
            score=85.0, subscores={},
        )
        mock_score.return_value = scored
        mock_classify.return_value = {
            "runnable_top5": [scored],
            "evergreen_candidates": [],
            "resource_candidates": [],
            "high_risk_skipped": [],
        }
        from src.main import cmd_dry_run
        with mock.patch("src.main.generate_content_pack") as mock_gen:
            mock_gen.return_value = (Path("/fake"), "ok")
            with mock.patch("src.main.REPORTS_DIR", Path("/fake_reports")):
                cmd_dry_run()
        captured = capsys.readouterr().out
        assert "风险" in captured or "risk" in captured.lower() or "Risk" in captured, \
            f"Output should mention risk items, got:\n{captured[:500]}"

    @mock.patch("src.main.score_repo")
    @mock.patch("src.main.apply_classification_and_filters")
    @mock.patch("src.main.enrich_repo")
    @mock.patch("src.main.search_repos")
    def test_dry_run_writes_report_file(self, mock_fetch, mock_enrich,
                                         mock_classify, mock_score, tmp_path):
        """dry-run 写入 dry_run_report 到 data/reports/."""
        mock_fetch.return_value = [_make_raw_repo("test/good-repo")]
        from src.enricher import EnrichedRepo
        mock_enrich.return_value = EnrichedRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300, open_issues=5,
            updated_at="2026-05-31T00:00:00Z", created_at="2025-01-01T00:00:00Z",
            topics=["AI"], license="MIT", readme="# Test\n" * 5, contributors_count=5,
        )
        from src.scorer import ScoredRepo
        scored = ScoredRepo(
            full_name="test/good-repo", name="good-repo",
            description="Test", url="https://github.com/test/good-repo",
            language="Python", stars=5000, forks=300,
            updated_at="2026-05-31T00:00:00Z", topics=["AI"],
            license="MIT", readme="# Test\n" * 5, contributors_count=5,
            score=85.0, subscores={},
        )
        mock_score.return_value = scored
        mock_classify.return_value = {
            "runnable_top5": [scored],
            "evergreen_candidates": [],
            "resource_candidates": [],
            "high_risk_skipped": [],
        }
        from src.main import cmd_dry_run
        reports_dir = tmp_path / "reports"
        with mock.patch("src.main.generate_content_pack") as mock_gen:
            mock_gen.return_value = (Path("/fake"), "ok")
            with mock.patch("src.main.REPORTS_DIR", reports_dir):
                cmd_dry_run()
        reports = list(reports_dir.glob("dry_run_report_*.md"))
        assert len(reports) >= 1, f"Expected dry_run_report in {reports_dir}"


# ── Phase 13: Daily-Workflow Tests ──────────────────────────────────────

class TestDailyWorkflow:
    """daily-workflow command: doctor → daily --no-llm → quality-gate."""

    def test_daily_workflow_command_registered(self):
        """python run.py daily-workflow 命令存在."""
        from src.main import build_parser
        parser = build_parser()
        choices = {}
        for action in parser._actions:
            if hasattr(action, 'choices') and action.choices:
                choices.update(action.choices)
        assert "daily-workflow" in choices, "daily-workflow subcommand must be registered"

    @mock.patch("src.main.cmd_doctor")
    @mock.patch("src.main.cmd_daily")
    @mock.patch("src.main.cmd_quality_gate")
    def test_daily_workflow_calls_doctor_daily_quality_gate(self, mock_qg, mock_daily, mock_doctor):
        """daily-workflow 按顺序调用 doctor → daily --no-llm → quality-gate."""
        from src.main import cmd_daily_workflow

        mock_doctor.return_value = 0
        mock_daily.return_value = 0
        mock_qg.return_value = 0
        result = cmd_daily_workflow()
        mock_doctor.assert_called_once()
        mock_daily.assert_called_once()
        mock_qg.assert_called_once()

    @mock.patch("src.main.cmd_doctor")
    def test_daily_workflow_stops_on_doctor_fail(self, mock_doctor):
        """doctor 不通过时，daily-workflow 应停止并返回非零."""
        from src.main import cmd_daily_workflow
        mock_doctor.return_value = 1
        result = cmd_daily_workflow()
        assert result != 0, "Should return non-zero when doctor fails"

    @mock.patch("src.main.cmd_doctor")
    @mock.patch("src.main.cmd_daily")
    @mock.patch("src.main.cmd_quality_gate")
    def test_daily_workflow_shows_top5_and_next_action(self, mock_qg, mock_daily, mock_doctor, capsys):
        """daily-workflow 输出包含 Top 5 和推荐下一步."""
        from src.main import cmd_daily_workflow
        mock_doctor.return_value = 0
        mock_daily.return_value = 0
        mock_qg.return_value = 0
        cmd_daily_workflow()
        captured = capsys.readouterr().out
        assert "Top" in captured or "选题" in captured or "推荐" in captured or \
            "next" in captured.lower()


# ── Phase 13: Review-Queue Tests ────────────────────────────────────────

class TestReviewQueue:
    """review-queue command: human review checklist output."""

    def test_review_queue_command_registered(self):
        """python run.py review-queue 命令存在."""
        from src.main import build_parser
        parser = build_parser()
        choices = {}
        for action in parser._actions:
            if hasattr(action, 'choices') and action.choices:
                choices.update(action.choices)
        assert "review-queue" in choices, "review-queue subcommand must be registered"

    def test_generate_review_queue_has_recommended_project(self):
        """输出包含'今日最推荐发布'段落."""
        from src.report import generate_review_queue

        repo = _make_scored_repo("test/good-repo", score=85)
        result = generate_review_queue(
            top5=[repo], evergreen=[], resource=[], high_risk=[], all_scored=[repo]
        )
        assert "最推荐" in result or "推荐" in result, \
            f"Should contain recommended project section, got:\n{result[:500]}"

    def test_generate_review_queue_has_risk_points(self):
        """输出包含风险点."""
        from src.report import generate_review_queue

        repo = _make_scored_repo("test/risky-repo", score=60, risk_level="medium")
        result = generate_review_queue(
            top5=[repo], evergreen=[], resource=[], high_risk=[], all_scored=[repo]
        )
        assert "风险" in result or "risk" in result.lower(), \
            f"Should mention risk, got:\n{result[:500]}"

    def test_generate_review_queue_has_suitable_platforms(self):
        """输出包含适合平台信息."""
        from src.report import generate_review_queue

        repo = _make_scored_repo("test/platform-repo", score=80)
        result = generate_review_queue(
            top5=[repo], evergreen=[], resource=[], high_risk=[], all_scored=[repo]
        )
        assert "平台" in result or "platform" in result.lower() or \
            "小红书" in result or "抖音" in result or "公众号" in result or \
            "深度分析" in result, \
            f"Should mention suitable platforms, got:\n{result[:500]}"

    def test_generate_review_queue_has_blocked_explanation(self):
        """blocked 项目有拦截原因解释."""
        from src.report import generate_review_queue

        blocked = _make_scored_repo("evil/phishing-tool", score=25, risk_level="high",
                                     content_type="high_risk", pool="blocked")
        blocked.filter_reason = "phishing/credential-harvesting 关键词命中"

        result = generate_review_queue(
            top5=[], evergreen=[], resource=[], high_risk=[blocked], all_scored=[blocked]
        )
        assert "拦截" in result or "blocked" in result.lower() or "phishing" in result.lower(), \
            f"Should explain blocked reason, got:\n{result[:500]}"

    def test_generate_review_queue_has_content_readiness(self):
        """输出包含是否可进入 content 生成的判断."""
        from src.report import generate_review_queue

        repo = _make_scored_repo("test/ready-repo", score=85)
        result = generate_review_queue(
            top5=[repo], evergreen=[], resource=[], high_risk=[], all_scored=[repo]
        )
        assert "content" in result.lower() or "生成" in result or "发布" in result or \
            "python run.py content" in result, \
            f"Should indicate content generation readiness, got:\n{result[:500]}"
