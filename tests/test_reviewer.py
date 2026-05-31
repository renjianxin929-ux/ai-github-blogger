"""Tests for reviewer.py — post-generation content review pipeline."""
import pytest


class TestRepoConsistencyCheck:
    """Test repo_consistency_check."""

    def test_passes_for_correct_content(self):
        """Should pass when content is about the right repo."""
        from src.reviewer import repo_consistency_check

        content = "# Firecrawl 深度拆解\n\nFirecrawl 是一个网页抓取工具，支持 scrape、crawl、search 等功能。"
        result = repo_consistency_check(content, "firecrawl/firecrawl")

        assert result.passed
        assert result.score >= 60

    def test_detects_wrong_project_signals_when_3plus(self):
        """Should detect 3+ wrong-project signals for a web_scraping_api project."""
        from src.reviewer import repo_consistency_check

        content = (
            "# Firecrawl 深度拆解\n\n"
            "该项目将 RAG 流程模块化，支持 Milvus 和 Chroma 向量数据库。\n"
            "深度适配 ChatGLM 和 Baichuan 等国内开源模型。\n"
            "非 AI 工程师也能一键构建知识库问答系统。\n"
        )
        result = repo_consistency_check(
            content, "firecrawl/firecrawl", project_type="web_scraping_api",
        )

        assert not result.passed
        assert len(result.issues) >= 3

    def test_tolerates_1_or_2_signals(self):
        """Should tolerate 1-2 wrong-project signals (may appear in README excerpts)."""
        from src.reviewer import repo_consistency_check

        # Only 1 signal — should pass with reduced score
        content = "# Test\n\nFirecrawl 不同于向量数据库如 Pinecone，它是数据采集层。"
        result = repo_consistency_check(content, "firecrawl/firecrawl")

        # 1 signal is below the 3-signal threshold → should pass
        assert result.passed


class TestClaimGroundingCheck:
    """Test claim_grounding_check."""

    def test_passes_for_grounded_content(self):
        """Should pass when claims are reasonable."""
        from src.reviewer import claim_grounding_check

        content = "# Test\n\n该项目提供了网页抓取 API，支持多种输出格式。"
        result = claim_grounding_check(content)

        assert result.passed

    def test_detects_unverified_claims(self):
        """Should flag absolute claims like '唯一' and '完美解决'."""
        from src.reviewer import claim_grounding_check

        content = "这是唯一能完美解决网页抓取问题的工具，覆盖 100% 的网页。"
        result = claim_grounding_check(content)

        assert len(result.issues) >= 1


class TestRiskBoundaryCheck:
    """Test risk_boundary_check."""

    def test_passes_for_safe_content(self):
        """Should pass when content has proper risk disclaimers."""
        from src.reviewer import risk_boundary_check

        content = (
            "# 风险边界\n\n"
            "使用前请遵守目标网站的 robots.txt。本项目不是绕过工具。"
            "大规模抓取需要注意版权和隐私合规。"
        )
        result = risk_boundary_check(content)

        assert result.passed

    def test_detects_exaggerated_claims(self):
        """Should flag phrases like '任意网页' and '绕过限制'."""
        from src.reviewer import risk_boundary_check

        content = "这个工具可以抓取任意网页，自动绕过反爬限制，像真人一样浏览。"
        result = risk_boundary_check(content)

        assert not result.passed
        assert len(result.issues) >= 3  # 任意网页, 绕过反爬, 像真人一样

    def test_scraping_api_blocks_hard_promises(self):
        """web_scraping_api should block '保证 AI 引用' as forbidden claim."""
        from src.reviewer import risk_boundary_check

        content = "使用 Firecrawl 可以保证提升 AI 引用和排名。"
        result = risk_boundary_check(content, project_type="web_scraping_api")

        assert not result.passed
        assert any("保证" in i for i in result.issues)

    def test_scraping_tool_missing_disclaimers_strict(self):
        """In strict mode, web_scraping_api should flag missing disclaimers."""
        from src.reviewer import risk_boundary_check

        content = "这个爬虫工具非常好用，可以抓取各种网站数据。"
        result = risk_boundary_check(content, project_type="web_scraping_api", strict_mode=True)

        assert not result.passed
        assert any("风险提醒" in i for i in result.issues)

    def test_scraping_tool_non_strict_skips_disclaimers(self):
        """In non-strict mode, should NOT flag missing disclaimers (only explicit exaggerations)."""
        from src.reviewer import risk_boundary_check

        content = "这个爬虫工具很好用，可以抓取公开网站数据。使用前请注意合规。"
        result = risk_boundary_check(content, strict_mode=False)

        # No exaggerated claims → should pass even without full disclaimers
        assert result.passed


class TestPlatformStyleCheck:
    """Test platform_style_check."""

    def test_xiaohongshu_style(self):
        """Should check for xiaohongshu-specific style requirements."""
        from src.reviewer import platform_style_check

        content = "今天拆了一个项目 \U0001f914 卡片式分享 评论区聊聊？建议收藏~"
        result = platform_style_check(content, "xiaohongshu")

        assert result.passed

    def test_wechat_should_not_be_soft_ad(self):
        """WeChat article should have learning perspective."""
        from src.reviewer import platform_style_check

        content = "立即购买！限时优惠！加我微信了解更多。"
        result = platform_style_check(content, "wechat_article")

        assert not result.passed


class TestRunReviewerPipeline:
    """Test run_reviewer_pipeline end-to-end."""

    def test_clean_content_passes(self):
        """Clean, well-written content should pass all checks."""
        from src.reviewer import run_reviewer_pipeline

        content = (
            "# Firecrawl 深度拆解\n\n"
            "## 核心能力\n\n"
            "Firecrawl 提供网页抓取 API，可将网页转为 Markdown 格式。\n"
            "## 风险边界\n\n"
            "使用前请遵守 robots.txt 和网站服务条款。\n"
            "大规模抓取需要注意版权和隐私合规。\n"
        )

        ctx = {
            "confirmed_features": ["网页抓取 API", "HTML → Markdown 转换"],
            "unsupported_features": ["知识库平台", "向量数据库"],
            "risk_boundaries": ["遵守 robots.txt", "注意版权合规"],
        }

        outcome = run_reviewer_pipeline(
            "05_wechat_article", content, "firecrawl/firecrawl", ctx=ctx,
        )

        assert outcome.passed
        assert not outcome.needs_regeneration

    def test_wrong_project_content_fails(self):
        """Content with 3+ wrong-project signals should fail and need regeneration."""
        from src.reviewer import run_reviewer_pipeline

        content = (
            "# Firecrawl 深度拆解\n\n"
            "该项目将 RAG 流程模块化，支持 Milvus 和 Chroma 向量数据库。\n"
            "深度适配 ChatGLM 和 Baichuan 等国内开源模型。\n"
            "非 AI 工程师也能一键构建私有化知识库。\n"
        )

        ctx = {
            "confirmed_features": ["网页抓取 API"],
            "unsupported_features": ["知识库平台", "向量数据库"],
            "risk_boundaries": ["遵守 robots.txt"],
        }

        outcome = run_reviewer_pipeline(
            "01_ai_fde_deep_analysis", content, "firecrawl/firecrawl",
            ctx=ctx, project_type="web_scraping_api",
        )

        assert not outcome.passed
        assert outcome.needs_regeneration
        assert len(outcome.core_checks_failed) >= 1

    def test_light_mode_content_passes(self):
        """Short-form content in non-strict mode should pass easier."""
        from src.reviewer import run_reviewer_pipeline

        content = (
            "今天拆了个工具，网页抓取转 Markdown，给 AI 喂数据用的。"
            "后台跑着就行，不复杂。"
        )

        outcome = run_reviewer_pipeline(
            "03_douyin_video", content, "firecrawl/firecrawl",
            strict_mode=False,
        )

        # Short script without disclaimers should pass in non-strict mode
        assert outcome.passed


class TestPublicationReadinessGate:
    """Phase 11.6: Publication readiness gate — template placeholder detection."""

    def test_template_placeholder_detected(self):
        """_check_template_placeholders should detect [TODO: LLM] and No-LLM fallback."""
        from src.reviewer import _check_template_placeholders

        # Content with TODO markers
        content = "# Test\n\n[TODO: LLM — 200-300 字]\n\n## Section\n\n[TODO: LLM]"
        issues = _check_template_placeholders(content)
        assert len(issues) >= 1
        assert any("TODO" in i for i in issues)

    def test_clean_content_no_placeholders(self):
        """Clean LLM-generated content should have no placeholder issues."""
        from src.reviewer import _check_template_placeholders

        content = "# browser-use 深度拆解\n\n这是一个 AI Agent 的浏览器操作工具。\n\n## 核心能力\n\n..."
        issues = _check_template_placeholders(content)
        assert len(issues) == 0

    def test_quality_review_rejects_template_wechat(self):
        """quality_review must return revise_first/no when 05 has [TODO: LLM] placeholders."""
        import tempfile
        import os
        from pathlib import Path
        from src.reviewer import quality_review

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)

            # Write 05_wechat_article with template placeholders
            wechat_content = (
                "# 公众号长文草稿\n\n"
                "> 模式：No-LLM fallback — 需要 LLM 生成完整文章\n\n"
                "## 标题建议\n\n"
                "1. [TODO: LLM]\n"
                "2. [TODO: LLM]\n\n"
                "### 为什么这个项目值得看\n\n"
                "[TODO: LLM — 200-300 字]\n"
            )
            (pack_dir / "05_wechat_article.md").write_text(wechat_content, encoding="utf-8")

            # Write clean content for other required files
            for fname in [
                "01_ai_fde_deep_analysis.md", "02_xiaohongshu.md",
                "03_douyin_video.md", "04_videohao_script.md",
                "07_geo_angle.md", "09_risk_review.md",
            ]:
                clean = f"# {fname}\n\n这是一个关于 browser-use 的深度分析文章。\n\n## 风险边界\n\n使用前请遵守 robots.txt 和服务条款。本项目不保证排名、AI 引用或询盘。\n"
                (pack_dir / fname).write_text(clean, encoding="utf-8")

            report = quality_review(pack_dir, "browser-use/browser-use")

            # Must NOT be "yes" when a core file has template placeholders
            assert report.publish_recommendation != "yes", (
                f"Expected revise_first or no, got {report.publish_recommendation}"
            )
            assert report.publish_recommendation in ("revise_first", "no")
            # Must have at least 1 blocking issue
            assert len(report.blocking_issues) >= 1
            # 05 must be flagged
            assert any("05_wechat_article" in b for b in report.blocking_issues)

    def test_quality_review_yes_when_all_clean(self):
        """quality_review should return yes when ALL files are clean LLM content."""
        import tempfile
        from pathlib import Path
        from src.reviewer import quality_review

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)

            clean_content = (
                "# browser-use 深度拆解\n\n"
                "这是一个 AI Agent 浏览器操作工具。\n\n"
                "## 风险边界\n\n"
                "使用前请遵守 robots.txt 和服务条款。\n"
                "本项目不等于 GEO，不能保证 AI 搜索引用、排名或询盘增长。\n"
                "它可以作为 GEO 服务链路中的组件之一。\n"
            )

            for fname in [
                "01_ai_fde_deep_analysis.md", "02_xiaohongshu.md",
                "03_douyin_video.md", "04_videohao_script.md",
                "05_wechat_article.md", "07_geo_angle.md", "09_risk_review.md",
            ]:
                (pack_dir / fname).write_text(clean_content, encoding="utf-8")

            report = quality_review(pack_dir, "browser-use/browser-use")
            # With all clean files, should be yes (or revise_first if minor issues)
            assert report.publish_recommendation in ("yes", "revise_first")
            assert len(report.blocking_issues) == 0


class TestQualityReportNoStaleExamples:
    """Phase 11.7: Quality check report must not contain hardcoded project examples."""

    STALE_NAMES = [
        "RAGFlow", "LangChain-ChatChat", "Milvus", "Chroma", "Pinecone",
        "ChatGLM", "Baichuan", "Qdrant", "Weaviate",
    ]

    def test_write_quality_report_no_stale_examples(self):
        """write_quality_report output must not contain stale project names."""
        import tempfile
        from pathlib import Path
        from src.reviewer import (
            PackQualityReport, FileReview, CheckResult, write_quality_report,
        )

        report = PackQualityReport(
            repo_full_name="test-org/test-project",
            publish_recommendation="yes",
            overall_score=95,
            blocking_issues=[],
            recommended_platform="公众号",
            file_reviews={
                "01_ai_fde_deep_analysis.md": FileReview(
                    file_name="01_ai_fde_deep_analysis.md",
                    overall_score=95,
                    checks=[CheckResult(
                        check_name="repo_consistency", passed=True, score=95,
                        issues=[], detail="检测到 0 个错位信号（阈值=3）",
                    )],
                ),
            },
            deleted_sentences={},
            unsupported_features=["知识库/RAG平台（与当前项目定位不符）", "LLM推理/模型部署"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            out_path = write_quality_report(pack_dir, report)
            content = out_path.read_text(encoding="utf-8")

            for name in self.STALE_NAMES:
                assert name not in content, (
                    f"Stale project name '{name}' found in quality report:\n{content}"
                )

    def test_quality_report_uses_project_specific_signals(self):
        """Quality report should contain project-specific unsupported_features not stale names."""
        import tempfile
        from pathlib import Path
        from src.reviewer import (
            PackQualityReport, FileReview, CheckResult, write_quality_report,
        )

        report = PackQualityReport(
            repo_full_name="mcp-org/awesome-list",
            publish_recommendation="yes",
            overall_score=90,
            blocking_issues=[],
            file_reviews={},
            deleted_sentences={},
            unsupported_features=[
                "网页抓取/爬虫工具（与当前MCP索引项目定位不符）",
                "浏览器自动化引擎",
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            out_path = write_quality_report(pack_dir, report)
            content = out_path.read_text(encoding="utf-8")

            # Must NOT contain stale project names
            for name in self.STALE_NAMES:
                assert name not in content, (
                    f"Stale project name '{name}' found in quality report"
                )

            # Must contain the project-specific signals
            assert "MCP" in content or "mcp" in content.lower()

    def test_empty_unsupported_features_no_stale_fallback(self):
        """When unsupported_features is empty, must not fall back to stale names."""
        import tempfile
        from pathlib import Path
        from src.reviewer import (
            PackQualityReport, write_quality_report,
        )

        report = PackQualityReport(
            repo_full_name="some-org/some-repo",
            publish_recommendation="yes",
            overall_score=90,
            blocking_issues=[],
            file_reviews={},
            deleted_sentences={},
            unsupported_features=[],  # Empty!
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            out_path = write_quality_report(pack_dir, report)
            content = out_path.read_text(encoding="utf-8")

            for name in self.STALE_NAMES:
                assert name not in content, (
                    f"Stale project name '{name}' leaked into report with empty unsupported_features"
                )


# ═════════════════════════════════════════════════════════════════════════════
# Phase 12: Cross-project boundary tests — project-type-driven checks
# ═════════════════════════════════════════════════════════════════════════════

class TestCrossProjectBoundary:
    """Verify each project type gets correct boundary rules, not hardcoded GEO."""

    # ── Positive: each project type should NOT be mis-classified ──

    def test_firecrawl_is_web_scraping_api_not_rag(self):
        """Firecrawl → web_scraping_api, not rag_engine."""
        from src.reviewer import classify_project_type, get_project_boundary

        pt = classify_project_type("mendableai/firecrawl", topics=["scraping", "crawl", "api"])
        assert pt == "web_scraping_api", f"Expected web_scraping_api, got {pt}"

        boundary = get_project_boundary(pt)
        assert "万能爬虫" in boundary.blocking_phrases
        assert any("抓取" in c or "爬取" in c for c in boundary.allowed_claims)

    def test_browser_use_is_browser_automation_not_geo_tool(self):
        """browser-use → browser_automation, not GEO tool."""
        from src.reviewer import classify_project_type, get_project_boundary

        pt = classify_project_type(
            "browser-use/browser-use",
            topics=["browser-automation", "ai-agent", "playwright"],
            description="AI agent for browser automation",
        )
        assert pt == "browser_automation", f"Expected browser_automation, got {pt}"

        boundary = get_project_boundary(pt)
        # Must NOT claim to be a GEO tool
        assert "GEO 工具" in boundary.forbidden_claims
        # Must have "不绕过安全措施" boundary signal
        assert boundary.required_boundary_signals

    def test_ragflow_is_rag_engine_not_scraping_api(self):
        """RAGFlow → rag_engine, not web_scraping_api."""
        from src.reviewer import classify_project_type, get_project_boundary

        pt = classify_project_type(
            "infiniflow/ragflow",
            topics=["rag", "knowledge-base", "document-qa", "retrieval"],
            description="RAG engine for enterprise document Q&A",
        )
        assert pt == "rag_engine", f"Expected rag_engine, got {pt}"

        boundary = get_project_boundary(pt)
        assert "爬虫 API" in boundary.blocking_phrases
        assert "实时搜索替代" in boundary.blocking_phrases

    def test_awesome_mcp_is_resource_list_not_runnable_product(self):
        """awesome-mcp-servers → resource_list, not runnable platform."""
        from src.reviewer import classify_project_type, get_project_boundary

        pt = classify_project_type(
            "punkpeye/awesome-mcp-servers",
            topics=["awesome-list", "mcp", "curated"],
            description="A curated list of MCP servers",
        )
        assert pt == "resource_list", f"Expected resource_list, got {pt}"

        boundary = get_project_boundary(pt)
        assert "可直接运行的产品" in boundary.forbidden_claims
        assert any("资源" in c or "清单" in c or "列表" in c for c in boundary.allowed_claims)

    # ── Negative: high-risk must be blocked ──

    def test_deepfake_classified_as_high_risk(self):
        """Deep-Live-Cam → high_risk."""
        from src.reviewer import classify_project_type

        pt = classify_project_type(
            "hacksider/Deep-Live-Cam",
            topics=["deepfake", "face-swap", "ai"],
            description="Real-time face swapping and deepfake tool",
        )
        assert pt == "high_risk", f"Expected high_risk, got {pt}"

    def test_phishing_tool_classified_as_high_risk(self):
        """Phishing/scraping-abuse → high_risk."""
        from src.reviewer import classify_project_type

        pt = classify_project_type(
            "evil/scraper-tool",
            topics=["phishing", "credential-harvesting"],
            description="Advanced credential harvesting toolkit",
        )
        assert pt == "high_risk", f"Expected high_risk, got {pt}"

    # ── Negative: forbidden claims must be detected ──

    def test_ai_ranking_guarantee_blocked_in_any_project(self):
        """'保证 AI 排名' must be blocked regardless of project type."""
        from src.reviewer import risk_boundary_check

        content = "这个工具能保证 AI 引用和排名，让所有网站都收录你的内容。"

        for pt in ["web_scraping_api", "browser_automation", "rag_engine", "generic"]:
            result = risk_boundary_check(content, project_type=pt)
            assert not result.passed, f"pt={pt}: '保证 AI 引用/排名' should be blocked"
            assert any("保证" in i for i in result.issues), (
                f"pt={pt}: should have '保证' in issues, got {result.issues}"
            )

    def test_bypass_login_blocked_in_scraping_and_browser(self):
        """'绕过登录' must be blocked in web_scraping_api and browser_automation."""
        from src.reviewer import risk_boundary_check

        content = "使用这个工具可以绕过登录和验证码，自动登入任何网站后台。"

        # web_scraping_api: must block
        r1 = risk_boundary_check(content, project_type="web_scraping_api")
        assert not r1.passed

        # browser_automation: must block
        r2 = risk_boundary_check(content, project_type="browser_automation")
        assert not r2.passed

        # rag_engine: should also block (in blocking_phrases)
        r3 = risk_boundary_check(content, project_type="rag_engine")
        assert not r3.passed

    def test_resource_list_written_as_platform_needs_review(self):
        """resource_list content claiming to be a runnable platform should be flagged."""
        from src.reviewer import risk_boundary_check

        content = (
            "Awesome MCP 是一个可直接运行的生产级平台，"
            "一键部署即可接入数百个API和SDK。"
        )
        result = risk_boundary_check(content, project_type="resource_list")
        assert not result.passed
        issues_text = " ".join(result.issues)
        assert "可直接运行" in issues_text or "平台" in issues_text or "资源" in issues_text

    def test_generic_project_blocks_universal_forbidden_phrases(self):
        """Even generic project type should block '保证 AI 引用' and '绕过登录'."""
        from src.reviewer import risk_boundary_check

        content = "这个工具可以绕过登录验证，保证AI引用排名。"
        result = risk_boundary_check(content, project_type="generic")
        assert not result.passed
        assert len(result.issues) >= 1
