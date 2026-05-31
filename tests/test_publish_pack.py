"""Tests for publish_pack.py — Phase 17 publish handoff builder."""
import json
from pathlib import Path
from unittest import mock

import pytest


MANIFEST_LLM = {
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

MANIFEST_FALLBACK = {
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


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _setup_content_pack(base_dir: Path, slug: str, manifest: dict) -> Path:
    """Create a mock content pack directory with manifest."""
    cp_dir = base_dir / slug
    cp_dir.mkdir(parents=True)
    (cp_dir / "_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return cp_dir


# ═════════════════════════════════════════════════════════════════════════════
# CLI command tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishPackCLI:
    """Verify the publish-pack subcommand is registered and dispatch works."""

    def test_publish_pack_command_exists(self):
        """publish-pack should be a registered subcommand."""
        from src.main import build_parser

        parser = build_parser()
        subcommands = []
        for action in parser._actions:
            if getattr(action, 'choices', None) is not None:
                subcommands = list(action.choices.keys())
                break

        assert "publish-pack" in subcommands

    def test_publish_pack_accepts_optional_repo_arg(self):
        """publish-pack should accept an optional repo argument."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["publish-pack"])
        assert args.command == "publish-pack"
        assert args.repo is None

        args = parser.parse_args(["publish-pack", "owner/repo"])
        assert args.repo == "owner/repo"

    @mock.patch("src.main.build_publish_pack")
    def test_cmd_publish_pack_returns_0_on_ok(self, mock_build):
        """cmd_publish_pack returns 0 when build succeeds."""
        from src.main import cmd_publish_pack

        mock_build.return_value = {
            "status": "ok",
            "pack_dir": "/tmp/pub/2026-01-01_test__awesome-ai",
            "repo": "test/awesome-ai",
            "files": ["00_publish_manifest.json", "README.md"],
            "manifest": {
                "source_mode": "full_llm",
                "quality_score": 92,
                "publishable": True,
                "suitable_platforms": ["公众号"],
                "manual_review_required": False,
            },
            "warnings": [],
        }

        rc = cmd_publish_pack("test/awesome-ai")
        assert rc == 0

    @mock.patch("src.main.build_publish_pack")
    def test_cmd_publish_pack_returns_1_on_no_candidate(self, mock_build):
        """cmd_publish_pack returns 1 when no qualified candidate exists."""
        from src.main import cmd_publish_pack

        mock_build.return_value = {
            "status": "no_candidate",
            "pack_dir": None,
            "repo": None,
            "files": [],
            "manifest": None,
            "warnings": ["今日无合格发布候选"],
        }

        rc = cmd_publish_pack()
        assert rc == 1


# ═════════════════════════════════════════════════════════════════════════════
# Core logic tests — use tmp_path correctly (CONTENT_PACKS_DIR = base,
# then build_publish_pack appends slug via CONTENT_PACKS_DIR / slug)
# ═════════════════════════════════════════════════════════════════════════════


class TestBuildPublishPack:
    """Test build_publish_pack core logic."""

    def test_build_pack_with_specified_repo_full_llm(self, tmp_path):
        """When a repo with full_llm manifest exists, build returns ok with publishable=true."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__awesome-ai", MANIFEST_LLM)
        (cp_base / "test__awesome-ai" / "05_wechat_article.md").write_text("# WX", encoding="utf-8")
        (cp_base / "test__awesome-ai" / "02_xiaohongshu.md").write_text("# XHS", encoding="utf-8")

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/awesome-ai")

        assert result["status"] == "ok"
        assert result["repo"] == "test/awesome-ai"
        assert result["manifest"]["source_mode"] == "full_llm"
        assert result["manifest"]["publishable"] is True
        assert result["manifest"]["manual_review_required"] is False
        assert "公众号" in result["manifest"]["suitable_platforms"]
        assert "小红书" in result["manifest"]["suitable_platforms"]

    def test_build_pack_with_structured_fallback(self, tmp_path):
        """structured_fallback repos: manual_review_required=true, publishable=false."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__fallback-project", MANIFEST_FALLBACK)

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/fallback-project")

        assert result["status"] == "ok"
        assert result["manifest"]["publishable"] is False
        assert result["manifest"]["manual_review_required"] is True
        assert len(result["warnings"]) >= 1
        assert any("structured_fallback" in w for w in result["warnings"])

    def test_generated_files_are_in_publish_packs_dir(self, tmp_path):
        """All generated files must be in the publish_packs subdirectory."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__awesome-ai", MANIFEST_LLM)

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/awesome-ai")

        pack_dir = result["pack_dir"]
        assert "publish_packs" in pack_dir.replace("\\", "/")
        for fname in result["files"]:
            fpath = pub_base / Path(pack_dir).name / fname
            assert fpath.exists(), f"Expected {fname} to exist"

    def test_all_seven_files_generated(self, tmp_path):
        """build_publish_pack should generate exactly 7 files per pack."""
        from src.publish_pack import build_publish_pack, PACK_FILES

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__awesome-ai", MANIFEST_LLM)

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/awesome-ai")

        assert len(result["files"]) == 7
        expected_names = set(PACK_FILES.values())
        actual_names = set(result["files"])
        assert actual_names == expected_names

    def test_no_candidate_when_all_below_threshold(self, tmp_path):
        """Returns no_candidate when all top5 scores are below threshold."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        cp_base.mkdir(parents=True)
        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack._find_best_from_review_queue", return_value=None), \
             mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack()

        assert result["status"] == "no_candidate"
        assert result["pack_dir"] is None

    def test_no_candidate_when_no_top5_data(self, tmp_path):
        """Returns no_candidate when _find_best_from_review_queue returns None."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        cp_base.mkdir(parents=True)
        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack._find_best_from_review_queue", return_value=None), \
             mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack()

        assert result["status"] == "no_candidate"

    def test_auto_detects_best_from_top5_json(self, tmp_path):
        """When no repo specified, auto-detects from review queue data."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "best__qualified-project", MANIFEST_LLM)
        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack._find_best_from_review_queue",
                        return_value="best/qualified-project"), \
             mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack()

        assert result["status"] == "ok"
        assert "qualified-project" in result["repo"]

    def test_manifest_contains_all_required_fields(self, tmp_path):
        """The generated manifest JSON should include all required metadata fields."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__awesome-ai", MANIFEST_LLM)

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/awesome-ai")

        m = result["manifest"]
        required_fields = [
            "repo", "generated_at", "source_mode", "quality_score",
            "recommendation", "publishable", "blocking_count",
            "suitable_platforms", "files", "manual_review_required",
            "risks", "suggested_publish_order",
        ]
        for field in required_fields:
            assert field in m, f"Manifest missing required field: {field}"

    def test_rendered_readme_includes_risk_warnings(self, tmp_path):
        """README.md should include risk warnings when structured_fallback."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__fallback-project", MANIFEST_FALLBACK)

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/fallback-project")

        readme_path = pub_base / Path(result["pack_dir"]).name / "README.md"
        readme = readme_path.read_text(encoding="utf-8")
        assert "风险提示" in readme
        assert "structured_fallback" in readme

    def test_review_checklist_includes_publish_decision(self, tmp_path):
        """04_review_checklist.md should ask for final publish decision."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__awesome-ai", MANIFEST_LLM)

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/awesome-ai")

        checklist_path = pub_base / Path(result["pack_dir"]).name / "04_review_checklist.md"
        checklist = checklist_path.read_text(encoding="utf-8")
        assert "可发布" in checklist
        assert "修改后发布" in checklist
        assert "不发布" in checklist


# ═════════════════════════════════════════════════════════════════════════════
# Edge case tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishPackEdgeCases:
    """Test edge cases for publish pack generation."""

    def test_build_pack_with_no_content_pack_files(self, tmp_path):
        """When content pack dir exists but has no files, still generates skeleton pack."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        _setup_content_pack(cp_base, "test__empty-project", MANIFEST_LLM)

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/empty-project")

        assert result["status"] == "ok"
        assert len(result["files"]) == 7

    def test_build_pack_with_no_manifest(self, tmp_path):
        """When content pack dir has no manifest, defaults cautiously (publishable=False)."""
        from src.publish_pack import build_publish_pack

        cp_base = tmp_path / "content_packs"
        (cp_base / "test__no-manifest").mkdir(parents=True)
        # No _manifest.json

        pub_base = tmp_path / "publish_packs"

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base), \
             mock.patch("src.publish_pack.PUBLISH_PACKS_DIR", pub_base):
            result = build_publish_pack("test/no-manifest")

        assert result["status"] == "ok"
        assert result["manifest"]["publishable"] is False

    def test_high_risk_blocked_repo_not_selected(self, tmp_path):
        """Repos with blocking>0 should not be auto-selected via _find_best_from_content_packs."""
        from src.publish_pack import _find_best_from_content_packs

        cp_base = tmp_path / "content_packs"

        _setup_content_pack(cp_base, "bad__blocked-repo", {
            "repo": "bad/blocked-repo",
            "quality_review_score": 90,
            "quality_review_recommendation": "no",
            "blocking": 3,
        })
        _setup_content_pack(cp_base, "good__clean-repo", {
            "repo": "good/clean-repo",
            "quality_review_score": 80,
            "quality_review_recommendation": "yes",
            "blocking": 0,
        })

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", cp_base):
            best = _find_best_from_content_packs()

        assert best == "good/clean-repo"

    def test_no_candidate_when_content_packs_empty(self):
        """_find_best_from_content_packs returns None when no manifests exist."""
        from src.publish_pack import _find_best_from_content_packs

        with mock.patch("src.publish_pack.CONTENT_PACKS_DIR", Path("/nonexistent/path")):
            best = _find_best_from_content_packs()

        assert best is None
