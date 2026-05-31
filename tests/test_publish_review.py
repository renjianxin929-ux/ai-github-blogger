"""Tests for publish_review.py — Phase 18 publish review & human editing loop."""
import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

# ═════════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════════

MANIFEST_PHASE17_FIELDS = [
    "repo", "generated_at", "source_mode", "quality_score",
    "recommendation", "publishable", "blocking_count",
    "suitable_platforms", "files", "manual_review_required",
    "risks", "suggested_publish_order",
]

SAFE_WECHAT_CONTENT = """# 公众号发布版本 — test/awesome-ai

## 标题：这个开源项目用一行命令解决了我三天的数据清洗工作

### 痛点
数据清洗是每个AI工程师每天都要面对的问题，而我发现了一个神器。

### 项目解释
awesome-ai 是一个基于 Python 的数据处理库，它封装了常见的清洗逻辑。

### 技术拆解
1. 自动检测数据格式
2. 智能填充缺失值
3. 异常值识别与处理
4. 支持自定义清洗规则

### 适用场景
- 数据预处理
- ETL 流程

### 风险边界
本工具不能绕过任何安全措施，使用前请检查数据来源的合规性。
robots.txt 合规是使用者的责任。

### 个人主线
今天学到的是，好的工具让数据工作事半功倍。

**关注我，每天拆解一个AI开源项目。**
"""

SAFE_XHS_CONTENT = """# 小红书发布版本 — test/awesome-ai

📌 这个AI工具太强了

一个命令解决三天数据清洗 💪

✨ 亮点一：自动检测格式
✨ 亮点二：智能填充缺失
✨ 亮点三：异常值识别

不能绕过任何安全措施哦～

#AI工具 #数据科学 #效率提升

评论区告诉我你平时用什么工具洗数据 👇
"""

SAFE_VIDEO_CONTENT = """# 视频脚本 — test/awesome-ai

## 30 秒版

【0-3s 钩子】你有没有花过三天时间只为了洗数据？

【3-15s 核心】这个开源项目用一个命令帮你搞定所有数据预处理。

【15-25s 场景】支持Python，pip install 即用。

【25-30s CTA】GitHub 搜 awesome-ai，关注我每天拆解一个AI项目。
"""

SAFE_README_CONTENT = """# 发布包 — test/awesome-ai

## 项目信息

- **项目**: test/awesome-ai
- **内容模式**: full_llm

## 风险提示
- 无阻断性风险

## 文件清单
| 文件 | 用途 |
|------|------|
| 00_publish_manifest.json | 元数据 |
"""

SAFE_CHECKLIST_CONTENT = """# 人工审稿清单 — test/awesome-ai

- [ ] **可发布** — 所有检查项通过，可以复制到平台发布
- [ ] **修改后发布** — 有少量需要修改的地方
- [ ] **不发布** — 存在阻断性问题
"""

SAFE_NEXT_ACTIONS_CONTENT = """# 下一步动作

## 今天怎么发
1. 公众号
"""

RISKY_WECHAT_CONTENT = """# 公众号发布版本 — test/bad-project

## 万能爬虫帮你抓取任何网站

保证排名第一，绝对可以绕过所有反爬。

全自动发布到全平台，无需人工。
"""

NO_CTA_WECHAT_CONTENT = """# 公众号发布版本 — test/no-cta

## 标题：一个好项目

这是一个很棒的项目的介绍。

技术细节很多很多。

但没有任何 CTA。
"""


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def _make_pack_dir(tmp_path: Path, manifest_overrides: dict | None = None,
                   files: dict | None = None) -> Path:
    """Create a mock publish pack directory with manifest and content files.

    Args:
        tmp_path: pytest tmp_path fixture
        manifest_overrides: dict merged on top of default manifest
        files: dict of filename -> content (or None to skip)
               If not specified, creates a complete safe pack.

    Returns:
        Path to the created pack directory.
    """
    pack_dir = tmp_path / "publish_pack"
    pack_dir.mkdir(parents=True)

    # Default manifest
    manifest = {
        "repo": "test/awesome-ai",
        "generated_at": "2026-05-31T00:00:00+00:00",
        "source_mode": "full_llm",
        "quality_score": 92,
        "recommendation": "yes",
        "publishable": True,
        "blocking_count": 0,
        "suitable_platforms": ["公众号", "小红书"],
        "files": [
            "00_publish_manifest.json",
            "README.md",
            "01_wechat_ready.md",
            "02_xiaohongshu_ready.md",
            "03_video_script_ready.md",
            "04_review_checklist.md",
            "05_next_actions.md",
        ],
        "manual_review_required": False,
        "risks": [],
        "suggested_publish_order": ["公众号", "小红书"],
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)

    (pack_dir / "00_publish_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Default content files
    default_files = {
        "README.md": SAFE_README_CONTENT,
        "01_wechat_ready.md": SAFE_WECHAT_CONTENT,
        "02_xiaohongshu_ready.md": SAFE_XHS_CONTENT,
        "03_video_script_ready.md": SAFE_VIDEO_CONTENT,
        "04_review_checklist.md": SAFE_CHECKLIST_CONTENT,
        "05_next_actions.md": SAFE_NEXT_ACTIONS_CONTENT,
    }

    files_to_write = files if files is not None else default_files
    for fname, content in files_to_write.items():
        if content is not None:
            (pack_dir / fname).write_text(content, encoding="utf-8")

    return pack_dir


# ═════════════════════════════════════════════════════════════════════════════
# TestReviewPack
# ═════════════════════════════════════════════════════════════════════════════


class TestReviewPack:
    """Test review_pack function."""

    def test_review_complete_pack_verdict_ready(self, tmp_path):
        """完整合规包 → verdict=ready."""
        from src.publish_review import review_pack

        pack_dir = _make_pack_dir(tmp_path)
        report = review_pack(str(pack_dir))

        assert report.verdict == "ready"
        assert report.blocking_issues == []
        assert report.overall_score >= 80

    def test_review_missing_file_needs_revision(self, tmp_path):
        """缺少核心平台文件 → needs_revision."""
        from src.publish_review import review_pack

        pack_dir = _make_pack_dir(tmp_path, files={
            "00_publish_manifest.json": None,  # use default manifest
            "README.md": SAFE_README_CONTENT,
            "01_wechat_ready.md": None,  # missing — won't create
            "02_xiaohongshu_ready.md": None,  # missing
            "03_video_script_ready.md": None,  # missing
            "04_review_checklist.md": SAFE_CHECKLIST_CONTENT,
            "05_next_actions.md": SAFE_NEXT_ACTIONS_CONTENT,
        })
        # Note: manifest is still created by _make_pack_dir
        report = review_pack(str(pack_dir))

        assert report.verdict in ("needs_revision", "rejected")
        assert len(report.blocking_issues) >= 1

    def test_review_pack_with_risk_phrases_rejected(self, tmp_path):
        """含阻断性风险词 → rejected."""
        from src.publish_review import review_pack

        pack_dir = _make_pack_dir(tmp_path, files={
            "README.md": SAFE_README_CONTENT,
            "01_wechat_ready.md": RISKY_WECHAT_CONTENT,
            "02_xiaohongshu_ready.md": SAFE_XHS_CONTENT,
            "03_video_script_ready.md": SAFE_VIDEO_CONTENT,
            "04_review_checklist.md": SAFE_CHECKLIST_CONTENT,
            "05_next_actions.md": SAFE_NEXT_ACTIONS_CONTENT,
        })
        report = review_pack(str(pack_dir))

        assert report.verdict == "rejected"
        assert report.risk_blocking_count >= 1
        assert len(report.blocking_issues) >= 1

    def test_review_pack_without_cta_needs_revision(self, tmp_path):
        """平台文件缺 CTA → needs_revision 或 rejected."""
        from src.publish_review import review_pack

        pack_dir = _make_pack_dir(tmp_path, files={
            "README.md": SAFE_README_CONTENT,
            "01_wechat_ready.md": NO_CTA_WECHAT_CONTENT,
            "02_xiaohongshu_ready.md": SAFE_XHS_CONTENT,
            "03_video_script_ready.md": SAFE_VIDEO_CONTENT,
            "04_review_checklist.md": SAFE_CHECKLIST_CONTENT,
            "05_next_actions.md": SAFE_NEXT_ACTIONS_CONTENT,
        })
        report = review_pack(str(pack_dir))

        # Missing CTA should be flagged
        assert report.verdict != "ready"
        cta_issues = report.cta_issues
        assert len(cta_issues) >= 1 or len(report.revision_suggestions) >= 1

    def test_review_wechat_missing_title(self, tmp_path):
        """公众号缺少标题 → 问题列出."""
        from src.publish_review import review_pack

        bad_wechat = "# 公众号发布版本 — test/awesome-ai\n\n直接开始正文，没有标题。\n\n关注我。"
        pack_dir = _make_pack_dir(tmp_path, files={
            "README.md": SAFE_README_CONTENT,
            "01_wechat_ready.md": bad_wechat,
            "02_xiaohongshu_ready.md": SAFE_XHS_CONTENT,
            "03_video_script_ready.md": SAFE_VIDEO_CONTENT,
            "04_review_checklist.md": SAFE_CHECKLIST_CONTENT,
            "05_next_actions.md": SAFE_NEXT_ACTIONS_CONTENT,
        })
        report = review_pack(str(pack_dir))

        wechat_check = report.file_checks.get("01_wechat_ready.md")
        assert wechat_check is not None
        assert len(wechat_check.custom_issues) >= 1

    def test_review_report_filename_is_06(self, tmp_path):
        """review-pack 生成的报告文件名必须是 06_review_report.md."""
        from src.publish_review import review_pack

        pack_dir = _make_pack_dir(tmp_path)
        review_pack(str(pack_dir))

        report_path = pack_dir / "06_review_report.md"
        assert report_path.exists(), "Expected 06_review_report.md to be generated"

    def test_review_report_contains_all_sections(self, tmp_path):
        """审核报告必须包含所有必要章节."""
        from src.publish_review import review_pack

        pack_dir = _make_pack_dir(tmp_path)
        review_pack(str(pack_dir))

        report_content = (pack_dir / "06_review_report.md").read_text(encoding="utf-8")
        assert "审核" in report_content or "review" in report_content.lower()
        assert "verdict" in report_content.lower() or "判决" in report_content or "结论" in report_content


# ═════════════════════════════════════════════════════════════════════════════
# TestApprovePack
# ═════════════════════════════════════════════════════════════════════════════


class TestApprovePack:
    """Test approve_pack function — each test creates its own independent pack."""

    def test_approve_ready_pack_succeeds(self, tmp_path):
        """ready 包可以 approve."""
        from src.publish_review import approve_pack

        pack_dir = _make_pack_dir(tmp_path)
        result = approve_pack(str(pack_dir))

        assert result["status"] == "ok"
        assert result["human_review_status"] == "approved"

    def test_approve_updates_manifest(self, tmp_path):
        """approve 后 manifest 增加 human_review_status/approved_at/approved_by."""
        from src.publish_review import approve_pack

        pack_dir = _make_pack_dir(tmp_path)
        approve_pack(str(pack_dir))

        manifest = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        assert manifest["human_review_status"] == "approved"
        assert "approved_at" in manifest
        assert "approved_by" in manifest

    def test_approve_generates_handoff_summary(self, tmp_path):
        """approve 生成 07_handoff_summary.md."""
        from src.publish_review import approve_pack

        pack_dir = _make_pack_dir(tmp_path)
        approve_pack(str(pack_dir))

        handoff = pack_dir / "07_handoff_summary.md"
        assert handoff.exists(), "Expected 07_handoff_summary.md to be generated"

    def test_approve_fails_when_no_manifest(self, tmp_path):
        """缺 manifest 时报错."""
        from src.publish_review import approve_pack

        pack_dir = tmp_path / "no_manifest_pack"
        pack_dir.mkdir()

        result = approve_pack(str(pack_dir))
        assert result["status"] != "ok"

    def test_needs_revision_pack_cannot_approve(self, tmp_path):
        """needs_revision 包不能 approve."""
        from src.publish_review import approve_pack

        pack_dir = _make_pack_dir(tmp_path, files={
            "README.md": SAFE_README_CONTENT,
            # Missing all platform files → needs_revision or worse
            "01_wechat_ready.md": None,
            "02_xiaohongshu_ready.md": None,
            "03_video_script_ready.md": None,
            "04_review_checklist.md": SAFE_CHECKLIST_CONTENT,
            "05_next_actions.md": SAFE_NEXT_ACTIONS_CONTENT,
        })
        result = approve_pack(str(pack_dir))

        assert result["status"] != "ok"

    def test_rejected_pack_cannot_approve(self, tmp_path):
        """先 reject 的独立 pack 不能再 approve."""
        from src.publish_review import reject_pack, approve_pack

        pack_dir = _make_pack_dir(tmp_path)
        reject_pack(str(pack_dir), "测试拒绝")

        result = approve_pack(str(pack_dir))
        assert result["status"] != "ok"
        assert "拒绝" in str(result) or "rejected" in str(result).lower()

    def test_already_approved_pack_cannot_approve_again(self, tmp_path):
        """已 approved 的包不能再次 approve."""
        from src.publish_review import approve_pack

        pack_dir = _make_pack_dir(tmp_path)
        approve_pack(str(pack_dir))

        result = approve_pack(str(pack_dir))
        assert result["status"] != "ok"


# ═════════════════════════════════════════════════════════════════════════════
# TestRejectPack
# ═════════════════════════════════════════════════════════════════════════════


class TestRejectPack:
    """Test reject_pack function — each test creates its own independent pack."""

    def test_reject_updates_manifest_with_reason(self, tmp_path):
        """拒绝后 manifest 记录 rejected_reason + rejected_at."""
        from src.publish_review import reject_pack

        pack_dir = _make_pack_dir(tmp_path)
        reject_pack(str(pack_dir), "质量不达标，需重写")

        manifest = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        assert manifest["human_review_status"] == "rejected"
        assert "rejected_at" in manifest
        assert manifest["rejected_reason"] == "质量不达标，需重写"

    def test_reject_preserves_all_files(self, tmp_path):
        """拒绝后所有原文件仍存在."""
        from src.publish_review import reject_pack

        pack_dir = _make_pack_dir(tmp_path)
        before_files = set(f.name for f in pack_dir.iterdir() if f.is_file())

        reject_pack(str(pack_dir), "preserve test")

        after_files = set(f.name for f in pack_dir.iterdir() if f.is_file())
        # All original files still present (plus possibly new 07 file)
        assert before_files.issubset(after_files)

    def test_reject_without_reason_fails(self, tmp_path):
        """缺 --reason 时报错."""
        from src.publish_review import reject_pack

        pack_dir = _make_pack_dir(tmp_path)

        result = reject_pack(str(pack_dir), "")
        assert result["status"] != "ok"

        result = reject_pack(str(pack_dir), "   ")
        assert result["status"] != "ok"

    def test_reject_generates_rejection_record(self, tmp_path):
        """生成 07_rejection_record.md."""
        from src.publish_review import reject_pack

        pack_dir = _make_pack_dir(tmp_path)
        reject_pack(str(pack_dir), "test rejection reason")

        record = pack_dir / "07_rejection_record.md"
        assert record.exists(), "Expected 07_rejection_record.md to be generated"
        content = record.read_text(encoding="utf-8")
        assert "test rejection reason" in content

    def test_already_approved_pack_cannot_reject(self, tmp_path):
        """已 approved 的独立 pack 不能 reject."""
        from src.publish_review import approve_pack, reject_pack

        pack_dir = _make_pack_dir(tmp_path)
        approve_pack(str(pack_dir))

        result = reject_pack(str(pack_dir), "try reject approved pack")
        assert result["status"] != "ok"
        assert "批准" in str(result) or "approved" in str(result).lower()


# ═════════════════════════════════════════════════════════════════════════════
# TestRevisePack
# ═════════════════════════════════════════════════════════════════════════════


class TestRevisePack:
    """Test revise_pack function — each test creates its own independent pack."""

    def test_revise_generates_revision_notes(self, tmp_path):
        """生成 07_revision_notes.md."""
        from src.publish_review import revise_pack

        pack_dir = _make_pack_dir(tmp_path)
        revise_pack(str(pack_dir))

        notes = pack_dir / "07_revision_notes.md"
        assert notes.exists(), "Expected 07_revision_notes.md to be generated"

    def test_revise_does_not_modify_content_files(self, tmp_path):
        """01/02/03/04/05 hash 不变 — revise 绝不修改正文."""
        from src.publish_review import revise_pack

        pack_dir = _make_pack_dir(tmp_path)
        content_files = [
            "01_wechat_ready.md",
            "02_xiaohongshu_ready.md",
            "03_video_script_ready.md",
            "04_review_checklist.md",
            "05_next_actions.md",
        ]
        before_hashes = {f: _sha256(pack_dir / f) for f in content_files if (pack_dir / f).exists()}

        revise_pack(str(pack_dir))

        for fname, before_hash in before_hashes.items():
            after_hash = _sha256(pack_dir / fname)
            assert after_hash == before_hash, f"{fname} was modified by revise_pack!"

    def test_revise_content_files_hash_unchanged(self, tmp_path):
        """revise-pack 后正文文件 hash 不变（更全面的检查）."""
        from src.publish_review import revise_pack

        pack_dir = _make_pack_dir(tmp_path)
        # Only check content files, not manifest (manifest gets review_history updates)
        content_files = {
            "01_wechat_ready.md", "02_xiaohongshu_ready.md",
            "03_video_script_ready.md", "04_review_checklist.md",
            "05_next_actions.md", "README.md",
        }
        before_hashes = {f.name: _sha256(f) for f in pack_dir.iterdir()
                         if f.is_file() and f.name in content_files}

        revise_pack(str(pack_dir))

        for fname, before_hash in before_hashes.items():
            current = pack_dir / fname
            if current.exists():
                after_hash = _sha256(current)
                assert after_hash == before_hash, f"{fname} was modified!"

    def test_already_approved_pack_cannot_revise(self, tmp_path):
        """已 approved 的独立 pack 不能 revise."""
        from src.publish_review import approve_pack, revise_pack

        pack_dir = _make_pack_dir(tmp_path)
        approve_pack(str(pack_dir))

        result = revise_pack(str(pack_dir))
        assert result["status"] != "ok"
        assert "批准" in str(result) or "approved" in str(result).lower()


# ═════════════════════════════════════════════════════════════════════════════
# TestManifestHistory
# ═════════════════════════════════════════════════════════════════════════════


class TestManifestHistory:
    """Test review_history in manifest."""

    def test_manifest_review_history_appended(self, tmp_path):
        """review/approve/reject/revise 都在 review_history 追加记录."""
        from src.publish_review import review_pack, approve_pack

        pack_dir = _make_pack_dir(tmp_path)

        # Run review_pack on this pack
        review_pack(str(pack_dir))
        manifest1 = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        history1 = manifest1.get("review_history", [])
        assert len(history1) >= 1, "review_pack should add to review_history"

        # Then approve
        approve_pack(str(pack_dir))
        manifest2 = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        history2 = manifest2.get("review_history", [])
        assert len(history2) >= len(history1) + 1, "approve_pack should append to review_history"

    def test_review_history_contains_required_fields(self, tmp_path):
        """每条 review_history 记录含 action, status/verdict, timestamp."""
        from src.publish_review import review_pack

        pack_dir = _make_pack_dir(tmp_path)
        review_pack(str(pack_dir))

        manifest = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        history = manifest.get("review_history", [])
        assert len(history) >= 1

        for entry in history:
            assert "action" in entry, f"Entry missing 'action': {entry}"
            assert "timestamp" in entry, f"Entry missing 'timestamp': {entry}"
            # Either status or verdict should be present
            has_status = "status" in entry or "verdict" in entry
            assert has_status, f"Entry missing status/verdict: {entry}"


# ═════════════════════════════════════════════════════════════════════════════
# TestCLI
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishReviewCLI:
    """Verify Phase 18 subcommands are registered."""

    def test_review_pack_command_exists(self):
        """review-pack should be a registered subcommand."""
        from src.main import build_parser

        parser = build_parser()
        subcommands = []
        for action in parser._actions:
            if getattr(action, 'choices', None) is not None:
                subcommands = list(action.choices.keys())
                break

        assert "review-pack" in subcommands

    def test_approve_pack_command_exists(self):
        """approve-pack should be a registered subcommand."""
        from src.main import build_parser

        parser = build_parser()
        subcommands = []
        for action in parser._actions:
            if getattr(action, 'choices', None) is not None:
                subcommands = list(action.choices.keys())
                break

        assert "approve-pack" in subcommands

    def test_reject_pack_command_exists(self):
        """reject-pack should be a registered subcommand."""
        from src.main import build_parser

        parser = build_parser()
        subcommands = []
        for action in parser._actions:
            if getattr(action, 'choices', None) is not None:
                subcommands = list(action.choices.keys())
                break

        assert "reject-pack" in subcommands

    def test_revise_pack_command_exists(self):
        """revise-pack should be a registered subcommand."""
        from src.main import build_parser

        parser = build_parser()
        subcommands = []
        for action in parser._actions:
            if getattr(action, 'choices', None) is not None:
                subcommands = list(action.choices.keys())
                break

        assert "revise-pack" in subcommands

    def test_reject_pack_requires_reason(self):
        """reject-pack 的 --reason 参数是必需的."""
        from src.main import build_parser

        parser = build_parser()

        # Should parse OK with --reason
        args = parser.parse_args(["reject-pack", "some/pack", "--reason", "test"])
        assert args.reason == "test"

    @mock.patch("src.main.review_pack")
    def test_cmd_review_pack_returns_0_on_ok(self, mock_review, tmp_path):
        """cmd_review_pack returns 0 on success."""
        from src.main import cmd_review_pack
        from src.publish_review import ReviewReport, FileCheckResult

        pack_dir = _make_pack_dir(tmp_path)
        mock_review.return_value = ReviewReport(
            verdict="ready",
            overall_score=95,
            file_checks={
                "01_wechat_ready.md": FileCheckResult(status="pass", score=95, custom_issues=[], custom_suggestions=[]),
            },
            risk_issues=[],
            risk_blocking_count=0,
            cta_issues=[],
            blocking_issues=[],
            revision_suggestions=[],
        )
        rc = cmd_review_pack(str(pack_dir))
        assert rc == 0

    @mock.patch("src.main.approve_pack")
    def test_cmd_approve_pack_returns_0_on_ok(self, mock_approve, tmp_path):
        """cmd_approve_pack returns 0 on success."""
        from src.main import cmd_approve_pack

        pack_dir = _make_pack_dir(tmp_path)
        mock_approve.return_value = {
            "status": "ok",
            "human_review_status": "approved",
        }
        rc = cmd_approve_pack(str(pack_dir))
        assert rc == 0

    @mock.patch("src.main.approve_pack")
    def test_cmd_approve_pack_returns_1_on_fail(self, mock_approve, tmp_path):
        """cmd_approve_pack returns 1 when gate fails."""
        from src.main import cmd_approve_pack

        pack_dir = _make_pack_dir(tmp_path)
        mock_approve.return_value = {
            "status": "blocked",
            "reason": "verdict is needs_revision",
        }
        rc = cmd_approve_pack(str(pack_dir))
        assert rc == 1

    @mock.patch("src.main.reject_pack")
    def test_cmd_reject_pack_returns_0_on_ok(self, mock_reject, tmp_path):
        """cmd_reject_pack returns 0 on success."""
        from src.main import cmd_reject_pack

        pack_dir = _make_pack_dir(tmp_path)
        mock_reject.return_value = {
            "status": "ok",
            "human_review_status": "rejected",
        }
        rc = cmd_reject_pack(str(pack_dir), "test reason")
        assert rc == 0

    @mock.patch("src.main.revise_pack")
    def test_cmd_revise_pack_returns_0_on_ok(self, mock_revise, tmp_path):
        """cmd_revise_pack returns 0 on success."""
        from src.main import cmd_revise_pack

        pack_dir = _make_pack_dir(tmp_path)
        mock_revise.return_value = {
            "status": "ok",
            "notes_file": "07_revision_notes.md",
        }
        rc = cmd_revise_pack(str(pack_dir))
        assert rc == 0
