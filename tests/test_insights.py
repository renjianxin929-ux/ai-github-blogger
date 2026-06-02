"""Tests for insights.py — Phase 25 post-publish insights engine."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _write_metrics(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_pubhist(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# 1. CLI command exists
# ═══════════════════════════════════════════════════════════════

class TestCliCommand:

    def test_insights_command_exists(self):
        """insights 命令已在 CLI parser 中注册."""
        from src.main import build_parser
        parser = build_parser()
        help_text = parser.format_help()
        assert "insights" in help_text


# ═══════════════════════════════════════════════════════════════
# 2. Output has 5 sections
# ═══════════════════════════════════════════════════════════════

class TestOutputSections:

    def test_all_five_sections_present(self, tmp_path, monkeypatch):
        """generate_insights 输出包含全部 5 个区块."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        metrics_file = state_dir / "metrics_history.json"
        pubhist_file = state_dir / "publish_history.json"

        _write_metrics(metrics_file, {
            "test/repo": [{
                "platform": "wechat", "views": 1000, "likes": 50,
                "favorites": 20, "comments": 10, "leads": 5,
                "engagement_rate": 0.08, "lead_rate": 0.005,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }]
        })
        _write_pubhist(pubhist_file, {
            "test/repo": [{
                "platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                "publishability_score": 80, "score": 75,
                "source_mode": "runnable_project", "pack_dir": "packs/test"
            }]
        })

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE", metrics_file)
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE", pubhist_file)

        output = generate_insights()

        assert "1. 总体表现摘要" in output
        assert "2. 平台表现建议" in output
        assert "3. Repo 复盘建议" in output
        assert "4. 明日选题建议" in output
        assert "5. 风险提示" in output


# ═══════════════════════════════════════════════════════════════
# 3. Empty data graceful
# ═══════════════════════════════════════════════════════════════

class TestEmptyData:

    def test_empty_metrics_no_crash(self, tmp_path, monkeypatch):
        """空 metrics 数据不崩溃，明确输出'暂无数据'."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        _write_metrics(state_dir / "metrics_history.json", {})
        _write_pubhist(state_dir / "publish_history.json", {})

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_insights()
        assert "暂无" in output or "暂无任何表现数据" in output

    def test_empty_insights_summary_for_workbench(self, tmp_path, monkeypatch):
        """insights_summary_for_workbench 空数据不崩溃."""
        from src.insights import insights_summary_for_workbench

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        _write_metrics(state_dir / "metrics_history.json", {})
        _write_pubhist(state_dir / "publish_history.json", {})

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        result = insights_summary_for_workbench()
        assert isinstance(result, list)
        assert any("暂无" in line for line in result)

    def test_empty_trend_for_dashboard(self, tmp_path, monkeypatch):
        """insights_trend_for_dashboard 空数据不崩溃."""
        from src.insights import insights_trend_for_dashboard

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        _write_metrics(state_dir / "metrics_history.json", {})

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        result = insights_trend_for_dashboard()
        assert isinstance(result, list)
        assert any("暂无" in line for line in result)


# ═══════════════════════════════════════════════════════════════
# 4. Repo filter
# ═══════════════════════════════════════════════════════════════

class TestRepoFilter:

    def test_filter_single_repo(self, tmp_path, monkeypatch):
        """--repo 过滤只显示指定项目."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        _write_metrics(state_dir / "metrics_history.json", {
            "alpha/x": [{"platform": "wechat", "views": 100, "likes": 5,
                         "favorites": 0, "comments": 0, "leads": 0,
                         "engagement_rate": 0.05, "lead_rate": 0.0,
                         "recorded_at": "2026-06-01T08:00:00Z", "note": ""}],
            "beta/y": [{"platform": "xiaohongshu", "views": 200, "likes": 10,
                        "favorites": 5, "comments": 3, "leads": 1,
                        "engagement_rate": 0.09, "lead_rate": 0.005,
                        "recorded_at": "2026-06-01T08:00:00Z", "note": ""}]
        })
        _write_pubhist(state_dir / "publish_history.json", {
            "alpha/x": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                         "publishability_score": 70, "score": 65,
                         "source_mode": "runnable_project", "pack_dir": "packs/a"}],
            "beta/y": [{"platform": "xiaohongshu", "published_at": "2026-06-01T08:00:00Z",
                        "publishability_score": 80, "score": 75,
                        "source_mode": "tutorial_guide", "pack_dir": "packs/b"}]
        })

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_insights(repo="alpha/x")
        assert "alpha/x" in output
        assert "beta/y" not in output


# ═══════════════════════════════════════════════════════════════
# 5. Platform recommendations with evidence
# ═══════════════════════════════════════════════════════════════

class TestPlatformRecommendations:

    def test_platform_recommendation_has_evidence(self, tmp_path, monkeypatch):
        """平台建议必须标注依据."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        _write_metrics(state_dir / "metrics_history.json", {
            "test/r": [{
                "platform": "wechat", "views": 1000, "likes": 80,
                "favorites": 30, "comments": 20, "leads": 15,
                "engagement_rate": 0.13, "lead_rate": 0.015,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }]
        })
        _write_pubhist(state_dir / "publish_history.json", {
            "test/r": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                        "publishability_score": 85, "score": 80,
                        "source_mode": "runnable_project", "pack_dir": "packs/t"}]
        })

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_insights()
        # Evidence markers must be present
        assert "依据" in output

    def test_wechat_good_performance_recommended(self, tmp_path, monkeypatch):
        """高互动+高线索的平台应被推荐（需≥3条数据满足置信度）."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        # Need ≥3 entries per platform to pass MIN_ENTRIES_FOR_CONFIDENCE
        _write_metrics(state_dir / "metrics_history.json", {
            "test/g1": [{
                "platform": "wechat", "views": 1000, "likes": 80,
                "favorites": 30, "comments": 20, "leads": 15,
                "engagement_rate": 0.13, "lead_rate": 0.015,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }],
            "test/g2": [{
                "platform": "wechat", "views": 800, "likes": 70,
                "favorites": 25, "comments": 15, "leads": 10,
                "engagement_rate": 0.14, "lead_rate": 0.012,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }],
            "test/g3": [{
                "platform": "wechat", "views": 600, "likes": 50,
                "favorites": 20, "comments": 10, "leads": 8,
                "engagement_rate": 0.13, "lead_rate": 0.013,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }],
        })
        _write_pubhist(state_dir / "publish_history.json", {
            "test/g1": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                         "publishability_score": 85, "score": 80,
                         "source_mode": "runnable_project", "pack_dir": "packs/g1"}],
            "test/g2": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                         "publishability_score": 85, "score": 80,
                         "source_mode": "runnable_project", "pack_dir": "packs/g2"}],
            "test/g3": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                         "publishability_score": 85, "score": 80,
                         "source_mode": "runnable_project", "pack_dir": "packs/g3"}],
        })

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_insights()
        assert "适合继续做" in output or "✅" in output


# ═══════════════════════════════════════════════════════════════
# 6. Risk detection
# ═══════════════════════════════════════════════════════════════

class TestRiskDetection:

    def test_small_sample_warning(self, tmp_path, monkeypatch):
        """样本过少时发出警告."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        _write_metrics(state_dir / "metrics_history.json", {
            "test/s": [{
                "platform": "wechat", "views": 50, "likes": 3,
                "favorites": 1, "comments": 0, "leads": 0,
                "engagement_rate": 0.08, "lead_rate": 0.0,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }]
        })
        _write_pubhist(state_dir / "publish_history.json", {
            "test/s": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                        "publishability_score": 70, "score": 65,
                        "source_mode": "runnable_project", "pack_dir": "packs/s"}]
        })

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_insights()
        assert "样本" in output

    def test_missing_data_warning(self, tmp_path, monkeypatch):
        """已发布但无数据时发出警告."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        _write_metrics(state_dir / "metrics_history.json", {})
        _write_pubhist(state_dir / "publish_history.json", {
            "test/m": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                        "publishability_score": 75, "score": 70,
                        "source_mode": "runnable_project", "pack_dir": "packs/m"}]
        })

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_insights()
        assert "已发布但无表现数据" in output or "无表现数据" in output or "数据不完整" in output

    def test_high_score_low_performance_warning(self, tmp_path, monkeypatch):
        """高分低表现时发出警告."""
        from src.insights import generate_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        _write_metrics(state_dir / "metrics_history.json", {
            "test/h": [{
                "platform": "wechat", "views": 200, "likes": 4,
                "favorites": 1, "comments": 1, "leads": 0,
                "engagement_rate": 0.02, "lead_rate": 0.0,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }]
        })
        _write_pubhist(state_dir / "publish_history.json", {
            "test/h": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                        "publishability_score": 85, "score": 80,
                        "source_mode": "runnable_project", "pack_dir": "packs/h"}]
        })

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_insights()
        assert "高分低表现" in output or "publishability_score 高" in output


# ═══════════════════════════════════════════════════════════════
# 7. insights cmd returns 0 always (read-only)
# ═══════════════════════════════════════════════════════════════

class TestCmdInsights:

    def test_cmd_insights_returns_zero(self, tmp_path, monkeypatch, capsys):
        """cmd_insights 始终返回 0（只读操作）."""
        from src.insights import cmd_insights

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        _write_metrics(state_dir / "metrics_history.json", {})
        _write_pubhist(state_dir / "publish_history.json", {})

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        rc = cmd_insights()
        assert rc == 0


# ═══════════════════════════════════════════════════════════════
# 8. Workbench integration
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchIntegration:

    def test_workbench_uses_insights(self, tmp_path, monkeypatch):
        """workbench 在无 metrics 数据时调用 insights 不崩溃."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")

        _write_metrics(state_dir / "metrics_history.json", {})
        _write_pubhist(state_dir / "publish_history.json", {})

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_workbench()
        assert "复盘建议" in output

    def test_workbench_with_metrics_data(self, tmp_path, monkeypatch):
        """workbench 有 metrics 数据时输出 insights 复盘建议."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")

        _write_metrics(state_dir / "metrics_history.json", {
            "test/wb": [{
                "platform": "wechat", "views": 1000, "likes": 50,
                "favorites": 20, "comments": 10, "leads": 3,
                "engagement_rate": 0.08, "lead_rate": 0.003,
                "recorded_at": "2026-06-01T08:00:00Z", "note": ""
            }]
        })
        _write_pubhist(state_dir / "publish_history.json", {
            "test/wb": [{"platform": "wechat", "published_at": "2026-06-01T08:00:00Z",
                         "publishability_score": 80, "score": 75,
                         "source_mode": "runnable_project", "pack_dir": "packs/wb"}]
        })

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_workbench()
        assert "复盘建议" in output
        # Should contain evidence marker
        assert "依据" in output


# ═══════════════════════════════════════════════════════════════
# 9. Dashboard integration
# ═══════════════════════════════════════════════════════════════

class TestDashboardIntegration:

    def test_dashboard_has_trend_section(self, tmp_path, monkeypatch):
        """dashboard 包含 '历史表现趋势摘要' 区块."""
        from src.dashboard import generate_dashboard

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")
        (state_dir / "seen_repos.json").write_text("{}", encoding="utf-8")
        (state_dir / "generated_repos.json").write_text("{}", encoding="utf-8")

        _write_metrics(state_dir / "metrics_history.json", {})
        _write_pubhist(state_dir / "publish_history.json", {})

        import src.dashboard as dash
        monkeypatch.setattr(dash, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(dash, "STATE_DIR", state_dir)
        monkeypatch.setattr(dash, "PROJECT_ROOT", tmp_path)

        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")
        monkeypatch.setattr("src.publish_history.PUBLISH_HISTORY_FILE",
                           state_dir / "publish_history.json")

        output = generate_dashboard()
        assert "8. 历史表现趋势摘要" in output
