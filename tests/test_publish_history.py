"""Tests for publish_history.py — Phase 21 publish tracking & dedup."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

# Ensure project root on path for imports
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ═════════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════════

PLATFORMS = ["wechat", "xiaohongshu", "douyin", "videohao", "geo"]

SAFE_WECHAT = """# 公众号发布版本 — test/awesome-ai

## 标题：这个开源项目用一行命令解决了我三天的数据清洗工作

### 痛点
数据清洗是每个AI工程师每天都要面对的问题。

### 项目解释
awesome-ai 是一个基于 Python 的数据处理库。

### 技术拆解
1. 自动检测数据格式
2. 智能填充缺失值
3. 异常值识别与处理

### 个人主线
今天学到的是，好的工具让数据工作事半功倍。

**关注我，每天拆解一个AI开源项目。**
"""

SAFE_XHS = """# 小红书发布版本 — test/awesome-ai

📌 这个AI工具太强了

一个命令解决三天数据清洗 💪

✨ 亮点一：自动检测格式
✨ 亮点二：智能填充缺失
✨ 亮点三：异常值识别

#AI工具 #数据科学 #效率提升

评论区告诉我你平时用什么工具洗数据 👇
"""

SAFE_VIDEO = """# 视频脚本 — test/awesome-ai

## 30 秒版

【0-3s 钩子】你有没有花过三天时间只为了洗数据？

【3-15s 核心】这个开源项目用一个命令帮你搞定所有数据预处理。

【25-30s CTA】GitHub 搜 awesome-ai，关注我每天拆解一个AI项目。
"""


# ═════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _isolate_publish_history(tmp_path, monkeypatch):
    """Redirect PUBLISH_HISTORY_FILE to a temp path for test isolation."""
    from src import publish_history
    temp_file = tmp_path / "publish_history.json"
    monkeypatch.setattr(publish_history, "PUBLISH_HISTORY_FILE", temp_file)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _make_pack(tmp_path: Path, status: str = "approved",
               repo: str = "test/awesome-ai") -> Path:
    """Create a mock publish pack with given human_review_status."""
    pack_dir = tmp_path / "publish_pack"
    pack_dir.mkdir(parents=True)

    manifest = {
        "repo": repo,
        "generated_at": "2026-06-01T00:00:00+00:00",
        "source_mode": "full_llm",
        "quality_score": 92,
        "recommendation": "yes",
        "publishable": True,
        "blocking_count": 0,
        "suitable_platforms": ["公众号", "小红书"],
        "files": [
            "00_publish_manifest.json", "README.md",
            "01_wechat_ready.md", "02_xiaohongshu_ready.md",
            "03_video_script_ready.md",
            "04_review_checklist.md", "05_next_actions.md",
        ],
        "manual_review_required": False,
        "risks": [],
        "suggested_publish_order": ["公众号", "小红书"],
        "human_review_status": status,
        "review_history": [],
        "score": 72.0,
        "publishability_score": 68.0,
    }
    if status == "approved":
        manifest["approved_at"] = "2026-06-01T08:00:00+00:00"
        manifest["approved_by"] = "human"

    (pack_dir / "00_publish_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    (pack_dir / "01_wechat_ready.md").write_text(SAFE_WECHAT, encoding="utf-8")
    (pack_dir / "02_xiaohongshu_ready.md").write_text(SAFE_XHS, encoding="utf-8")
    (pack_dir / "03_video_script_ready.md").write_text(SAFE_VIDEO, encoding="utf-8")
    (pack_dir / "README.md").write_text("# Publish pack", encoding="utf-8")
    (pack_dir / "04_review_checklist.md").write_text("# Checklist", encoding="utf-8")
    (pack_dir / "05_next_actions.md").write_text("# Next actions", encoding="utf-8")

    return pack_dir


def _hash_file(filepath: Path) -> str:
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# Constraint 1: approved pack can be mark-published
# ═════════════════════════════════════════════════════════════════════════════


class TestMarkPublishedApproved:
    """approved 状态的 pack 可以 mark-published."""

    def test_approved_pack_can_mark_published_wechat(self, tmp_path):
        """approved pack 第一次 mark-published wechat 成功."""
        from src.publish_history import mark_published

        pack_dir = _make_pack(tmp_path, status="approved")
        result = mark_published(str(pack_dir), platform="wechat")

        assert result["status"] == "ok"
        assert result["platform"] == "wechat"
        assert result["repo"] == "test/awesome-ai"

        # Manifest should be updated to published
        manifest = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        assert manifest["human_review_status"] == "published"
        assert "published_at" in manifest
        assert "wechat" in manifest.get("published_platforms", [])

        # Review history should have the mark-published entry
        history = manifest.get("review_history", [])
        assert any(e["action"] == "mark-published" for e in history)


class TestMarkPublishedMultiPlatform:
    """published 状态的 pack 可以追加新平台."""

    def test_published_pack_can_add_xiaohongshu(self, tmp_path):
        """已发布到 wechat 后，可以追加 xiaohongshu."""
        from src.publish_history import mark_published

        pack_dir = _make_pack(tmp_path, status="approved")

        # First: mark wechat
        r1 = mark_published(str(pack_dir), platform="wechat")
        assert r1["status"] == "ok"

        # Second: mark xiaohongshu on same pack
        r2 = mark_published(str(pack_dir), platform="xiaohongshu", note="morning publish")
        assert r2["status"] == "ok"
        assert r2["platform"] == "xiaohongshu"

        manifest = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        platforms = manifest.get("published_platforms", [])
        assert "wechat" in platforms
        assert "xiaohongshu" in platforms


class TestMarkPublishedDuplicatePlatform:
    """同一 platform 重复 mark 不产生重复记录."""

    def test_same_platform_duplicate_no_duplicate(self, tmp_path):
        """同一个 pack 同一 platform 重复 mark 不追加."""
        from src.publish_history import mark_published, get_publish_history

        pack_dir = _make_pack(tmp_path, status="approved")

        # First mark
        mark_published(str(pack_dir), platform="wechat")
        # Second mark — same platform
        r2 = mark_published(str(pack_dir), platform="wechat")

        # Should indicate already recorded (not a new entry)
        assert r2["status"] in ("duplicate", "already_published")

        # History should have exactly 1 wechat entry
        history = get_publish_history("test/awesome-ai")
        wechat_entries = [e for e in history if e["platform"] == "wechat"]
        assert len(wechat_entries) == 1


# ═════════════════════════════════════════════════════════════════════════════
# Constraint 4: rejected pack cannot be mark-published
# ═════════════════════════════════════════════════════════════════════════════


class TestMarkPublishedRejected:
    """rejected 状态的 pack 不能 mark-published."""

    def test_rejected_pack_cannot_mark_published(self, tmp_path):
        """rejected pack 调用 mark_published 被阻止."""
        from src.publish_history import mark_published

        pack_dir = _make_pack(tmp_path, status="rejected")
        # Update manifest to have rejected fields
        manifest = json.loads((pack_dir / "00_publish_manifest.json").read_text(encoding="utf-8"))
        manifest["rejected_at"] = "2026-06-01T07:00:00+00:00"
        manifest["rejected_reason"] = "content not ready"
        (pack_dir / "00_publish_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        result = mark_published(str(pack_dir), platform="wechat")
        assert result["status"] == "blocked"


# ═════════════════════════════════════════════════════════════════════════════
# Constraint 5: published pack cannot approve/reject/revise
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishedPackBlocksMutations:
    """published 后不能 approve/reject/revise."""

    def test_published_pack_cannot_approve(self, tmp_path):
        """已发布 pack 不能再次 approve."""
        from src.publish_history import mark_published
        from src.publish_review import approve_pack

        pack_dir = _make_pack(tmp_path, status="approved")
        mark_published(str(pack_dir), platform="wechat")

        result = approve_pack(str(pack_dir))
        assert result["status"] == "blocked"
        assert "已发布" in result.get("reason", "")

    def test_published_pack_cannot_reject(self, tmp_path):
        """已发布 pack 不能 reject."""
        from src.publish_history import mark_published
        from src.publish_review import reject_pack

        pack_dir = _make_pack(tmp_path, status="approved")
        mark_published(str(pack_dir), platform="wechat")

        result = reject_pack(str(pack_dir), reason="changed my mind")
        assert result["status"] == "blocked"
        assert "已发布" in result.get("reason", "")

    def test_published_pack_cannot_revise(self, tmp_path):
        """已发布 pack 不能 revise."""
        from src.publish_history import mark_published
        from src.publish_review import revise_pack

        pack_dir = _make_pack(tmp_path, status="approved")
        mark_published(str(pack_dir), platform="wechat")

        result = revise_pack(str(pack_dir))
        assert result["status"] == "blocked"
        assert "已发布" in result.get("reason", "")


# ═════════════════════════════════════════════════════════════════════════════
# Constraint 3: daily/review-queue/publish-flow skip published repos
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishedRepoExcluded:
    """已发布 repo 在候选检测中被过滤."""

    def test_is_published_returns_true(self, tmp_path, monkeypatch):
        """is_published 对已发布 repo 返回 True."""
        from src.publish_history import mark_published, is_published

        pack_dir = _make_pack(tmp_path, status="approved")
        mark_published(str(pack_dir), platform="wechat")

        assert is_published("test/awesome-ai") is True
        assert is_published("test/never-published") is False

    def test_is_published_normalizes_case(self, tmp_path, monkeypatch):
        """is_published 对大小写不敏感."""
        from src.publish_history import mark_published, is_published, normalize_repo

        pack_dir = _make_pack(tmp_path, status="approved")
        mark_published(str(pack_dir), platform="wechat")

        # normalize_repo should lowercase
        assert normalize_repo("Test/Awesome-AI") == "test/awesome-ai"
        # is_published should be case-insensitive
        assert is_published("Test/Awesome-AI") is True

    def test_find_best_skips_published(self, tmp_path, monkeypatch):
        """_find_best_from_review_queue 跳过已发布 repo."""
        from unittest import mock

        from src.publish_history import mark_published

        # Mark test/awesome-ai as published
        pack_dir = _make_pack(tmp_path, status="approved")
        mark_published(str(pack_dir), platform="wechat")

        # Create a top5 JSON where the best candidate is the published one
        top5_data = [
            {"full_name": "test/awesome-ai", "publishability_score": 85, "score": 80, "stars": 1000},
            {"full_name": "other/good-repo", "publishability_score": 75, "score": 70, "stars": 500},
        ]

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        top5_path = reports_dir / "top5_2026-06-01.json"
        top5_path.write_text(json.dumps(top5_data), encoding="utf-8")

        from src.publish_pack import _find_best_from_review_queue
        with mock.patch("src.config.REPORTS_DIR", reports_dir):
            # Mock _find_best_from_content_packs to return None
            with mock.patch("src.publish_pack._find_best_from_content_packs", return_value=None):
                result = _find_best_from_review_queue()
                # Should pick other/good-repo, not test/awesome-ai
                assert result == "other/good-repo"


# ═════════════════════════════════════════════════════════════════════════════
# Constraint 7: publish-history shows multi-platform records
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishHistoryQuery:
    """publish-history 查询功能."""

    def test_publish_history_shows_multi_platform(self, tmp_path, monkeypatch):
        """按 repo 查询展示多平台发布历史."""
        from src.publish_history import mark_published, get_publish_history

        pack_dir = _make_pack(tmp_path, status="approved")

        # Publish to wechat
        mark_published(str(pack_dir), platform="wechat", url="https://mp.weixin.qq.com/s/test")
        # Publish to xiaohongshu
        mark_published(str(pack_dir), platform="xiaohongshu", note="afternoon")

        history = get_publish_history("test/awesome-ai")
        assert len(history) == 2

        platforms = {e["platform"] for e in history}
        assert platforms == {"wechat", "xiaohongshu"}

    def test_publish_history_includes_scores_and_hashes(self, tmp_path):
        """记录包含 score、publishability_score、content_hashes."""
        from src.publish_history import mark_published, get_publish_history

        pack_dir = _make_pack(tmp_path, status="approved")
        mark_published(str(pack_dir), platform="wechat")

        history = get_publish_history("test/awesome-ai")
        entry = history[0]

        assert "score" in entry
        assert "publishability_score" in entry
        assert "content_hashes" in entry
        assert "source_mode" in entry
        assert "pack_dir" in entry
        # Verify content hashes match actual file content
        expected_wechat_hash = _hash_file(pack_dir / "01_wechat_ready.md")
        assert entry["content_hashes"]["01_wechat_ready.md"] == expected_wechat_hash


# ═════════════════════════════════════════════════════════════════════════════
# Constraint 8: data/state/publish_history.json not in git
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishHistoryGitignore:
    """data/state/publish_history.json 必须被 gitignore."""

    def test_publish_history_json_is_gitignored(self):
        """.gitignore 包含 data/state/publish_history.json."""
        root = _project_root
        gitignore_path = root / ".gitignore"
        assert gitignore_path.exists(), ".gitignore not found"

        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
        patterns = {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}

        assert "data/state/publish_history.json" in patterns, \
            "data/state/publish_history.json must be in .gitignore"
