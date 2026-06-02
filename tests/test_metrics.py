"""Tests for metrics.py — Phase 24 post-publish metrics tracking."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ═══════════════════════════════════════════════════════════════
# 1. record_metrics writes correctly
# ═══════════════════════════════════════════════════════════════

class TestRecordMetrics:

    def test_normal_write(self, tmp_path, monkeypatch):
        """record_metrics 正常写入并返回正确数据."""
        from src.metrics import record_metrics, METRICS_HISTORY_FILE

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        result = record_metrics("test/repo", platform="wechat",
                                views=1000, likes=50, favorites=20,
                                comments=10, leads=3, note="test run")

        assert result["status"] == "ok"
        assert result["repo"] == "test/repo"
        assert result["platform"] == "wechat"
        assert result["engagement_rate"] == pytest.approx(0.08, abs=0.01)
        assert result["lead_rate"] == pytest.approx(0.003, abs=0.001)

        # Verify file written
        history_file = state_dir / "metrics_history.json"
        assert history_file.exists()
        data = json.loads(history_file.read_text("utf-8"))
        assert "test/repo" in data
        assert len(data["test/repo"]) == 1
        assert data["test/repo"][0]["views"] == 1000
        assert data["test/repo"][0]["likes"] == 50


# ═══════════════════════════════════════════════════════════════
# 2. engagement_rate calculation
# ═══════════════════════════════════════════════════════════════

class TestEngagementRate:

    def test_engagement_rate_correct(self, tmp_path, monkeypatch):
        """互动率 = (likes + favorites + comments) / views."""
        from src.metrics import record_metrics

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        # 100 views, 10 likes + 5 favs + 5 comments = 20 total → 0.20
        result = record_metrics("test/eng", platform="wechat",
                                views=100, likes=10, favorites=5, comments=5)
        assert result["engagement_rate"] == pytest.approx(0.20, abs=0.01)

    def test_zero_views_returns_zero(self, tmp_path, monkeypatch):
        """views=0 时互动率为 0."""
        from src.metrics import record_metrics

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        result = record_metrics("test/zero", platform="xiaohongshu",
                                views=0, likes=999, favorites=999, comments=999)
        assert result["engagement_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════
# 3. lead_rate calculation
# ═══════════════════════════════════════════════════════════════

class TestLeadRate:

    def test_lead_rate_correct(self, tmp_path, monkeypatch):
        """线索率 = leads / views."""
        from src.metrics import record_metrics

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        result = record_metrics("test/lead", platform="wechat",
                                views=500, leads=10)
        assert result["lead_rate"] == pytest.approx(0.02, abs=0.001)

    def test_zero_views_lead_rate_zero(self, tmp_path, monkeypatch):
        """views=0 时线索率为 0."""
        from src.metrics import record_metrics

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        result = record_metrics("test/zero2", platform="douyin",
                                views=0, leads=100)
        assert result["lead_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════
# 4. metrics_history query by repo
# ═══════════════════════════════════════════════════════════════

class TestMetricsHistoryQuery:

    def test_query_by_repo(self, tmp_path, monkeypatch):
        """按 repo 查询返回正确条目."""
        from src.metrics import record_metrics, get_metrics_history

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        record_metrics("alpha/one", platform="wechat", views=100, likes=5)
        record_metrics("alpha/one", platform="xiaohongshu", views=200, likes=10)
        record_metrics("beta/two", platform="wechat", views=50, likes=2)

        entries = get_metrics_history("alpha/one")
        assert len(entries) == 2
        assert entries[0]["platform"] == "wechat"
        assert entries[1]["platform"] == "xiaohongshu"

    def test_query_all(self, tmp_path, monkeypatch):
        """不传 repo 返回全部."""
        from src.metrics import record_metrics, get_metrics_history

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        record_metrics("a/b", platform="wechat", views=100)
        record_metrics("c/d", platform="xiaohongshu", views=200)

        history = get_metrics_history()
        assert isinstance(history, dict)
        assert "a/b" in history
        assert "c/d" in history


# ═══════════════════════════════════════════════════════════════
# 5. Empty data — dashboard/workbench don't crash
# ═══════════════════════════════════════════════════════════════

class TestEmptyDataNoCrash:

    def test_dashboard_handles_no_metrics(self, tmp_path, monkeypatch):
        """dashboard 在无 metrics 数据时不崩溃."""
        from src.dashboard import generate_dashboard

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        # Minimal quality gate for dashboard
        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")
        (state_dir / "seen_repos.json").write_text("{}", encoding="utf-8")
        (state_dir / "generated_repos.json").write_text("{}", encoding="utf-8")

        import src.dashboard as dash
        monkeypatch.setattr(dash, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(dash, "STATE_DIR", state_dir)
        monkeypatch.setattr(dash, "PROJECT_ROOT", tmp_path)

        output = generate_dashboard()
        assert "暂无发布后表现数据" in output or "发布后表现摘要" in output

    def test_workbench_handles_no_metrics(self, tmp_path, monkeypatch):
        """workbench 在无 metrics 数据时不崩溃."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench()
        assert "复盘建议" in output
        assert "暂无发布后数据" in output or "record-metrics" in output


# ═══════════════════════════════════════════════════════════════
# 6. metrics_history.json is gitignored
# ═══════════════════════════════════════════════════════════════

class TestGitignore:

    def test_metrics_history_is_gitignored(self):
        """data/state/metrics_history.json 在 .gitignore 中."""
        gitignore = _project_root / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert "metrics_history.json" in content


# ═══════════════════════════════════════════════════════════════
# 7. CLI commands exist
# ═══════════════════════════════════════════════════════════════

class TestCliCommands:

    def test_record_metrics_command_exists(self):
        """record-metrics 命令已在 CLI parser 中注册."""
        from src.main import build_parser
        parser = build_parser()
        help_text = parser.format_help()
        assert "record-metrics" in help_text

    def test_metrics_history_command_exists(self):
        """metrics-history 命令已在 CLI parser 中注册."""
        from src.main import build_parser
        parser = build_parser()
        help_text = parser.format_help()
        assert "metrics-history" in help_text


# ═══════════════════════════════════════════════════════════════
# 8. summarize_metrics aggregation
# ═══════════════════════════════════════════════════════════════

class TestSummarizeMetrics:

    def test_aggregates_correctly(self, tmp_path, monkeypatch):
        """summarize_metrics 正确聚合多项目数据."""
        from src.metrics import record_metrics, summarize_metrics

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        record_metrics("x/a", platform="wechat", views=1000, likes=50,
                       favorites=20, comments=10, leads=5)
        record_metrics("x/a", platform="xiaohongshu", views=500, likes=30,
                       favorites=10, comments=5, leads=2)
        record_metrics("y/b", platform="wechat", views=200, likes=5,
                       favorites=2, comments=1, leads=0)

        summary = summarize_metrics()
        assert summary["repo_count"] == 2
        assert summary["entry_count"] == 3
        assert summary["platform_count"] == 2
        assert summary["best_views"]["views"] == 1000
        assert summary["best_views"]["repo"] == "x/a"
        assert summary["best_lead"]["rate"] > 0
        assert len(summary["recent_entries"]) == 3

    def test_empty_returns_zeros(self, tmp_path, monkeypatch):
        """空数据时 summarize 返回零值，不崩溃."""
        from src.metrics import summarize_metrics

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        summary = summarize_metrics()
        assert summary["entry_count"] == 0
        assert summary["repo_count"] == 0


# ═══════════════════════════════════════════════════════════════
# 9. reject invalid platform
# ═══════════════════════════════════════════════════════════════

class TestInvalidPlatform:

    def test_invalid_platform_blocked(self, tmp_path, monkeypatch):
        """不支持的平台返回 blocked."""
        from src.metrics import record_metrics

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("src.metrics.METRICS_HISTORY_FILE",
                           state_dir / "metrics_history.json")

        result = record_metrics("test/p", platform="instagram",
                                views=100)
        assert result["status"] == "blocked"
        assert "instagram" in result.get("reason", "")
