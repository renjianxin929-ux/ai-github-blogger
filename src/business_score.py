"""Business Value Score — evaluates repos for AI blog / consulting content fitness.

6 dimensions with v4 weights (total 100):
  普通人理解成本 15, 企业落地场景 25, AI-FDE训练价值 20,
  商业服务延展 20, 业务流程结合度 10, 风险可控性 10

Phase 10: Adds detailed business evidence to every scored repo.
"""
import re
from dataclasses import dataclass, field


@dataclass
class BusinessScore:
    """Business value evaluation for a repo's content potential."""
    full_name: str
    total: float = 0.0
    subscores: dict = field(default_factory=dict)
    summary: str = ""
    evidence: dict = field(default_factory=dict)


def score_business_value(repo) -> BusinessScore:
    """Score a repo across 6 business-value dimensions.

    Returns:
        BusinessScore with 0-100 total, per-dimension subscores, and evidence dict.
    """
    subscores = {
        "understandability": _score_understandability(repo),
        "enterprise_fit": _score_enterprise_fit(repo),
        "fde_training": _score_fde_training(repo),
        "service_extensibility": _score_service_extensibility(repo),
        "workflow_integration": _score_workflow_integration(repo),
        "risk_controllability": _score_risk_controllability(repo),
    }

    weights = {
        "understandability": 0.15,
        "enterprise_fit": 0.25,
        "fde_training": 0.20,
        "service_extensibility": 0.20,
        "workflow_integration": 0.10,
        "risk_controllability": 0.10,
    }

    total = sum(subscores[k] * weights[k] * 10 for k in subscores)
    total = round(min(100.0, max(0.0, total)), 1)

    return BusinessScore(
        full_name=repo.full_name,
        total=total,
        subscores=subscores,
        summary=_build_summary(repo, subscores, total),
        evidence=_build_business_evidence(repo, subscores, total),
    )


def _build_text(repo) -> str:
    return f"{repo.name or ''} {repo.description or ''} {' '.join(repo.topics or [])}".lower()


# ── Dimension 1: 普通人理解成本 (15 pts) ──────────────────────────────────

def _score_understandability(repo) -> float:
    score = 6.0
    readme = (repo.readme or "").lower()
    text = _build_text(repo)

    if re.search(r"[一-鿿]", repo.readme or ""):
        score += 1.5
    desc = repo.description or ""
    if 20 < len(desc) < 150:
        score += 1.0
    if any(k in readme for k in ("demo", "playground", "try it", "screenshot", "gif")):
        score += 1.0
    simple = {"chatbot", "search", "automation", "workflow", "browser",
              "document", "知识库", "问答", "客服", "销售", "agent",
              "tool", "api", "cli", "web", "app", "server"}
    simple_hits = sum(1 for c in simple if c in text)
    score += min(1.5, simple_hits * 0.25)
    if repo.stars >= 50000:
        score += 1.0
    complex_kw = {"distributed", "sharding", "raft", "consensus", "blockchain",
                  "cryptography", "zero-knowledge", "compiler", "kernel"}
    if any(c in text for c in complex_kw):
        score -= 1.0
    return max(0.0, min(10.0, score))


# ── Dimension 2: 企业落地场景 (25 pts) ────────────────────────────────────

def _score_enterprise_fit(repo) -> float:
    score = 4.5
    text = _build_text(repo)
    readme = (repo.readme or "").lower()

    enterprise_signals = {
        "客服": ("customer-service", "support", "helpdesk", "客服", "ticket"),
        "销售": ("sales", "crm", "lead", "pipeline", "销售", "prospecting"),
        "知识库": ("knowledge-base", "rag", "retrieval", "知识库", "document"),
        "自动化": ("automation", "workflow", "自动化", "orchestration", "n8n", "browser"),
        "外贸": ("geo", "seo", "外贸", "cross-border", "ecommerce", "跨境电商"),
        "内容生产": ("content", "generation", "writing", "copywriting", "内容", "文案"),
        "运营提效": ("operation", "analytics", "dashboard", "运营", "reporting"),
        "开发者工具": ("api", "sdk", "cli", "plugin", "integration", "webhook"),
        "商业智能": ("business", "monitoring", "competitor", "intelligence", "insight"),
    }

    hits = 0
    for _category, keywords in enterprise_signals.items():
        if any(k in text or k in readme for k in keywords):
            hits += 1

    score += min(5, hits * 0.8)
    if any(k in text for k in ("api", "webhook", "slack", "notion", "airtable", "zapier")):
        score += 1.0
    if repo.stars >= 100000:
        score += 2.0
    elif repo.stars >= 50000:
        score += 1.5
    elif repo.stars >= 5000:
        score += 1.0
    if repo.contributors_count >= 10:
        score += 0.5
    return max(0.0, min(10.0, score))


# ── Dimension 3: AI-FDE 训练价值 (20 pts) ─────────────────────────────────

def _score_fde_training(repo) -> float:
    score = 5.5
    text = _build_text(repo)
    novel = {"agent", "rag", "mcp", "browser-use", "geo", "ai-search",
             "multimodal", "function-calling", "prompt-engineering",
             "tool-use", "tool-calling", "orchestration", "memory"}
    novel_hits = sum(1 for t in novel if t in text)
    score += min(3.5, novel_hits * 0.7)
    problem_signals = ("solve", "problem", "challenge", "解决", "痛点", "automate", "simplify")
    if any(s in text for s in problem_signals):
        score += 1.0
    if repo.stars >= 10000:
        score += 1.0
    elif repo.stars >= 1000:
        score += 0.5
    if repo.license:
        score += 0.5
    readme = (repo.readme or "").lower()
    if len(readme) > 1000:
        score += 1.0
    return max(0.0, min(10.0, score))


# ── Dimension 4: 商业服务延展 (20 pts) ────────────────────────────────────

def _score_service_extensibility(repo) -> float:
    score = 4.5
    text = _build_text(repo)
    readme = (repo.readme or "").lower()
    all_text = f"{text} {readme}"
    extension_signals = {
        "api": 1.2, "plugin": 1.0, "template": 1.0,
        "custom": 0.8, "self-hosted": 1.2, "cloud": 0.8,
        "enterprise": 1.0, "open-source": 1.0, "sdk": 1.0,
        "client": 0.8, "library": 0.8, "toolkit": 0.8,
        "tool": 0.5, "agent": 0.8, "server": 0.5,
    }
    for signal, bonus in extension_signals.items():
        if signal in all_text:
            score += bonus
    deploy_options = ("docker", "pip", "npm", "homebrew", "helm", "npx")
    deploy_hits = sum(1 for d in deploy_options if d in all_text)
    score += min(2.0, deploy_hits * 0.5)
    if repo.stars >= 100000:
        score += 2.0
    elif repo.stars >= 50000:
        score += 1.5
    elif repo.stars >= 10000:
        score += 1.0
    return max(0.0, min(10.0, score))


# ── Dimension 5: 业务流程结合度 (10 pts) ──────────────────────────────────

def _score_workflow_integration(repo) -> float:
    score = 4.5
    text = _build_text(repo)
    readme = (repo.readme or "").lower()
    all_text = f"{text} {readme}"
    workflow_signals = ("workflow", "automation", "n8n", "dify", "zapier",
                        "integration", "webhook", "api", "orchestration",
                        "pipeline", "trigger", "schedule", "agent",
                        "connect", "tool", "rag", "knowledge-base",
                        "search", "crawl")
    hits = sum(1 for s in workflow_signals if s in all_text)
    score += min(5.0, hits * 0.7)
    if any(k in all_text for k in ("low-code", "no-code", "visual", "drag-and-drop")):
        score += 2.0
    if repo.stars >= 10000:
        score += 0.5
    return max(0.0, min(10.0, score))


# ── Dimension 6: 风险可控性 (10 pts) ──────────────────────────────────────

def _score_risk_controllability(repo) -> float:
    from .risk_score import assess_risk
    profile = assess_risk(repo)
    mapping = {"low": 9.0, "medium": 7.0, "high": 4.5, "blocked": 0.0}
    return mapping.get(profile.overall, 5.0)


# ── Summary builder ────────────────────────────────────────────────────────

def _build_summary(repo, subscores: dict, total: float) -> str:
    understand = subscores.get("understandability", 5)
    enterprise = subscores.get("enterprise_fit", 5)
    risk = subscores.get("risk_controllability", 5)

    parts = []
    if understand >= 7:
        parts.append("普通人容易理解")
    elif understand >= 4:
        parts.append("需要一定技术背景才能理解")
    else:
        parts.append("概念较为复杂，需要额外解释")

    if enterprise >= 7:
        parts.append("企业落地场景丰富")
    elif enterprise >= 4:
        parts.append("有一定企业场景，但需定制化")
    else:
        parts.append("企业直接落地较难")

    if risk >= 7:
        parts.append("风险可控")
    elif risk >= 4:
        parts.append("有轻度风险需注意")
    else:
        parts.append("风险较高，需要谨慎推荐")

    if total >= 75:
        parts.append("非常适合作为今日主选题")
    elif total >= 55:
        parts.append("可以作为辅助选题")
    else:
        parts.append("建议作为备选或专题深度拆解")

    return "；".join(parts)


def _build_business_evidence(repo, subscores: dict, total: float) -> dict:
    """Build detailed 7-point business evidence for a high-confidence repo.

    Returns dict with: one_liner, boss_care, scenarios, fde_value,
                       service_paths, no_hard_rub, deduction_reasons
    """
    text = _build_text(repo)
    readme = (repo.readme or "").lower()
    all_text = f"{text} {readme}"
    name = repo.name or ""
    desc = repo.description or ""
    topics = [t.lower() for t in (repo.topics or [])]
    topics_str = " ".join(topics)

    # ── 1. One-liner for average person ──
    one_liner = _make_one_liner(name, desc, text, topics_str)

    # ── 2. Why a business owner cares ──
    boss_care = _make_boss_care(name, desc, text, all_text, topics_str)

    # ── 3. Concrete business scenarios (≥3) ──
    scenarios = _make_scenarios(text, all_text, topics_str)

    # ── 4. AI-FDE training value ──
    fde_value = _make_fde_value(text, topics_str, subscores.get("fde_training", 5))

    # ── 5. Service extension paths ──
    service_paths = _make_service_paths(text, all_text, topics_str)

    # ── 6. Where NOT to force it ──
    no_hard_rub = _make_no_hard_rub(name, desc, text, topics_str)

    # ── 7. Deduction reasons ──
    deduction_reasons = _make_deduction_reasons(subscores, total)

    return {
        "one_liner": one_liner,
        "boss_care": boss_care,
        "scenarios": scenarios,
        "fde_value": fde_value,
        "service_paths": service_paths,
        "no_hard_rub": no_hard_rub,
        "deduction_reasons": deduction_reasons,
    }


def _make_one_liner(name: str, desc: str, text: str, topics_str: str) -> str:
    """Craft a one-sentence explanation for an average person."""
    if "browser" in text and "automation" in text:
        return f"{name} 是一个让AI像人一样操作浏览器的工具——你可以让它自动填表单、抓网页、做重复性工作"
    if "crawl" in text or "scrap" in text or "firecrawl" in text:
        return f"{name} 是一个把网页变成AI能读懂的结构化数据的工具——你想让AI分析任何网站内容，它都能自动抓取整理"
    if "rag" in text and ("knowledge" in text or "retrieval" in text or "document" in text):
        return f"{name} 是一个帮企业把内部文档变成AI可问答的知识库——员工可以直接用自然语言查资料"
    if "agent" in text and ("mcp" in text or "tool" in text):
        return f"{name} 是一个让AI Agent连接各种工具和服务的中间件——相当于给AI装上万能接口"
    if "workflow" in text or "n8n" in text or "dify" in text:
        return f"{name} 是一个可视化AI工作流编排工具——不用写代码就能把AI能力串成自动化流程"
    if "search" in text and ("ai" in text or "vector" in text):
        return f"{name} 是一个AI时代的搜索引擎——不只是关键词匹配，而是真正理解你想找什么"
    if "eval" in text or "prompt" in text:
        return f"{name} 是一个AI应用质量评估工具——帮你在上线前确保AI不会胡说八道"
    if "langchain" in text or "llamaindex" in text:
        return f"{name} 是一个AI开发框架——让开发者用积木式的方式搭建AI应用"
    if "chat" in text or "bot" in text:
        return f"{name} 是一个可定制的AI对话机器人——你可以训练它成为客服、销售或内部助手"
    # fallback
    if desc:
        return f"{name} — {desc[:80]}"
    return f"{name} — 一个值得了解的AI工具"


def _make_boss_care(name: str, desc: str, text: str, all_text: str, topics_str: str) -> str:
    """Explain why a business owner would care."""
    reasons = []
    if any(k in text for k in ("automation", "workflow", "orchestration")):
        reasons.append("减少重复性人工操作，降低运营成本")
    if any(k in all_text for k in ("api", "integration", "webhook", "connect")):
        reasons.append("可集成到现有业务系统，不需要推翻重来")
    if any(k in text for k in ("search", "knowledge", "rag", "document", "retrieval")):
        reasons.append("让员工更快找到信息，减少重复问答和培训成本")
    if any(k in text for k in ("agent", "tool", "mcp")):
        reasons.append("扩展现有AI能力边界，用Agent自动处理原来人工才能做的事")
    if any(k in text for k in ("self-hosted", "open-source", "privacy", "私有化")):
        reasons.append("数据不出企业内网，满足合规和安全要求")
    if any(k in text for k in ("scrap", "crawl", "monitor", "competitor")):
        reasons.append("自动监控市场和竞品动态，决策速度领先对手")
    if any(k in text for k in ("eval", "test", "quality", "prompt")):
        reasons.append("确保AI输出质量稳定，避免因AI失误造成业务损失")
    if not reasons:
        if desc:
            reasons.append(f"通过AI技术提升效率——{desc[:60]}")
        else:
            reasons.append("AI技术落地可降低运营成本或提升服务效率")
    return "；".join(reasons[:3])


def _make_scenarios(text: str, all_text: str, topics_str: str) -> list:
    """Generate ≥3 concrete business scenarios."""
    scenarios = []
    if any(k in text for k in ("browser", "automation", "crawl", "scrap")):
        scenarios.append("外贸客户网站分析：自动抓取目标客户网站内容，分析其业务模式")
        scenarios.append("GEO/SEO内容检查：扫描自己的网站，检查在AI搜索中的可见性")
        scenarios.append("竞品价格监控：定时抓取竞品网站，第一时间发现价格/产品变化")
    if any(k in text for k in ("rag", "knowledge", "document", "retrieval")):
        scenarios.append("企业知识库问答：把产品手册/规章制度导入后，员工用自然语言查询")
        scenarios.append("客服自动回复：基于知识库自动回答客户常见问题，降低人工客服成本")
        scenarios.append("销售资料库：销售随时查询产品信息、案例、报价，提升响应速度")
    if any(k in text for k in ("agent", "tool", "mcp")):
        scenarios.append("企业系统集成：连接CRM/ERP/邮件，让Agent自动处理跨系统工作流")
        scenarios.append("数据分析Agent：自动从多个数据源取数、分析、出报告")
        scenarios.append("智能客服升级：Agent不只回答问题，还能查订单、退款、改地址")
    if any(k in text for k in ("eval", "prompt", "test", "quality")):
        scenarios.append("AI应用上线前质量把关：自动评估AI回复的准确性、安全性")
        scenarios.append("Prompt迭代管理：系统化管理不同版本的Prompt，对比效果")
        scenarios.append("合规审核：确保AI输出符合行业法规（金融/医疗/法律）")
    if any(k in text for k in ("workflow", "n8n", "dify", "orchestration")):
        scenarios.append("业务流程自动化：把市场线索→CRM录入→分配销售→发送邮件全流程自动化")
        scenarios.append("内容发布工作流：AI写稿→人工审核→自动发布到多平台")
        scenarios.append("数据ETL管道：定时从API取数据→清洗→入库→生成报表")
    if any(k in text for k in ("chat", "bot", "assistant")):
        scenarios.append("内部培训助手：新员工可以随时向AI提问学习公司产品和流程")
        scenarios.append("客户自助服务：网站/小程序接入AI客服，7×24自动应答")
        scenarios.append("销售陪练：模拟客户对话，帮助销售练习话术")
    # fallback scenarios
    if not scenarios:
        scenarios.append("内容创作辅助：AI生成初稿，人工润色后发布")
        scenarios.append("数据整理和摘要：自动从大量文本中提取关键信息")
        scenarios.append("效率工具：减少重复性脑力劳动，让团队聚焦高价值工作")
    return scenarios[:5]


def _make_fde_value(text: str, topics_str: str, fde_score: float) -> str:
    """Describe AI-FDE training value."""
    parts = []
    if any(k in text for k in ("agent", "tool-use", "function-calling")):
        parts.append("可学习Agent工具调用的实现模式和最佳实践")
    if any(k in text for k in ("rag", "retrieval", "knowledge")):
        parts.append("可深入理解RAG系统的检索-增强-生成全链路")
    if any(k in text for k in ("browser", "automation")):
        parts.append("可掌握浏览器自动化的核心技术：DOM解析、操作模拟、状态管理")
    if any(k in text for k in ("crawl", "scrap")):
        parts.append("可学习大规模网页抓取和结构化转换的工程方案")
    if any(k in text for k in ("eval", "prompt", "quality")):
        parts.append("可理解AI系统质量评估的方法论和指标体系")
    if any(k in text for k in ("mcp", "tool", "plugin")):
        parts.append(f"可了解MCP协议和Agent工具生态的扩展机制")
    if not parts:
        parts.append("可作为AI应用层案例研究，分析其架构设计和工程取舍")
    if fde_score >= 8:
        parts.append("高训练价值：技术栈典型、代码可读、社区活跃")
    return "；".join(parts)


def _make_service_paths(text: str, all_text: str, topics_str: str) -> str:
    """Describe service extension paths."""
    paths = []
    if any(k in text for k in ("browser", "automation")):
        paths.append("为企业提供浏览器自动化定制方案：竞品监控、表单自动填写、数据采集")
    if any(k in text for k in ("rag", "knowledge", "document")):
        paths.append("为企业搭建私有知识库系统：文档导入→向量化→问答→持续更新")
    if any(k in text for k in ("agent", "mcp")):
        paths.append("为企业做Agent集成咨询：连接内部系统、定制工具链、部署运维")
    if any(k in text for k in ("crawl", "scrap")):
        paths.append("提供网页数据服务：定制化采集、结构化输出、定时更新")
    if any(k in all_text for k in ("api", "self-hosted", "docker")):
        paths.append("私有化部署+运维+培训一条龙服务")
    if any(k in text for k in ("workflow", "automation", "n8n", "dify")):
        paths.append("工作流定制开发：根据企业实际业务场景设计自动化流程")
    if any(k in text for k in ("search", "vector")):
        paths.append("企业搜索方案：从传统关键词搜索升级到语义搜索")
    if not paths:
        paths.append("提供技术咨询和方案设计服务")
        paths.append("可作为AI落地案例在咨询项目中引用")
    return "；".join(paths[:3])


def _make_no_hard_rub(name: str, desc: str, text: str, topics_str: str) -> str:
    """Identify scenarios where this repo should NOT be forced."""
    rubs = []
    if "browser" in text and "automation" in text:
        rubs.append("不能硬说成\"AI员工\"——它需要编程和配置，不是开箱即用的机器人")
        rubs.append("不能直接和RPA对标——它面向开发者，不是业务人员的低代码工具")
    elif "rag" in text or "knowledge" in text:
        rubs.append("不能硬说成\"替代搜索引擎\"——它是基于已有文档的检索，不是全网搜索")
        rubs.append("不能保证100%准确——RAG仍然可能检索到不相关内容，需要人工校验")
    elif "agent" in text or "mcp" in text:
        rubs.append("不能硬说\"AI取代程序员\"——它解决的是连接问题，不是生成代码")
        rubs.append("MCP只是协议，不是产品——实际落地仍需大量工程工作")
    elif "eval" in text or "prompt" in text:
        rubs.append("不能硬说\"AI会自我进化\"——评估只是测量，不是自动改进")
    elif "chat" in text or "bot" in text:
        rubs.append("不能硬说\"通用AI客服\"——每个业务场景需要专门配置和训练")
    else:
        rubs.append("需要具体了解项目能力后判断——不硬蹭热点概念")
        rubs.append("如果README信息不完整，建议先用--no-llm模式生成内容包验证质量")
    return "；".join(rubs)


def _make_deduction_reasons(subscores: dict, total: float) -> str:
    """Explain what pulled the score down from 100."""
    reasons = []
    thresholds = [
        ("understandability", 7, "理解门槛偏高——概念较复杂，需要一定技术背景"),
        ("enterprise_fit", 7, "企业落地场景不够明确——缺乏清晰的商业案例"),
        ("fde_training", 7, "AI-FDE训练价值有限——技术栈不够典型或代码可读性一般"),
        ("service_extensibility", 7, "商业服务延展方式有限——缺乏API/插件/SDK等可扩展接口"),
        ("workflow_integration", 7, "与业务流程结合度不够——无法直接嵌入企业现有工作流"),
        ("risk_controllability", 7, "存在一定风险——许可/隐私/合规方面需要额外关注"),
    ]
    for key, threshold, reason in thresholds:
        if subscores.get(key, 5) < threshold:
            reasons.append(reason)
    if total >= 90 and not reasons:
        return "整体表现优秀，无显著扣分项——各方面均衡，商业价值明确"
    if total >= 75 and not reasons:
        return "商业价值总体良好，无单项短板"
    if not reasons:
        return "部分维度表现一般，建议查看详细子评分"
    return "；".join(reasons)
