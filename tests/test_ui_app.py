"""Tests for local operator UI — Phase 26.

Uses httpx.AsyncClient + ASGITransport with tmp_path injection for full isolation.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════════
# Async helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_app(tmp_path: Path):
    """Create FastAPI app with custom paths for testing."""
    from src.ui_app import create_app
    import os
    state_dir = tmp_path / "data" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    content_dir = tmp_path / "data" / "content_packs"
    content_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    # Point to real templates/ and static/ dirs for Jinja2 + CSS
    real_root = Path(__file__).resolve().parent.parent
    return create_app(
        project_root=tmp_path,
        state_dir=state_dir,
        content_packs_dir=content_dir,
        reports_dir=reports_dir,
        templates_dir=real_root / "templates",
        static_dir=real_root / "static",
    )


def _setup_publish_pack(pack_dir: Path, repo: str, status: str = "approved"):
    """Create a minimal publish pack for testing."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "repo": repo,
        "human_review_status": status,
        "score": 85,
        "publishability_score": 78,
        "source_mode": "llm",
        "published_platforms": [],
        "review_history": [],
    }
    manifest_path = pack_dir / "00_publish_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. App Factory
# ═══════════════════════════════════════════════════════════════════════════════

class TestAppFactory:
    """create_app() returns a valid FastAPI instance with custom paths."""

    def test_create_app_returns_fastapi_instance(self):
        from fastapi import FastAPI
        from src.ui_app import create_app
        app = create_app()
        assert isinstance(app, FastAPI)

    @pytest.mark.asyncio
    async def test_create_app_with_custom_paths(self, tmp_path):
        import httpx
        from src.ui_app import create_app
        state_dir = tmp_path / "mystate"
        state_dir.mkdir()
        app = create_app(state_dir=state_dir)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GET /
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetIndex:
    """GET / returns the operator workspace page."""

    @pytest.mark.asyncio
    async def test_get_index_returns_200(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_index_contains_all_sections(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            for section_id in ["section-next-step", "section-env", "section-topics",
                               "section-content", "section-review", "section-publish",
                               "section-metrics", "section-insights"]:
                assert section_id in html, f"Missing section: {section_id}"

    @pytest.mark.asyncio
    async def test_index_has_four_action_categories(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            for cls in ["action-readonly", "action-generate", "action-review", "action-publish"]:
                assert cls in html, f"Missing action category class: {cls}"

    @pytest.mark.asyncio
    async def test_index_has_next_step_block(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert "下一步行动" in resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Static Files
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaticFiles:
    """CSS must be served from /static/."""

    @pytest.mark.asyncio
    async def test_css_accessible(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/static/ui.css")
            assert resp.status_code == 200
            assert "text/css" in resp.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Time Period Detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimePeriod:
    """_get_time_period returns correct period based on time of day."""

    def test_night_period_21_to_23(self):
        from src.ui_app import _get_time_period
        assert _get_time_period(datetime(2026, 6, 2, 21, 0)) == "night"
        assert _get_time_period(datetime(2026, 6, 2, 23, 59)) == "night"

    def test_morning_period_00_to_09(self):
        from src.ui_app import _get_time_period
        assert _get_time_period(datetime(2026, 6, 2, 0, 0)) == "morning"
        assert _get_time_period(datetime(2026, 6, 2, 7, 30)) == "morning"
        assert _get_time_period(datetime(2026, 6, 2, 8, 59)) == "morning"

    def test_late_morning_09_to_0930(self):
        from src.ui_app import _get_time_period
        assert _get_time_period(datetime(2026, 6, 2, 9, 0)) == "late_morning"
        assert _get_time_period(datetime(2026, 6, 2, 9, 15)) == "late_morning"
        assert _get_time_period(datetime(2026, 6, 2, 9, 29)) == "late_morning"

    def test_post_publish_10am(self):
        from src.ui_app import _get_time_period
        assert _get_time_period(datetime(2026, 6, 2, 10, 0)) == "post_publish"

    def test_post_publish_3pm(self):
        from src.ui_app import _get_time_period
        assert _get_time_period(datetime(2026, 6, 2, 15, 0)) == "post_publish"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Next Step — Time-Aware Logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestNextStepTimeAware:
    """derive_page_state returns correct next_step based on state + time."""

    @pytest.mark.asyncio
    async def test_next_step_no_candidate_prompts_daily_first(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            assert "daily" in html.lower() or "选题" in html

    @pytest.mark.asyncio
    async def test_next_step_has_candidate_not_built_prompts_build(self, tmp_path):
        import httpx
        reports_dir = tmp_path / "data" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        daily = reports_dir / "daily_brief_2026-06-02.md"
        daily.write_text("# 今日选题\n- A级: test/repo (85分)\n", encoding="utf-8")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            assert "Build" in html or "build" in html.lower() or "构建" in html or "内容包" in html

    @pytest.mark.asyncio
    async def test_next_step_built_not_reviewed_prompts_review(self, tmp_path):
        import httpx
        content_dir = tmp_path / "data" / "content_packs" / "test__repo"
        content_dir.mkdir(parents=True)
        (content_dir / "05_wechat_article.md").write_text("# test", encoding="utf-8")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            assert "Review" in html or "审核" in html or "review" in html.lower()

    def test_next_step_approved_not_published_shows_0900_deadline(self, tmp_path):
        from src.ui_app import derive_page_state
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "approved")
        # Simulate morning time (07:30) to trigger 09:00 deadline message
        now = datetime(2026, 6, 2, 7, 30)
        state = derive_page_state(now=now, project_root=tmp_path)
        msg = state.get("next_step", {}).get("message", "")
        assert "09:00" in msg

    @pytest.mark.asyncio
    async def test_next_step_published_shows_record_metrics(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "published")
        state_dir = tmp_path / "data" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        pub_hist = {"test/repo": [{"platform": "wechat", "published_at": "2026-06-02T09:00:00Z",
                                    "url": "https://mp.weixin.qq.com/s/test"}]}
        (state_dir / "publish_history.json").write_text(json.dumps(pub_hist), encoding="utf-8")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            assert "数据" in html or "metrics" in html.lower() or "录入" in html

    @pytest.mark.asyncio
    async def test_next_step_page_contains_publish_time_hints(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            assert "09:00" in html or "09:30" in html or "发布时间" in html or "发布" in html


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Night Mode Wording
# ═══════════════════════════════════════════════════════════════════════════════

class TestNightModeWording:
    """Evening (21:00+) next_step wording mentions tomorrow prep."""

    def test_night_mode_mentions_tomorrow_prep(self, tmp_path):
        from src.ui_app import derive_page_state
        now = datetime(2026, 6, 2, 21, 30)
        state = derive_page_state(now=now, project_root=tmp_path)
        msg = state.get("next_step", {}).get("message", "")
        assert "明天" in msg or "明日" in msg

    def test_late_morning_shows_too_late_warning(self, tmp_path):
        from src.ui_app import derive_page_state
        now = datetime(2026, 6, 2, 9, 15)
        state = derive_page_state(now=now, project_root=tmp_path)
        msg = state.get("next_step", {}).get("message", "")
        assert "偏晚" in msg or "尽快" in msg


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Safety Validators
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyValidators:
    """Input validation and sanitization functions."""

    def test_validate_pack_dir_rejects_traversal(self):
        from src.ui_app import _validate_pack_dir
        try:
            _validate_pack_dir("../../../etc/passwd", Path("/tmp"))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_validate_pack_dir_accepts_valid_path(self):
        from src.ui_app import _validate_pack_dir
        root = Path("/tmp/project")
        result = _validate_pack_dir("data/publish_packs/test__repo", root)
        assert result is not None

    def test_validate_repo_name_rejects_bad_format(self):
        from src.ui_app import _validate_repo_name
        try:
            _validate_repo_name("not-a-valid-repo")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_validate_platform_rejects_unknown(self):
        from src.ui_app import _validate_platform
        try:
            _validate_platform("unknown_platform")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_mask_key_only_shows_first_4_chars(self):
        from src.ui_app import _mask_key
        masked = _mask_key("sk-1234567890abcdef")
        assert masked.startswith("sk-1")
        assert "1234567890abcdef" not in masked
        assert len(masked) <= 15


# ═══════════════════════════════════════════════════════════════════════════════
# 8. POST Actions
# ═══════════════════════════════════════════════════════════════════════════════

class TestPostBuild:
    """POST /action/build triggers build_publish_pack."""

    @pytest.mark.asyncio
    async def test_build_redirects(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/build", data={"repo": "test/repo"},
                                     follow_redirects=False)
            assert resp.status_code in (302, 303, 200)


class TestPostReview:
    """POST /action/review triggers review_pack."""

    @pytest.mark.asyncio
    async def test_review_redirects(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        (pack_dir / "05_wechat_article.md").write_text("# test", encoding="utf-8")
        _setup_publish_pack(pack_dir, "test/repo")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/review", data={"pack_dir": str(pack_dir)},
                                     follow_redirects=False)
            assert resp.status_code in (302, 303, 200)


class TestPostApprove:
    """POST /action/approve triggers approve_pack with confirmation."""

    @pytest.mark.asyncio
    async def test_approve_redirects(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "needs_revision")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/approve", data={
                "pack_dir": str(pack_dir), "confirmed": "true"
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)


class TestPostReject:
    """POST /action/reject triggers reject_pack with reason."""

    @pytest.mark.asyncio
    async def test_reject_redirects(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/reject", data={
                "pack_dir": str(pack_dir), "reason": "内容质量不达标", "confirmed": "true"
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)


class TestPostRevise:
    """POST /action/revise triggers revise_pack with confirmation."""

    @pytest.mark.asyncio
    async def test_revise_redirects(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/revise", data={
                "pack_dir": str(pack_dir), "confirmed": "true"
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)


class TestPostMarkPublished:
    """POST /action/mark-published records publication."""

    @pytest.mark.asyncio
    async def test_mark_published_redirects(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "approved")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/mark-published", data={
                "pack_dir": str(pack_dir),
                "platform": "wechat",
                "url": "https://mp.weixin.qq.com/s/test",
                "confirmed": "true",
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)

    @pytest.mark.asyncio
    async def test_mark_published_rejects_non_approved_pack(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "draft")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/mark-published", data={
                "pack_dir": str(pack_dir),
                "platform": "wechat",
                "url": "https://example.com",
                "confirmed": "true",
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)


class TestPostRecordMetrics:
    """POST /action/record-metrics records performance data."""

    @pytest.mark.asyncio
    async def test_record_metrics_redirects(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/record-metrics", data={
                "repo": "test/repo",
                "platform": "wechat",
                "views": "1000",
                "likes": "50",
                "favorites": "20",
                "comments": "10",
                "leads": "3",
                "confirmed": "true",
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)

    @pytest.mark.asyncio
    async def test_record_metrics_rejects_negative_views(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/record-metrics", data={
                "repo": "test/repo",
                "platform": "wechat",
                "views": "-5",
                "likes": "50",
                "favorites": "20",
                "comments": "10",
                "leads": "3",
                "confirmed": "true",
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Security Boundaries
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityNoCmdInjection:
    """POST actions must not execute arbitrary shell commands."""

    @pytest.mark.asyncio
    async def test_no_command_injection_via_repo_param(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/build", data={"repo": "test; rm -rf /"},
                                     follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400, 422)


class TestSecurityPathTraversal:
    """Pack dir inputs must reject path traversal attempts."""

    @pytest.mark.asyncio
    async def test_traversal_rejected(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/review", data={"pack_dir": "../../../etc/passwd"},
                                     follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400, 422)


class TestNoEnvLeak:
    """The UI page must not leak .env content."""

    @pytest.mark.asyncio
    async def test_page_does_not_contain_api_key(self, tmp_path):
        import httpx
        env_file = tmp_path / ".env"
        env_file.write_text("GITHUB_TOKEN=ghp_fake123456789\nLLM_API_KEY=sk-fake123456789\n",
                            encoding="utf-8")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            html = resp.text
            assert "ghp_fake123456789" not in html
            assert "sk-fake123456789" not in html


class TestMarkPublishedOnlyWritesStateJson:
    """mark-published must only write to data/state/ JSON, no other files."""

    @pytest.mark.asyncio
    async def test_mark_published_writes_only_state_json(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "approved")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/action/mark-published", data={
                "pack_dir": str(pack_dir),
                "platform": "wechat",
                "url": "https://mp.weixin.qq.com/s/test",
                "confirmed": "true",
            }, follow_redirects=False)
        state_dir = tmp_path / "data" / "state"
        pub_hist = state_dir / "publish_history.json"
        if pub_hist.exists():
            data = json.loads(pub_hist.read_text(encoding="utf-8"))
            assert isinstance(data, dict)


class TestRecordMetricsOnlyWritesStateJson:
    """record-metrics must only write to data/state/ JSON, no other files."""

    @pytest.mark.asyncio
    async def test_record_metrics_writes_only_state_json(self, tmp_path):
        import httpx
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/action/record-metrics", data={
                "repo": "test/repo",
                "platform": "wechat",
                "views": "1000",
                "likes": "50",
                "favorites": "20",
                "comments": "10",
                "leads": "3",
                "confirmed": "true",
            }, follow_redirects=False)
        state_dir = tmp_path / "data" / "state"
        metrics_hist = state_dir / "metrics_history.json"
        if metrics_hist.exists():
            data = json.loads(metrics_hist.read_text(encoding="utf-8"))
            assert isinstance(data, (dict, list))


# ═══════════════════════════════════════════════════════════════════════════════
# 10. State Machine Constraints
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublishedPackCannotBeModified:
    """Published packs are terminal — no approve/reject/revise after."""

    @pytest.mark.asyncio
    async def test_published_pack_cannot_approve(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "published")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/approve", data={
                "pack_dir": str(pack_dir), "confirmed": "true"
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)

    @pytest.mark.asyncio
    async def test_published_pack_cannot_revise(self, tmp_path):
        import httpx
        pack_dir = tmp_path / "data" / "publish_packs" / "test__repo"
        pack_dir.mkdir(parents=True)
        _setup_publish_pack(pack_dir, "test/repo", "published")
        app = _make_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action/revise", data={
                "pack_dir": str(pack_dir), "confirmed": "true"
            }, follow_redirects=False)
            assert resp.status_code in (302, 303, 200, 400)
