"""Tests for dashboard.py — Phase 22 daily dashboard."""
import json
import sys
from datetime import date as dt_date, timedelta
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Constants ──────────────────────────────────────────────────

TODAY = dt_date.today()
TODAY_STR = TODAY.isoformat()


# ── Helpers ────────────────────────────────────────────────────

def _make_top5_entry(full_name="test/repo", score=75.0,
                     publishability_score=72.0, stars=1000,
                     content_type="runnable_project", pool="top5",
                     description="A test repo", language="Python",
                     topics=None):
    return {
        "full_name": full_name,
        "name": full_name.split("/")[-1],
        "score": score,
        "publishability_score": publishability_score,
        "stars": stars,
        "description": description,
        "language": language,
        "content_type": content_type,
        "topics": topics or ["AI", "LLM"],
        "pool": pool,
    }


def _write_top5_json(path: Path, entries: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# 1. _load_top5
# ═══════════════════════════════════════════════════════════════

class TestLoadTop5:

    def test_valid_json_returns_list(self, tmp_path):
        """有效 top5 JSON 返回正确列表."""
        from src.dashboard import _load_top5
        entries = [_make_top5_entry("a/b", score=80, publishability_score=80),
                   _make_top5_entry("c/d", score=60, publishability_score=60)]
        reports_dir = tmp_path / "reports"
        _write_top5_json(reports_dir / f"top5_{TODAY_STR}.json", entries)

        result = _load_top5(TODAY_STR, reports_dir=reports_dir)
        assert len(result) == 2
        assert result[0]["full_name"] == "a/b"
        assert result[1]["publishability_score"] == 60

    def test_missing_file_returns_empty(self, tmp_path):
        """文件不存在返回空列表."""
        from src.dashboard import _load_top5
        reports_dir = tmp_path / "reports"

        result = _load_top5("2099-01-01", reports_dir=reports_dir)
        assert result == []

    def test_corrupt_json_returns_empty(self, tmp_path):
        """损坏的 JSON 返回空列表."""
        from src.dashboard import _load_top5
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / f"top5_{TODAY_STR}.json").write_text("not json", encoding="utf-8")

        result = _load_top5(TODAY_STR, reports_dir=reports_dir)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# 2. _needs_human_review
# ═══════════════════════════════════════════════════════════════

class TestNeedsHumanReview:

    def test_high_score_no_review(self):
        """pub >= 75 不需要人工审核."""
        from src.dashboard import _needs_human_review
        needs, reason = _needs_human_review(85.0)
        assert needs is False
        assert reason == ""

    def test_high_score_boundary_no_review(self):
        """pub == 75 边界值不需要人工审核."""
        from src.dashboard import _needs_human_review
        needs, reason = _needs_human_review(75.0)
        assert needs is False

    def test_low_score_needs_review(self):
        """pub < 60 需要人工审核."""
        from src.dashboard import _needs_human_review
        needs, reason = _needs_human_review(45.0)
        assert needs is True
        assert "审核" in reason

    def test_mid_score_needs_review(self):
        """60 <= pub < 75 需要人工审核（边界提示）."""
        from src.dashboard import _needs_human_review
        needs, reason = _needs_human_review(65.0)
        assert needs is True
        assert "60" in reason or "75" in reason


# ═══════════════════════════════════════════════════════════════
# 3. _suggest_platforms
# ═══════════════════════════════════════════════════════════════

class TestSuggestPlatforms:

    def test_runnable_returns_all_five(self):
        """runnable_project 返回全部 5 个平台."""
        from src.dashboard import _suggest_platforms
        repo = _make_top5_entry(content_type="runnable_project")
        platforms = _suggest_platforms(repo)
        assert len(platforms) == 5
        for p in ["公众号", "小红书", "抖音", "视频号", "GEO"]:
            assert p in platforms

    def test_tutorial_returns_wechat_xiaohongshu(self):
        """tutorial_guide 返回 公众号 + 小红书."""
        from src.dashboard import _suggest_platforms
        repo = _make_top5_entry(content_type="tutorial_guide")
        platforms = _suggest_platforms(repo)
        assert "公众号" in platforms
        assert "小红书" in platforms
        assert "抖音" not in platforms

    def test_framework_returns_wechat_geo(self):
        """framework_platform 返回 公众号 + GEO."""
        from src.dashboard import _suggest_platforms
        repo = _make_top5_entry(content_type="framework_platform")
        platforms = _suggest_platforms(repo)
        assert "公众号" in platforms
        assert "GEO" in platforms


# ═══════════════════════════════════════════════════════════════
# 4. _next_action
# ═══════════════════════════════════════════════════════════════

class TestNextAction:

    def test_published_suggests_mark_published(self):
        """已发布 repo 建议 mark-published."""
        from src.dashboard import _next_action
        repo = _make_top5_entry(publishability_score=85)
        result = _next_action(repo, is_published=True)
        assert "mark-published" in result or "已发布" in result

    def test_high_pub_suggests_publish_flow(self):
        """pub >= 75 建议 publish-flow."""
        from src.dashboard import _next_action
        repo = _make_top5_entry(publishability_score=80)
        result = _next_action(repo, is_published=False)
        assert "publish-flow" in result

    def test_mid_pub_suggests_publish_pack(self):
        """60 <= pub < 75 建议 publish-pack."""
        from src.dashboard import _next_action
        repo = _make_top5_entry(publishability_score=65)
        result = _next_action(repo, is_published=False)
        assert "publish-pack" in result or "review-pack" in result

    def test_low_pub_suggests_review(self):
        """pub < 60 建议 review-pack."""
        from src.dashboard import _next_action
        repo = _make_top5_entry(publishability_score=45)
        result = _next_action(repo, is_published=False)
        assert "review-pack" in result or "审核" in result


# ═══════════════════════════════════════════════════════════════
# 5. generate_dashboard — integration
# ═══════════════════════════════════════════════════════════════

class TestGenerateDashboard:

    def test_all_six_sections_present(self, tmp_path, monkeypatch):
        """输出包含全部 6 个 section headers."""
        from src.dashboard import generate_dashboard

        # Setup: top5 JSON
        reports_dir = tmp_path / "reports"
        entries = [
            _make_top5_entry("test/alpha", publishability_score=85, score=90, stars=5000,
                             content_type="runnable_project", topics=[]),
            _make_top5_entry("test/beta", publishability_score=65, score=70, stars=3000,
                             content_type="tutorial_guide", topics=[]),
        ]
        _write_top5_json(reports_dir / f"top5_{TODAY_STR}.json", entries)

        # Setup: empty publish history
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        # Setup: quality gate report
        qg_report = reports_dir / "system_quality_report_v8.md"
        qg_report.parent.mkdir(parents=True, exist_ok=True)
        qg_report.write_text("Final Verdict: **PASS**\nAdjusted Score: 97.3/100\nPassed 15/15 conditions\n", encoding="utf-8")

        # Setup: seen_repos.json for stats
        (state_dir / "seen_repos.json").write_text(json.dumps({}), encoding="utf-8")
        (state_dir / "generated_repos.json").write_text(json.dumps({}), encoding="utf-8")

        # Redirect constants
        import src.dashboard as dash
        monkeypatch.setattr(dash, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(dash, "STATE_DIR", state_dir)
        monkeypatch.setattr(dash, "PROJECT_ROOT", tmp_path)

        output = generate_dashboard(TODAY_STR)

        # All 6 section headers
        assert "今日最佳候选" in output
        assert "审核判断" in output
        assert "下一步建议" in output
        assert "发布摘要" in output or "发布历史" in output
        assert "系统健康" in output or "Doctor" in output
        assert "管线统计" in output or "统计" in output

    def test_published_repo_marked_in_output(self, tmp_path, monkeypatch):
        """已发布 repo 在输出中被标记."""
        from src.dashboard import generate_dashboard

        reports_dir = tmp_path / "reports"
        entries = [
            _make_top5_entry("test/alpha", publishability_score=85, score=90, stars=5000),
            _make_top5_entry("published/repo", publishability_score=70, score=60, stars=1000),
        ]
        _write_top5_json(reports_dir / f"top5_{TODAY_STR}.json", entries)

        # Setup publish history with published/repo
        from datetime import timezone, datetime
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        history = {
            "published/repo": [{
                "published_at": datetime.now(timezone.utc).isoformat(),
                "published_by": "human",
                "platform": "wechat",
                "url": None,
                "note": "test",
                "pack_dir": "/tmp/test",
                "source_mode": "full_llm",
                "score": 60,
                "publishability_score": 70,
                "content_hashes": {},
            }],
        }
        (state_dir / "publish_history.json").write_text(
            json.dumps(history, ensure_ascii=False), encoding="utf-8")

        # Quality gate
        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")

        (state_dir / "seen_repos.json").write_text(json.dumps({}), encoding="utf-8")
        (state_dir / "generated_repos.json").write_text(json.dumps({}), encoding="utf-8")

        import src.dashboard as dash
        monkeypatch.setattr(dash, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(dash, "STATE_DIR", state_dir)
        monkeypatch.setattr(dash, "PROJECT_ROOT", tmp_path)

        output = generate_dashboard(TODAY_STR)

        # Published repo should be marked
        assert "published/repo" in output
        assert "已发布" in output

    def test_empty_top5_graceful(self, tmp_path, monkeypatch):
        """无 top5 数据时不崩溃，返回合理提示."""
        from src.dashboard import generate_dashboard

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")
        (state_dir / "seen_repos.json").write_text(json.dumps({}), encoding="utf-8")
        (state_dir / "generated_repos.json").write_text(json.dumps({}), encoding="utf-8")

        import src.dashboard as dash
        monkeypatch.setattr(dash, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(dash, "STATE_DIR", state_dir)
        monkeypatch.setattr(dash, "PROJECT_ROOT", tmp_path)

        output = generate_dashboard(TODAY_STR)
        assert "无" in output or "暂无" in output or "今日暂无" in output


# ═══════════════════════════════════════════════════════════════
# 6. cmd_dashboard
# ═══════════════════════════════════════════════════════════════

class TestCmdDashboard:

    def test_returns_zero(self, tmp_path, monkeypatch):
        """cmd_dashboard 总是返回 0（只读命令，不因缺数据而失败）."""
        from src.dashboard import cmd_dashboard

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        (reports_dir / "system_quality_report_v8.md").write_text(
            "Final Verdict: **PASS**\nAdjusted Score: 97.3/100\n", encoding="utf-8")
        (state_dir / "seen_repos.json").write_text(json.dumps({}), encoding="utf-8")
        (state_dir / "generated_repos.json").write_text(json.dumps({}), encoding="utf-8")

        import src.dashboard as dash
        monkeypatch.setattr(dash, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(dash, "STATE_DIR", state_dir)
        monkeypatch.setattr(dash, "PROJECT_ROOT", tmp_path)

        exit_code = cmd_dashboard()
        assert exit_code == 0
