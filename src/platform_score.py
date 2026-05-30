"""Platform fit scoring — separate scores for each content platform.

Evaluates how well a repo fits 小红书, 抖音, 视频号, 公众号, and 外贸/GEO.
Each platform scores 0-100 with detailed subscores and reasoning.

Phase 10: Adds per-platform detailed reasoning, not reused text.
"""
import re
from dataclasses import dataclass, field


@dataclass
class PlatformFitScore:
    """Full platform fit analysis for one repo."""
    full_name: str

    # Individual platform scores (0-100)
    xiaohongshu: float = 0.0
    douyin: float = 0.0
    videohao: float = 0.0
    wechat: float = 0.0
    geo_trade: float = 0.0

    # Subscores
    xhs_visual: float = 0.0
    xhs_bookmark: float = 0.0
    xhs_beginner: float = 0.0

    dy_hook: float = 0.0
    dy_visual: float = 0.0
    dy_60s: float = 0.0

    vh_business: float = 0.0
    vh_stable: float = 0.0
    vh_value: float = 0.0

    wx_depth: float = 0.0
    wx_methodology: float = 0.0
    wx_fde: float = 0.0

    geo_applicable: float = 0.0
    geo_search: float = 0.0
    geo_service: float = 0.0

    # Verdicts
    geo_verdict: str = "不能硬蹭"
    best_platform: str = ""
    best_platform_score: float = 0.0

    # Phase 10: Per-platform reasoning
    reasons: dict = field(default_factory=dict)


def _build_text(repo) -> str:
    return f"{repo.name or ''} {repo.description or ''} {' '.join(repo.topics or [])}".lower()


def score_platform_fit(repo) -> PlatformFitScore:
    """Score a repo's fit for each content platform.

    Args:
        repo: ScoredRepo with name, description, topics, readme, stars, etc.
    """
    text = _build_text(repo)
    readme = (getattr(repo, 'readme', '') or '').lower()
    all_text = f"{text} {readme}"
    stars = getattr(repo, 'stars', 0)
    description = getattr(repo, 'description', '') or ''
    topics = getattr(repo, 'topics', []) or []
    topics_lower = {t.lower() for t in topics}

    pf = PlatformFitScore(full_name=getattr(repo, 'full_name', ''))

    # ═══════════════════════════════════════════════════════════════════
    # 小红书 (Xiaohongshu) — 图文卡片 / 收藏价值 / 小白理解
    # ═══════════════════════════════════════════════════════════════════
    xhs_visual = 5.0  # baseline
    if any(k in all_text for k in ("demo", "screenshot", "gif", "playground", "video")):
        xhs_visual += 2.0
    if any(k in all_text for k in ("ui", "interface", "dashboard", "visual", "图表")):
        xhs_visual += 1.5
    if len(topics) >= 4:
        xhs_visual += 1.5
    pf.xhs_visual = min(10.0, xhs_visual)

    xhs_bookmark = 5.0
    if any(k in all_text for k in ("tutorial", "guide", "how-to", "教程", "入门", "上手")):
        xhs_bookmark += 2.0
    if any(k in text for k in ("tool", "framework", "library", "工具", "框架")):
        xhs_bookmark += 1.5
    if stars >= 1000:
        xhs_bookmark += 1.5
    pf.xhs_bookmark = min(10.0, xhs_bookmark)

    xhs_beginner = 5.0
    if re.search(r"[一-鿿]", readme):
        xhs_beginner += 2.0
    if 20 < len(description) < 120:
        xhs_beginner += 1.5
    simple_concepts = {"chatbot", "search", "automation", "workflow", "browser",
                       "document", "知识库", "问答", "客服", "销售"}
    if any(c in text for c in simple_concepts):
        xhs_beginner += 1.5
    pf.xhs_beginner = min(10.0, xhs_beginner)

    pf.xiaohongshu = round((pf.xhs_visual * 3.5 + pf.xhs_bookmark * 3.5 + pf.xhs_beginner * 3.0))  # out of 100

    # ═══════════════════════════════════════════════════════════════════
    # 抖音 (Douyin) — 3秒钩子 / 视觉演示 / 60秒短视频
    # ═══════════════════════════════════════════════════════════════════
    dy_hook = 5.0
    hook_signals = {"agent", "browser-use", "automation", "deepfake", "face swap",
                    "search", "scrape", "视频生成", "图片生成", "ai画画"}
    if any(k in text for k in hook_signals):
        dy_hook += 2.0
    if stars > 50000:
        dy_hook += 1.0  # name recognition
    if len(description) > 30:
        dy_hook += 1.0
    if any(k in text for k in ("real-time", "live", "秒", "一键", "自动")):
        dy_hook += 1.0
    pf.dy_hook = min(10.0, dy_hook)

    dy_visual = 5.0
    if any(k in all_text for k in ("demo", "gif", "video", "screen", "screenshot", "animation")):
        dy_visual += 2.5
    if any(k in all_text for k in ("image", "visual", "graphic", "图表", "图片")):
        dy_visual += 1.5
    if "demo" in text or "playground" in text:
        dy_visual += 1.0
    pf.dy_visual = min(10.0, dy_visual)

    dy_60s = 5.0
    if any(k in text for k in ("browser-use", "search", "chatbot", "automation", "tool", "scrape")):
        dy_60s += 2.5
    if 20 < len(description) < 100:  # Short enough to explain quickly
        dy_60s += 1.5
    if any(k in topics_lower for k in ("agent", "ai", "llm", "rag", "mcp")):
        dy_60s += 1.0
    pf.dy_60s = min(10.0, dy_60s)

    pf.douyin = round((pf.dy_hook * 4.0 + pf.dy_visual * 3.5 + pf.dy_60s * 2.5))  # out of 100

    # ═══════════════════════════════════════════════════════════════════
    # 视频号 (VideoHao) — 企业老板/业务负责人 / 稳重 / 业务价值
    # ═══════════════════════════════════════════════════════════════════
    vh_business = 5.5
    biz_signals = {"enterprise", "business", "企业", "自动化", "效率", "降本",
                   "workflow", "automation", "api", "integration", "saas",
                   "knowledge", "document", "search", "analytics"}
    biz_hits = sum(1 for s in biz_signals if s in text)
    vh_business += min(3.5, biz_hits * 0.7)
    if stars >= 5000:
        vh_business += 1.5
    pf.vh_business = min(10.0, vh_business)

    vh_stable = 6.0  # Higher baseline for 视频号
    if getattr(repo, 'license', ''):
        vh_stable += 1.0
    contributors = getattr(repo, 'contributors_count', 0)
    if contributors >= 5:
        vh_stable += 1.5
    elif contributors >= 2:
        vh_stable += 0.5
    if not any(r in text for r in ("deprecated", "unmaintained", "alpha", "beta", "实验")):
        vh_stable += 1.5
    pf.vh_stable = min(10.0, vh_stable)

    vh_value = 5.0
    value_signals = {"roi", "efficiency", "cost", "revenue", "productivity",
                     "效率", "成本", "收入", "效果", "结果"}
    if any(s in text for s in value_signals):
        vh_value += 2.0
    if any(k in text for k in ("enterprise", "business", "api", "integration")):
        vh_value += 1.5
    if any(k in topics_lower for k in ("automation", "workflow", "mcp")):
        vh_value += 1.5
    pf.vh_value = min(10.0, vh_value)

    pf.videohao = round((pf.vh_business * 4.0 + pf.vh_stable * 3.0 + pf.vh_value * 3.0))

    # ═══════════════════════════════════════════════════════════════════
    # 公众号 (WeChat) — 深度长文 / 方法论沉淀 / AI-FDE视角
    # ═══════════════════════════════════════════════════════════════════
    wx_depth = 5.0
    if len(readme) > 1000:
        wx_depth += 2.5
    if re.search(r"^#{1,3}\s", readme, re.MULTILINE):
        wx_depth += 1.5
    deep_topics = {"rag", "agent", "mcp", "langchain", "vector-database",
                   "prompt-engineering", "function-calling", "llamaindex"}
    if any(t in topics_lower for t in deep_topics):
        wx_depth += 1.0
    pf.wx_depth = min(10.0, wx_depth)

    wx_method = 5.0
    if any(k in all_text for k in ("architecture", "design", "pattern", "架构", "设计", "原理")):
        wx_method += 2.0
    if re.search(r"[一-鿿]", readme):
        wx_method += 2.0
    if len(all_text) > 3000:
        wx_method += 1.0
    pf.wx_methodology = min(10.0, wx_method)

    wx_fde = 5.0
    fde_signals = {"agent", "rag", "mcp", "browser-use", "geo", "ai-search",
                   "prompt-engineering", "workflow", "automation"}
    if any(k in text for k in fde_signals):
        wx_fde += 3.0
    if any(k in text for k in ("open-source", "开源")):
        wx_fde += 1.0
    if stars >= 1000:
        wx_fde += 1.0
    pf.wx_fde = min(10.0, wx_fde)

    pf.wechat = round((pf.wx_depth * 4.0 + pf.wx_methodology * 3.0 + pf.wx_fde * 3.0))

    # ═══════════════════════════════════════════════════════════════════
    # 外贸/GEO — 外贸客户分析 / AI搜索可见性 / 服务切入点
    # ═══════════════════════════════════════════════════════════════════
    has_geo = any(k in text for k in ("geo", "seo", "ai-search", "search engine",
                                        "web scrap", "crawl", "scrap"))
    has_auto = any(k in text for k in ("automation", "workflow", "n8n", "dify", "browser-use"))
    has_trade = any(k in text for k in ("外贸", "跨境电商", "cross-border", "ecommerce", "贸易"))
    has_biz = any(k in text for k in ("enterprise", "business", "api", "integration",
                                        "knowledge-base", "search", "crawl", "scrap",
                                        "rag", "agent", "mcp"))

    if has_geo or has_trade:
        pf.geo_applicable = 8.0
        pf.geo_search = 8.0
        pf.geo_service = 7.0
        pf.geo_verdict = "可以结合 — 项目与GEO/外贸直接相关"
    elif has_auto and "browser-use" in text:
        pf.geo_applicable = 8.5
        pf.geo_search = 7.5
        pf.geo_service = 8.0
        pf.geo_verdict = "可以结合 — 浏览器自动化可用于外贸客户分析、竞品监控、GEO检测"
    elif has_auto and has_biz:
        pf.geo_applicable = 6.5
        pf.geo_search = 6.0
        pf.geo_service = 6.5
        pf.geo_verdict = "可以结合 — 自动化+企业能力可转化为外贸工作流或数据分析方案"
    elif has_auto:
        pf.geo_applicable = 5.0
        pf.geo_search = 4.5
        pf.geo_service = 6.0
        pf.geo_verdict = "可以结合 — 自动化能力可转化为外贸工作流方案"
    elif has_biz:
        pf.geo_applicable = 6.0
        pf.geo_search = 5.5
        pf.geo_service = 5.5
        pf.geo_verdict = "可以结合 — 企业级工具可服务于外贸公司的技术栈需求"
    else:
        pf.geo_applicable = 2.0
        pf.geo_search = 1.0
        pf.geo_service = 2.0
        pf.geo_verdict = "不能硬蹭 — 该项目与外贸/GEO没有明显交集，强行结合会降低账号可信度"

    pf.geo_trade = round((pf.geo_applicable * 4.0 + pf.geo_search * 3.5 + pf.geo_service * 2.5))

    # ═══════════════════════════════════════════════════════════════════
    # Best platform
    # ═══════════════════════════════════════════════════════════════════
    platforms = {
        "小红书": pf.xiaohongshu,
        "抖音": pf.douyin,
        "视频号": pf.videohao,
        "公众号": pf.wechat,
        "外贸/GEO": pf.geo_trade,
    }
    pf.best_platform = max(platforms, key=platforms.get)
    pf.best_platform_score = platforms[pf.best_platform]

    # Phase 10: Per-platform detailed reasoning
    pf.reasons = _build_platform_reasons(pf, text, all_text, topics_lower, stars, description)

    return pf


def _build_platform_reasons(pf: PlatformFitScore, text: str, all_text: str,
                            topics_lower: set, stars: int, description: str) -> dict:
    """Generate per-platform reasoning — not reused text, each is unique."""
    reasons = {}

    # ── 小红书 ──
    xhs_parts = []
    if pf.xhs_visual >= 7:
        xhs_parts.append(f"适合图文卡片：有{'演示/截图' if any(k in all_text for k in ('demo','screenshot','gif')) else '可视化元素'}可做封面")
    else:
        xhs_parts.append("图文卡片适配一般：缺少可视化素材，需要自行设计概念图")
    if pf.xhs_bookmark >= 7:
        xhs_parts.append(f"收藏价值高：{'有教程/指南内容' if any(k in all_text for k in ('tutorial','guide','how-to')) else '工具实用性强'}")
    else:
        xhs_parts.append("收藏价值中等：实用性和教程性不够突出")
    if pf.xhs_beginner >= 7:
        xhs_parts.append("小白友好：概念直白，无需技术背景即可理解核心价值")
    else:
        xhs_parts.append("不适合小白：概念偏技术，需要一定基础才能看懂")
    # Unsuitable point
    if pf.xiaohongshu < 60:
        xhs_parts.append("不适合点：缺乏视觉冲击力和收藏冲动，不建议作为小红书主推")
    else:
        heavy_tech = any(k in text for k in ("distributed", "compiler", "kernel", "blockchain"))
        if heavy_tech:
            xhs_parts.append("不适合点：技术概念太硬核，小红书受众难以理解")
        else:
            xhs_parts.append("可发布，建议配上操作截图或效果对比图增强吸引力")
    reasons["xiaohongshu"] = "；".join(xhs_parts) if xhs_parts else "需进一步分析"

    # ── 抖音 ──
    dy_parts = []
    if pf.dy_hook >= 7:
        hook = _find_hook(text, all_text)
        dy_parts.append(f"前3秒钩子：{hook}")
    else:
        dy_parts.append("前3秒钩子较弱：缺乏天然的话题引爆点，需要脚本创意包装")
    if pf.dy_visual >= 7:
        dy_parts.append(f"有视觉演示可能：{'有demo/gif/截图' if any(k in all_text for k in ('demo','gif','screenshot')) else '操作过程可视性强'}")
    else:
        dy_parts.append("视觉演示难度大：偏代码/架构层面，需要大量动画辅助")
    if pf.dy_60s >= 7:
        dy_parts.append("60秒能讲清：核心概念简洁，可以用一个Demo讲明白")
    else:
        dy_parts.append("60秒难讲透：概念较深，可能需要系列视频而非单条")
    if pf.douyin < 55:
        dy_parts.append("风险点：缺乏视觉冲击和情绪钩子，抖音完播率可能偏低")
    else:
        dy_parts.append("风险点：需注意不要过度技术化，用故事和场景代入而非念代码")
    reasons["douyin"] = "；".join(dy_parts)

    # ── 视频号 ──
    vh_parts = []
    if pf.vh_business >= 7:
        vh_parts.append("适合老板/业务负责人：直接讲业务价值和降本增效的数字")
    else:
        vh_parts.append("对老板吸引力一般：偏技术工具而非业务成果展示")
    if pf.vh_value >= 7:
        vh_parts.append("能讲降本增效：有明确的效率提升或成本节省场景")
    else:
        vh_parts.append("降本增效故事不强：缺少可直接量化的业务成果")
    if pf.vh_stable >= 7:
        vh_parts.append("够稳重：非实验性项目，有社区基础，适合企业决策者参考")
    else:
        vh_parts.append("不够稳重：项目较新或实验性较强，视频号受众可能观望")
    if pf.videohao < 55:
        vh_parts.append("不适合点：商业叙事不足，视频号观众更关心'这对我有什么用'")
    else:
        vh_parts.append("可做，建议以'AI落地案例'角度切入，突出具体业务场景")
    reasons["videohao"] = "；".join(vh_parts)

    # ── 公众号 ──
    wx_parts = []
    if pf.wx_depth >= 7:
        wx_parts.append("适合长文：技术深度够，可以展开讲架构设计和实现细节")
    else:
        wx_parts.append("长文深度有限：项目本身偏工具使用而非方法论沉淀")
    if pf.wx_methodology >= 7:
        wx_parts.append("能沉淀方法论：可以从具体案例提炼出可复用的原则和框架")
    else:
        wx_parts.append("方法论沉淀空间小：更像操作手册而非思维模型")
    if pf.wx_fde >= 7:
        wx_parts.append("能讲AI-FDE视角：Fact-Demonstration-Explanation框架适用")
    else:
        wx_parts.append("AI-FDE视角适配度一般")
    if pf.wechat < 55:
        wx_parts.append("不建议公众号长文：更适合作为工具推荐短文或纳入合集")
    else:
        wx_parts.append("有案例拆解空间：可以从实际使用场景出发做深度案例分析")
    reasons["wechat"] = "；".join(wx_parts)

    # ── 外贸/GEO ──
    geo_parts = []
    geo_parts.append(pf.geo_verdict)
    if pf.geo_applicable >= 6:
        geo_parts.append("可用于外贸客户网站分析" if pf.geo_applicable >= 7 else "外贸方向可尝试但非核心优势")
    if pf.geo_search >= 6:
        geo_parts.append("可用于AI搜索可见性：帮助客户检查网站在AI搜索中的表现")
    else:
        geo_parts.append("AI搜索可见性关联较弱——项目不直接涉及搜索优化")
    if pf.geo_service >= 6:
        geo_parts.append("可变成服务切入点：作为出海客户的服务方案组件")
    else:
        geo_parts.append("服务切入点不明确——较难包装成独立的GEO服务产品")
    if pf.geo_trade < 50:
        geo_parts.append("明确结论：不能硬蹭——该项目与外贸/GEO没有明显交集，强行结合会降低账号可信度")
    reasons["geo"] = "；".join(geo_parts)

    return reasons


def _find_hook(text: str, all_text: str) -> str:
    """Find a compelling hook for douyin."""
    if "browser" in text and "automation" in text:
        return '"AI帮你操作浏览器，不用再手动填表了"'
    if "crawl" in text or "scrap" in text:
        return '"这个工具让AI能读懂任何网站"'
    if "deepfake" in text or "face swap" in text:
        return '"AI换脸技术到底有多真？"'
    if "agent" in text and "mcp" in text:
        return '"给AI装上一双手，让它自己去干活"'
    if "search" in text and "ai" in text:
        return '"未来的搜索不是百度这样，而是……"'
    if "rag" in text:
        return '"你的公司文档太多找不到？AI三秒帮你查"'
    if "workflow" in text:
        return '"不用写代码，拖拽就能让AI帮你干活"'
    if "eval" in text or "prompt" in text:
        return '"你的AI真的靠谱吗？这个工具帮你测"'
    return f'"一个AI工具，{60}秒讲清楚怎么用"'
