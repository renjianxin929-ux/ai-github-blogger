"""Smoke tests for Phase 19 publish-flow — end-to-end integration.

Uses tmp_path with real file I/O, mocking only directory constants.
Validates: build → review → approve/reject/revise full chain.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

FULL_LLM_MANIFEST = {
    "repo": "test/awesome-ai",
    "mode": "full_llm",
    "content_mode": "full_llm",
    "quality_review_score": 92,
    "quality_review_recommendation": "yes",
    "blocking": 0,
    "files_generated": 11,
    "files_degraded": 0,
    "files_failed": 0,
}

FALLBACK_MANIFEST = {
    "repo": "test/fallback-project",
    "mode": "structured_fallback",
    "content_mode": "structured_fallback",
    "quality_review_score": 65,
    "quality_review_recommendation": "review",
    "blocking": 1,
    "files_generated": 11,
    "files_degraded": 3,
    "files_failed": 0,
}

SAFE_WECHAT = """# 公众号发布版本 — test/awesome-ai

## 标题：这个开源项目用一行命令解决了我三天的数据清洗工作

### 痛点
数据清洗是每个AI工程师每天都要面对的问题。

### 项目解释
awesome-ai 是一个基于 Python 的数据处理库。

### 技术拆解
1. 自动检测数据格式
2. 智能填充缺失值

### 风险边界
本工具不能绕过任何安全措施，使用前请检查数据来源的合规性。

### 个人主线
今天学到的是，好的工具让数据工作事半功倍。

**关注我，每天拆解一个AI开源项目。**
"""

SAFE_XHS = """# 小红书发布版本 — test/awesome-ai

📌 这个AI工具太强了

一个命令解决三天数据清洗 💪

✨ 亮点一：自动检测格式
✨ 亮点二：智能填充缺失

不能绕过任何安全措施哦～

#AI工具 #数据科学 #效率提升

评论区告诉我你平时用什么工具洗数据 👇
"""

SAFE_VIDEO = """# 视频脚本 — test/awesome-ai

## 30 秒版

【0-3s 钩子】你有没有花过三天时间只为了洗数据？

【3-15s 核心】这个开源项目用一个命令帮你搞定所有数据预处理。

【25-30s CTA】GitHub 搜 awesome-ai，关注我每天拆解一个AI项目。
"""

RISKY_WECHAT = """# 公众号发布版本 — test/bad-project

## 万能爬虫帮你抓取任何网站

保证排名第一，绝对可以绕过所有反爬。

全自动发布到全平台，无需人工。
"""


def _create_content_pack(base_dir: Path, slug: str, manifest: dict,
                         files: dict | None = None) -> Path:
    """Create a mock content pack directory with _manifest.json and content files."""
    cp_dir = base_dir / slug
    cp_dir.mkdir(parents=True)
    (cp_dir / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    default_files = {
        "05_wechat_article.md": SAFE_WECHAT,
        "02_xiaohongshu.md": SAFE_XHS,
        "03_douyin_video.md": SAFE_VIDEO,
        "04_videohao_script.md": SAFE_VIDEO,
    }
    for fname, content in (files or default_files).items():
        (cp_dir / fname).write_text(content, encoding="utf-8")

    return cp_dir


def _create_top5_json(reports_dir: Path, repos: list[dict]) -> Path:
    """Create a top5_{today}.json file in reports_dir."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    top5_path = reports_dir / f"top5_{today}.json"
    top5_path.write_text(json.dumps(repos, ensure_ascii=False, indent=2), encoding="utf-8")
    return top5_path


# ═════════════════════════════════════════════════════════════════════════════
# Full chain smoke tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishFlowEndToEnd:
    """Integration tests for the complete publish flow chain."""

    def test_full_chain_ready_pack_flow(self, tmp_path):
        """完整链路：build → review → approve，验证所有文件生成和 manifest 更新."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        content_dir.mkdir()
        publish_dir.mkdir()

        slug = "test__awesome-ai"
        _create_content_pack(content_dir, slug, FULL_LLM_MANIFEST)

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir):
            from src.publish_pack import build_publish_pack
            from src.publish_review import review_pack, approve_pack

            # Step 1: Build
            result = build_publish_pack("test/awesome-ai")
            assert result["status"] == "ok"
            pack_dir = Path(result["pack_dir"])
            assert pack_dir.exists()
            assert (pack_dir / "00_publish_manifest.json").exists()

            # Step 2: Review
            report = review_pack(str(pack_dir))
            assert report.verdict == "ready"
            assert (pack_dir / "06_review_report.md").exists()

            # Step 3: Approve
            result = approve_pack(str(pack_dir))
            assert result["status"] == "ok"
            assert (pack_dir / "07_handoff_summary.md").exists()

            # Verify manifest updated
            manifest = json.loads(
                (pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
            assert manifest["human_review_status"] == "approved"
            assert "approved_at" in manifest
            assert "review_history" in manifest

    def test_full_chain_needs_revision_flow(self, tmp_path):
        """build → review（needs_revision）→ revise 链路."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        content_dir.mkdir()
        publish_dir.mkdir()

        slug = "test__fallback-project"
        _create_content_pack(content_dir, slug, FALLBACK_MANIFEST)

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir):
            from src.publish_pack import build_publish_pack
            from src.publish_review import review_pack, revise_pack

            result = build_publish_pack("test/fallback-project")
            pack_dir = Path(result["pack_dir"])

            report = review_pack(str(pack_dir))
            # structured_fallback produces publishable=False → quality issues → not ready
            assert report.verdict in ("needs_revision", "rejected")

            if report.verdict == "needs_revision":
                rev_result = revise_pack(str(pack_dir))
                assert rev_result["status"] == "ok"
                assert (pack_dir / "07_revision_notes.md").exists()

    def test_full_chain_rejected_flow(self, tmp_path):
        """含阻断词的包 → review 返回 rejected."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        content_dir.mkdir()
        publish_dir.mkdir()

        slug = "test__bad-project"
        risky_files = {"05_wechat_article.md": RISKY_WECHAT}
        _create_content_pack(content_dir, slug, FULL_LLM_MANIFEST, files=risky_files)

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir):
            from src.publish_pack import build_publish_pack
            from src.publish_review import review_pack

            result = build_publish_pack("test/bad-project")
            pack_dir = Path(result["pack_dir"])

            report = review_pack(str(pack_dir))
            assert report.verdict == "rejected"
            assert len(report.blocking_issues) > 0
            assert (pack_dir / "06_review_report.md").exists()

    def test_publish_flow_auto_detect(self, tmp_path):
        """无参数自动检测：从 top5 JSON 选择最佳候选."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        reports_dir = tmp_path / "reports"
        for d in [content_dir, publish_dir, reports_dir]:
            d.mkdir()

        slug = "test__awesome-ai"
        _create_content_pack(content_dir, slug, FULL_LLM_MANIFEST)
        _create_top5_json(reports_dir, [
            {"full_name": "test/awesome-ai", "score": 92, "stars": 1500},
            {"full_name": "test/other", "score": 60, "stars": 300},
        ])

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir), \
             mock.patch("src.config.REPORTS_DIR", reports_dir):
            from src.publish_pack import build_publish_pack

            result = build_publish_pack()  # No repo specified
            assert result["status"] == "ok"
            assert result["repo"] == "test/awesome-ai"

    def test_publish_flow_with_explicit_repo(self, tmp_path):
        """指定 repo 参数直接构建."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        content_dir.mkdir()
        publish_dir.mkdir()

        slug = "test__awesome-ai"
        _create_content_pack(content_dir, slug, FULL_LLM_MANIFEST)

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir):
            from src.publish_pack import build_publish_pack

            result = build_publish_pack("test/awesome-ai")
            assert result["status"] == "ok"
            assert "test/awesome-ai" in result["repo"]

    def test_approved_pack_cannot_reject(self, tmp_path):
        """已批准的包不能再拒绝."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        content_dir.mkdir()
        publish_dir.mkdir()

        slug = "test__awesome-ai"
        _create_content_pack(content_dir, slug, FULL_LLM_MANIFEST)

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir):
            from src.publish_pack import build_publish_pack
            from src.publish_review import review_pack, approve_pack, reject_pack

            result = build_publish_pack("test/awesome-ai")
            pack_dir = str(result["pack_dir"])
            review_pack(pack_dir)
            approve_pack(pack_dir)

            reject_result = reject_pack(pack_dir, "should be blocked")
            assert reject_result["status"] != "ok"

    def test_rejected_pack_cannot_approve(self, tmp_path):
        """已拒绝的包不能再批准."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        content_dir.mkdir()
        publish_dir.mkdir()

        slug = "test__awesome-ai"
        _create_content_pack(content_dir, slug, FULL_LLM_MANIFEST)

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir):
            from src.publish_pack import build_publish_pack
            from src.publish_review import review_pack, approve_pack, reject_pack

            result = build_publish_pack("test/awesome-ai")
            pack_dir = str(result["pack_dir"])
            review_pack(pack_dir)
            reject_pack(pack_dir, "not good enough")

            approve_result = approve_pack(pack_dir)
            assert approve_result["status"] != "ok"

    def test_publish_flow_output_files_complete(self, tmp_path):
        """验证发布包输出文件完整性（00-07 + README）."""
        content_dir = tmp_path / "content_packs"
        publish_dir = tmp_path / "publish_packs"
        content_dir.mkdir()
        publish_dir.mkdir()

        slug = "test__awesome-ai"
        _create_content_pack(content_dir, slug, FULL_LLM_MANIFEST)

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", content_dir), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", publish_dir):
            from src.publish_pack import build_publish_pack
            from src.publish_review import review_pack, approve_pack

            result = build_publish_pack("test/awesome-ai")
            pack_dir = Path(result["pack_dir"])
            review_pack(str(pack_dir))
            approve_pack(str(pack_dir))

            expected_files = [
                "00_publish_manifest.json",
                "README.md",
                "01_wechat_ready.md",
                "02_xiaohongshu_ready.md",
                "03_video_script_ready.md",
                "04_review_checklist.md",
                "05_next_actions.md",
                "06_review_report.md",
                "07_handoff_summary.md",
            ]
            for fname in expected_files:
                assert (pack_dir / fname).exists(), f"Missing: {fname}"


class TestPublishFlowCLI:
    """Verify the publish-flow subcommand is registered."""

    def test_publish_flow_command_exists(self):
        """publish-flow should be a registered subcommand."""
        from src.main import build_parser

        parser = build_parser()
        subcommands = []
        for action in parser._actions:
            if getattr(action, 'choices', None) is not None:
                subcommands = list(action.choices.keys())
                break

        assert "publish-flow" in subcommands
