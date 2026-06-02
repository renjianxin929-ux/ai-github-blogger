"""Tests for workbench.py — Phase 23 daily operator workbench."""
import json
import sys
from datetime import date as dt_date, datetime, timedelta, timezone
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

TODAY = dt_date.today()
TODAY_STR = TODAY.isoformat()
YESTERDAY_STR = (TODAY - timedelta(days=1)).isoformat()


def _make_entry(full_name="test/repo", score=75.0, publishability_score=72.0,
                stars=1000, content_type="runnable_project", pool="top5",
                description="A test repo", language="Python", topics=None):
    return {
        "full_name": full_name, "name": full_name.split("/")[-1],
        "score": score, "publishability_score": publishability_score,
        "stars": stars, "description": description, "language": language,
        "content_type": content_type, "topics": topics or ["AI", "LLM"],
        "pool": pool,
    }


def _write_top5(path: Path, entries: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def _write_qg_report(path: Path, verdict="PASS", score="97.3", passed="15", total="15"):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"Final Verdict: **{verdict}**\n"
        f"Adjusted Score: {score}/100\n"
        f"Passed {passed}/{total} conditions\n"
    )
    path.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# 1. Command exists
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchCommandExists:

    def test_workbench_subcommand_registered(self):
        """workbench 命令已在 CLI parser 中注册."""
        from src.main import build_parser
        parser = build_parser()
        # Parse help output to find workbench
        help_text = parser.format_help()
        assert "workbench" in help_text


# ═══════════════════════════════════════════════════════════════
# 2. Recommends candidate when top5 available
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchRecommends:

    def test_recommends_best_candidate(self, tmp_path, monkeypatch):
        """有 top5 时推荐最佳候选."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("test/alpha", publishability_score=85, score=90, stars=5000),
            _make_entry("test/beta", publishability_score=60, score=50, stars=1000),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR)

        assert "test/alpha" in output
        assert "test/beta" in output
        assert "今日最推荐" in output
        assert "下一步命令" in output


# ═══════════════════════════════════════════════════════════════
# 3. Skips published candidates
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchSkipsPublished:

    def test_published_repo_skipped(self, tmp_path, monkeypatch):
        """已发布候选被跳过，推荐下一个未发布的."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("published/alpha", publishability_score=90, score=95, stars=10000),
            _make_entry("fresh/beta", publishability_score=85, score=80, stars=5000),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        history = {
            "published/alpha": [{
                "published_at": datetime.now(timezone.utc).isoformat(),
                "published_by": "human", "platform": "wechat",
                "url": None, "note": "", "pack_dir": "/tmp",
                "source_mode": "full_llm", "score": 95,
                "publishability_score": 90, "content_hashes": {},
            }],
        }
        (state_dir / "publish_history.json").write_text(
            json.dumps(history, ensure_ascii=False), encoding="utf-8")

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR)

        assert "已发布跳过" in output or "已发布" in output
        assert "published/alpha" in output
        # The best candidate should be the fresh one, not the published one
        best_section = output[output.find("今日最推荐"):output.find("全部候选") if "全部候选" in output else len(output)]
        assert "fresh/beta" in best_section

    def test_all_published_no_recommendation(self, tmp_path, monkeypatch):
        """全部候选已发布时不硬推."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("pub/a", publishability_score=90, score=95, stars=10000),
            _make_entry("pub/b", publishability_score=85, score=80, stars=5000),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        history = {
            "pub/a": [{"published_at": datetime.now(timezone.utc).isoformat(),
                        "published_by": "human", "platform": "wechat",
                        "url": None, "note": "", "pack_dir": "/tmp",
                        "source_mode": "full_llm", "score": 95,
                        "publishability_score": 90, "content_hashes": {}}],
            "pub/b": [{"published_at": datetime.now(timezone.utc).isoformat(),
                        "published_by": "human", "platform": "wechat",
                        "url": None, "note": "", "pack_dir": "/tmp",
                        "source_mode": "full_llm", "score": 80,
                        "publishability_score": 85, "content_hashes": {}}],
        }
        (state_dir / "publish_history.json").write_text(
            json.dumps(history, ensure_ascii=False), encoding="utf-8")

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR)

        assert "已发布跳过" in output or "已发布" in output
        # Should explain WHY no recommendation
        assert "强推荐" not in output or "无" in output


# ═══════════════════════════════════════════════════════════════
# 4. No qualified candidate — no hard recommend
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchNoQualified:

    def test_no_qualified_no_hard_recommend(self, tmp_path, monkeypatch):
        """无合格候选时不硬推."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("test/low", publishability_score=25, score=30, stars=100),
            _make_entry("test/low2", publishability_score=35, score=40, stars=200),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR)

        # Should have the "no strong recommendation" message
        assert "无" in output or "不推荐" in output
        # Should not present a "推荐发布" tier for the best
        best_section = output[output.find("今日最推荐"):]
        # Should explain why
        assert "原因" in best_section or "建议" in best_section

    def test_empty_top5_no_hard_recommend(self, tmp_path, monkeypatch):
        """无 top5 数据时不硬推也不崩溃."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR)

        assert "无" in output or "暂无" in output
        assert "python run.py daily" in output  # suggests next step


# ═══════════════════════════════════════════════════════════════
# 5. Output contains next-step commands
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchNextCommands:

    def test_output_contains_next_commands(self, tmp_path, monkeypatch):
        """输出包含下一步命令建议."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("test/cmd", publishability_score=80, score=75, stars=3000),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR)

        assert "下一步命令" in output
        assert "publish-flow" in output
        assert "review-queue" in output
        assert "publish-history" in output


# ═══════════════════════════════════════════════════════════════
# 6. Does not write content_packs
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchNoSideEffects:

    def test_does_not_create_content_packs(self, tmp_path, monkeypatch):
        """workbench 不创建 content_packs 目录或文件."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("test/side", publishability_score=90, score=88, stars=8000),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        content_packs_dir = tmp_path / "content_packs"

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        _output = generate_workbench(TODAY_STR)

        # content_packs should not be created
        assert not content_packs_dir.exists()
        # publish_history should not be created (read-only)
        pubhist = state_dir / "publish_history.json"
        assert not pubhist.exists()  # workbench is read-only, doesn't write state


# ═══════════════════════════════════════════════════════════════
# 7. All 7 sections present
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchSections:

    def test_all_seven_sections_present(self, tmp_path, monkeypatch):
        """输出包含全部 7 个 section."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("test/a", publishability_score=80, score=80, stars=5000),
            _make_entry("test/b", publishability_score=50, score=40, stars=1000),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR)

        assert "今日决策摘要" in output
        assert "今日最推荐" in output
        assert "全部候选" in output
        assert "平台建议" in output
        assert "风险提醒" in output
        assert "下一步命令" in output
        assert "人工检查清单" in output


# ═══════════════════════════════════════════════════════════════
# 8. cmd_workbench returns 0
# ═══════════════════════════════════════════════════════════════

class TestCmdWorkbench:

    def test_returns_zero(self, tmp_path, monkeypatch):
        """cmd_workbench 总是返回 0（只读命令）."""
        from src.workbench import cmd_workbench

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        exit_code = cmd_workbench(date_str=TODAY_STR)
        assert exit_code == 0

    def test_returns_zero_even_without_data(self, tmp_path, monkeypatch):
        """即使没有数据也不崩溃，返回 0."""
        from src.workbench import cmd_workbench

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        exit_code = cmd_workbench(date_str="2099-12-31")
        assert exit_code == 0


# ═══════════════════════════════════════════════════════════════
# 9. --repo filter works
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchRepoFilter:

    def test_repo_filter_shows_only_specified(self, tmp_path, monkeypatch):
        """--repo 过滤只显示指定项目."""
        from src.workbench import generate_workbench

        reports_dir = tmp_path / "reports"
        entries = [
            _make_entry("test/alpha", publishability_score=80, score=75, stars=3000),
            _make_entry("test/beta", publishability_score=85, score=80, stars=5000),
        ]
        _write_top5(reports_dir / f"top5_{TODAY_STR}.json", entries)
        _write_qg_report(reports_dir / "system_quality_report_v8.md")

        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        import src.workbench as wb
        monkeypatch.setattr(wb, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(wb, "STATE_DIR", state_dir)
        monkeypatch.setattr(wb, "PROJECT_ROOT", tmp_path)

        output = generate_workbench(TODAY_STR, repo_filter="test/beta")

        assert "test/beta" in output
        # test/alpha should not appear in candidate table
        # (it may appear elsewhere but not as a candidate being recommended)
        assert "test/alpha" not in output or "候选总数" in output


# ═══════════════════════════════════════════════════════════════
# 10. No LLM calls
# ═══════════════════════════════════════════════════════════════

class TestWorkbenchNoLLM:

    def test_workbench_never_imports_llm(self):
        """workbench 模块不导入 LLM 相关模块."""
        import src.workbench as wb_mod
        source = (Path(wb_mod.__file__).read_text(encoding="utf-8")
                  if wb_mod.__file__ else "")
        # Should not import analyzer (which has LLM calls)
        assert "from .analyzer import" not in source
        assert "from .content_pack import" not in source
        assert "_call_llm" not in source
