"""Report generation — daily_report.md with v4 4-layer scoring structure.

Shows:
  - repo_selection_score (Layer 1)
  - business_value_score (Layer 2)
  - platform_fit_score (Layer 3)
  - risk_profile (Layer 4)
  - Pool assignments (top5 / evergreen / resource / blocked / review)
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from .analyzer import FDEAnalysis
from .business_score import score_business_value
from .platform_score import score_platform_fit
from .risk_score import assess_risk
from .scorer import ScoredRepo


@dataclass
class SkippedRecord:
    full_name: str
    reason: str


def _is_active_recently(repo: ScoredRepo) -> bool:
    try:
        updated = datetime.fromisoformat(repo.updated_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - updated).days <= 7
    except (ValueError, TypeError):
        return False


def _badge(content_type: str) -> str:
    badges = {
        "runnable_project": "`[可运行项目]`",
        "framework_tool": "`[框架/平台]`",
        "awesome_list": "`[资料合集]`",
        "tutorial_guide": "`[教程/指南]`",
        "high_risk": "`[高风险]`",
        "unclear": "`[信息不足]`",
    }
    return badges.get(content_type, "")


def _risk_badge(risk_level: str) -> str:
    badges = {"none": "🟢 低", "low": "🟡 中", "high": "🔴 高"}
    return badges.get(risk_level, "⚪ 未知")


def _pool_badge(pool: str) -> str:
    badges = {
        "top5": "⭐ Top5",
        "evergreen": "🌲 常青",
        "resource": "📚 资料库",
        "blocked": "🚫 已拦截",
        "review": "🔍 待审查",
    }
    return badges.get(pool, "")


def _assign_confidence(repo: ScoredRepo) -> str:
    """Assign confidence tier to a repo based on signal quality.

    Returns: high_confidence | needs_review | unclear | blocked
    """
    if repo.pool == "blocked" or repo.risk_level == "high":
        return "blocked"
    if repo.content_type == "unclear":
        return "unclear"
    if repo.content_type == "high_risk":
        return "blocked"
    if repo.risk_level in ("high",):
        return "needs_review"
    if repo.content_type in ("tutorial_guide", "awesome_list"):
        return "needs_review"
    if repo.stars < 1000 and repo.score < 60:
        return "needs_review"
    if repo.score >= 65 and repo.risk_level in ("low", "none"):
        return "high_confidence"
    return "needs_review"


# ── Platform picks (using platform_score.py) ──────────────────────────────

def _pick_top3_for_platforms(repos: list[ScoredRepo]) -> dict[str, list[ScoredRepo]]:
    safe = [r for r in repos if r.content_type != "high_risk"]
    scored_repos = [(r, score_platform_fit(r)) for r in safe]

    xhs = sorted(scored_repos, key=lambda x: x[1].xiaohongshu, reverse=True)
    dy = sorted(scored_repos, key=lambda x: x[1].douyin, reverse=True)
    vh = sorted(scored_repos, key=lambda x: x[1].videohao, reverse=True)
    wx = sorted(scored_repos, key=lambda x: x[1].wechat, reverse=True)
    geo = sorted(scored_repos, key=lambda x: x[1].geo_trade, reverse=True)

    return {
        "xiaohongshu": [r for r, _ in xhs[:3] if _get_platform_score(r, "xiaohongshu") > 0],
        "douyin": [r for r, _ in dy[:3] if _get_platform_score(r, "douyin") > 0],
        "videohao": [r for r, _ in vh[:3] if _get_platform_score(r, "videohao") > 0],
        "wechat": [r for r, _ in wx[:3] if _get_platform_score(r, "wechat") > 0],
        "geo": [r for r, _ in geo[:3] if _get_platform_score(r, "geo_trade") > 0],
    }


def _get_platform_score(repo: ScoredRepo, platform: str) -> float:
    pf = score_platform_fit(repo)
    attr = "geo_trade" if platform == "geo" else platform
    return getattr(pf, attr, 0.0)


# ── Section formatters ────────────────────────────────────────────────────

def _format_header() -> str:
    return "# 每日 AI 开源项目选题报告\n"


# ── Section 1: Runnable Top 5 (with all 4 score layers) ───────────────────

def _format_runnable_top5(top5: list[ScoredRepo], analyses: dict[str, FDEAnalysis]) -> str:
    lines = ["## 一、今日最适合做主选题的 Top 5 Runnable Projects\n"]
    if not top5:
        lines.append("> 今日暂无满足条件的 runnable project，建议从常青候选或资料库中选取。\n")
        return "\n".join(lines)

    for i, repo in enumerate(top5, 1):
        analysis = analyses.get(repo.full_name)
        bv = score_business_value(repo)
        pf = score_platform_fit(repo)
        risk = assess_risk(repo)

        score_text = f"AI-FDE: {analysis.overall_score}/10" if analysis else ""
        lines.append(f"### {i}. {repo.full_name} — 选题分: {repo.score} {score_text}")
        lines.append(f"{_badge(repo.content_type)} 池: {_pool_badge(getattr(repo, 'pool', ''))} | 综合风险: **{risk.overall}**\n")
        lines.append(f"> {repo.description}\n")
        lines.append(f"⭐ {repo.stars} | 🍴 {repo.forks} | 📝 {repo.language} | 📅 {repo.updated_at[:10]}")
        lines.append(f"🔗 {repo.url}\n")

        # Layer 1 — Selection subscores
        if repo.subscores:
            sub = repo.subscores
            lines.append(f"**选题维度**: AI相关 {sub.get('ai_relevance',0):.0f}/20 | "
                         f"活跃 {sub.get('recency',0):.0f}/15 | "
                         f"清晰 {sub.get('clarity',0):.0f}/15 | "
                         f"可运行 {sub.get('runnability',0):.0f}/15 | "
                         f"可讲性 {sub.get('tellability',0):.0f}/15 | "
                         f"社区 {sub.get('community',0):.0f}/10 | "
                         f"风险 {sub.get('risk_controllable',0):.0f}/10")

        # Layer 2 — Business value
        lines.append(f"**商业价值**: {bv.total}/100 — {bv.summary}")

        # Layer 3 — Platform fit
        best_pf = pf.best_platform
        lines.append(f"**最佳平台**: {best_pf}（{pf.best_platform_score:.0f}/100）| "
                     f"小红书 {pf.xiaohongshu:.0f} | 抖音 {pf.douyin:.0f} | "
                     f"视频号 {pf.videohao:.0f} | 公众号 {pf.wechat:.0f} | 外贸 {pf.geo_trade:.0f}")

        # Layer 4 — Risk
        if risk.warnings:
            lines.append(f"**风险提示**: {'; '.join(risk.warnings[:2])}")

        # AI evidence + recommendation
        if repo.ai_evidence:
            lines.append(f"**AI 相关性**: {', '.join(repo.ai_evidence[:8])}")
        reasons = _build_recommendation_reasons(repo)
        lines.append(f"**推荐理由**: {reasons}")
        if repo.demotion_reason:
            lines.append(f"**注意**: {repo.demotion_reason}")
        lines.append("")
    return "\n".join(lines)


def _build_recommendation_reasons(repo: ScoredRepo) -> str:
    parts = []
    if _is_active_recently(repo):
        parts.append("近期活跃")
    if 1000 <= repo.stars <= 50000:
        parts.append(f"{repo.stars/1000:.0f}K stars 中型项目，新鲜感高")
    elif repo.stars < 1000:
        parts.append("新兴项目，先发优势")
    topics_lower = {t.lower() for t in repo.topics}
    hot = {"agent", "mcp", "rag", "browser-use", "geo"}
    hot_hits = hot & topics_lower
    if hot_hits:
        parts.append(f"覆盖热门话题: {', '.join(sorted(hot_hits))}")
    if repo.contributors_count >= 5:
        parts.append("社区健康")
    if repo.license:
        parts.append(f"有明确许可证({repo.license})")
    return "；".join(parts) if parts else "评分表现优异"


# ── Section 2: Evergreen Candidates ──────────────────────────────────────

def _format_evergreen_section(evergreen: list[ScoredRepo]) -> str:
    lines = ["## 二、常青基础设施候选（适合做专题复盘/深度拆解）\n"]
    if not evergreen:
        lines.append("> 今日无常青基础设施候选。\n")
        return "\n".join(lines)

    lines.append("| # | 项目 | Stars | 选题分 | 商业价值 | 降权原因 |")
    lines.append("|---|------|-------|--------|----------|----------|")
    for i, repo in enumerate(evergreen, 1):
        bv = score_business_value(repo)
        reason = repo.demotion_reason or "常青项目自动降权"
        lines.append(f"| {i} | [{repo.full_name}]({repo.url}) | {repo.stars} | {repo.score} | {bv.total} | {reason} |")
    return "\n".join(lines)


# ── Section 3: Resource Candidates ───────────────────────────────────────

def _format_resource_section(resource: list[ScoredRepo]) -> str:
    lines = ["## 三、资料库/合集候选（适合做工具盘点/资源推荐）\n"]
    if not resource:
        lines.append("> 今日无资料库候选。\n")
        return "\n".join(lines)

    lines.append("| # | 项目 | 类型 | Stars | 降权原因 |")
    lines.append("|---|------|------|-------|----------|")
    for i, repo in enumerate(resource, 1):
        reason = repo.demotion_reason or repo.filter_reason or "资料库候选"
        ct = {"awesome_list": "合集", "tutorial_guide": "教程"}.get(repo.content_type, repo.content_type)
        lines.append(f"| {i} | [{repo.full_name}]({repo.url}) | {ct} | {repo.stars} | {reason} |")
    return "\n".join(lines)


# ── Section 4: High-risk Skipped ─────────────────────────────────────────

def _format_high_risk_section(high_risk: list[ScoredRepo]) -> str:
    lines = ["## 四、高风险跳过项目（不推荐作为选题）\n"]
    if not high_risk:
        lines.append("> 今日无高风险项目。\n")
        return "\n".join(lines)

    lines.append("| # | 项目 | 风险关键词 | 风险评估 |")
    lines.append("|---|------|-----------|----------|")
    for i, repo in enumerate(high_risk, 1):
        risk = assess_risk(repo)
        reason = repo.filter_reason or "高风险项目，不适合AI布道/拆解账号"
        lines.append(f"| {i} | {repo.full_name} | {reason} | {risk.overall} |")
    return "\n".join(lines)


# ── Section 5: Top 6-20 Candidates ───────────────────────────────────────

def _format_candidate_table(top5: list[ScoredRepo], all_candidates: list[ScoredRepo],
                            evergreen: list[ScoredRepo], resource: list[ScoredRepo]) -> str:
    top5_names = {r.full_name for r in top5}
    lines = ["## 五、Top 6-20 候选列表\n"]

    pool = []
    seen = set(top5_names)
    for r in evergreen:
        if r.full_name not in seen:
            pool.append(r); seen.add(r.full_name)
    for r in resource:
        if r.full_name not in seen:
            pool.append(r); seen.add(r.full_name)
    for r in all_candidates:
        if r.full_name not in seen and r.content_type != "high_risk":
            pool.append(r); seen.add(r.full_name)

    pool.sort(key=lambda r: r.score, reverse=True)
    candidates = pool[:15]

    if not candidates:
        lines.append("暂无更多候选项目。\n")
        return "\n".join(lines)

    lines.append("| # | 项目 | 选题分 | 商业价值 | 最佳平台 | 类型 | 风险 |")
    lines.append("|---|------|--------|----------|----------|------|------|")
    for i, repo in enumerate(candidates, 6):
        bv = score_business_value(repo)
        pf = score_platform_fit(repo)
        risk = assess_risk(repo)
        lines.append(f"| {i} | {repo.full_name} | {repo.score} | {bv.total} | {pf.best_platform} | {_badge(repo.content_type)} | {risk.overall} |")
    return "\n".join(lines)


# ── Section 6: Platform picks (using platform_score.py) ──────────────────

def _format_platform_picks_section(repos: list[ScoredRepo]) -> str:
    picks = _pick_top3_for_platforms(repos)
    lines = ["## 六、平台方向推荐\n"]

    platform_labels = {
        "xiaohongshu": ("小红书", "图文"),
        "douyin": ("抖音", "短视频"),
        "videohao": ("视频号", "企业视角"),
        "wechat": ("公众号", "深度长文"),
        "geo": ("外贸/GEO", "商业服务"),
    }

    for key, (name, style) in platform_labels.items():
        lines.append(f"### 今日最适合{name}的 3 个（{style}）\n")
        if picks[key]:
            for r in picks[key]:
                s = _get_platform_score(r, key)
                risk = assess_risk(r)
                lines.append(f"- **{r.full_name}**（适配度 {s:.0f}/100）{_badge(r.content_type)} 风险: {risk.overall}")
                lines.append(f"  {r.description[:80]}\n")
        else:
            lines.append("暂无明确推荐。\n")
        lines.append("")

    return "\n".join(lines)


# ── Section 7: Dedup skipped ─────────────────────────────────────────────

def _format_skipped_section(skipped: list[SkippedRecord]) -> str:
    lines = ["## 七、被降权或跳过的项目原因\n"]
    if not skipped:
        lines.append("本次没有项目被降权或跳过。\n")
    else:
        for record in skipped:
            lines.append(f"- **{record.full_name}**：{record.reason}\n")
    return "\n".join(lines)


# ── Section 8: Data source ───────────────────────────────────────────────

def _format_source_section(obs_stats: dict | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "## 十五、数据来源与时间\n",
        f"- **生成时间**：{now}",
        "- **数据来源**：GitHub REST API Search（15 个关键词）",
        "- **评分引擎**：v4 四层评分体系 — repo_selection_score + business_value_score + platform_fit_score + risk_score",
        "- **分析模式**：无 LLM 模式（仅规则打分）",
        "- **池分类**：Top5 / 常青候选 / 资料库候选 / 高风险拦截 / 待审查",
    ]
    if obs_stats:
        lines.append("")
        lines.append("**管道指标**:")
        lines.append(f"- 抓取数: {obs_stats.get('fetched', 0)}")
        lines.append(f"- 入库数: {obs_stats.get('enriched', 0)}")
        lines.append(f"- 失败数: {obs_stats.get('failed', 0)}")
        if obs_stats.get('fetched', 0) > 0:
            success_rate = obs_stats['enriched'] / max(1, obs_stats['fetched']) * 100
            lines.append(f"- 入库率: {success_rate:.0f}%")
    return "\n".join(lines)


# ── Human review queues (Phase 6) ──────────────────────────────────────────

def _format_confidence_queue(repos: list[ScoredRepo],
                              analyses: dict[str, "FDEAnalysis"]) -> str:
    """Format the high-confidence / needs-review / unclear / blocked queues."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Classify all repos
    high_conf = []
    needs_review = []
    unclear = []
    blocked = []
    evergreen_queue = []
    resource_queue = []
    geo_trade_queue = []

    for r in repos:
        conf = _assign_confidence(r)
        if conf == "high_confidence":
            high_conf.append(r)
        elif conf == "blocked":
            blocked.append(r)
        elif conf == "unclear":
            unclear.append(r)
        else:
            needs_review.append(r)

        # Separate queues for evergreen/resources already demoted
        if r.pool == "evergreen":
            evergreen_queue.append(r)
        if r.pool == "resource":
            resource_queue.append(r)

    # GEO trade scoring
    from .platform_score import score_platform_fit
    for r in repos:
        pf = score_platform_fit(r)
        if pf.geo_trade >= 70 and r.pool not in ("blocked", "resource"):
            geo_trade_queue.append(r)

    lines = []

    # High confidence section
    lines.append("## 八、高置信度选题（可直接使用）")
    lines.append("")
    if high_conf:
        lines.append("> 以下选题信号清晰、风险可控，可直接进入内容制作。")
        lines.append("")
        for r in high_conf[:5]:
            bv = score_business_value(r)
            pf = score_platform_fit(r)
            lines.append(f"- **{r.full_name}** `{_badge(r.content_type)}` 选题分={r.score:.0f} 商业={bv.total:.0f} 最佳平台={pf.best_platform} {_risk_badge(r.risk_level)}")
            lines.append(f"  {r.description or '(无描述)'}")
            lines.append("")
    else:
        lines.append("> 今日无高置信度选题。所有候选需要人工审核。")
        lines.append("")
    lines.append("")

    # Needs human review section
    lines.append("## 九、需人工审核候选")
    lines.append("")
    if needs_review:
        lines.append("> 以下选题存在信息不足、风险模糊或信号矛盾，需人工判断后决定是否采用。")
        lines.append("")
        lines.append("| # | 项目 | 选题分 | 商业 | 风险 | 需检查什么 |")
        lines.append("|---|------|--------|------|------|------------|")
        for i, r in enumerate(needs_review[:15], 1):
            bv = score_business_value(r)
            checks = []
            if r.content_type == "unclear":
                checks.append("信息不足")
            if r.risk_level == "medium":
                checks.append("风险需确认")
            if r.stars < 1000:
                checks.append("低star验证")
            if not r.license:
                checks.append("许可证不明")
            check_str = "、".join(checks) if checks else "常规审核"
            lines.append(f"| {i} | {r.full_name} | {r.score:.0f} | {bv.total:.0f} | {_risk_badge(r.risk_level)} | {check_str} |")
        lines.append("")
    else:
        lines.append("> 无需人工审核的候选。")
        lines.append("")
    lines.append("")

    # Unclear section
    if unclear:
        lines.append("## 十、信息不足项目（需补充资料）")
        lines.append("")
        for r in unclear:
            lines.append(f"- **{r.full_name}** — content_type=unclear, README过短或缺失，stars={r.stars}")
        lines.append("")

    # Evergreen candidates
    if evergreen_queue:
        lines.append("## 十一、常青基础设施候选")
        lines.append("")
        lines.append("> 适合做专题复盘/深度拆解，不建议作为日常选题。")
        lines.append("")
        for r in evergreen_queue:
            lines.append(f"- **{r.full_name}** ⭐{r.stars} — {r.description or '(无描述)'} — 选题分={r.score:.0f}")
        lines.append("")

    # Resource candidates
    if resource_queue:
        lines.append("## 十二、资料库/合集候选")
        lines.append("")
        lines.append("> 适合做工具盘点/资源推荐类内容。")
        lines.append("")
        for r in resource_queue:
            lines.append(f"- **{r.full_name}** ⭐{r.stars} — {r.description or '(无描述)'}")
        lines.append("")

    # GEO trade candidates
    if geo_trade_queue:
        lines.append("## 十三、外贸GEO选题候选")
        lines.append("")
        lines.append("> 以下项目有较高外贸/GEO适配度，适合做海外推广类内容。")
        lines.append("")
        for r in geo_trade_queue[:5]:
            pf = score_platform_fit(r)
            lines.append(f"- **{r.full_name}** GEO={pf.geo_trade:.0f}/100 — {r.description or '(无描述)'}")
        lines.append("")

    # Observability metrics
    lines.append("## 十四、系统可观测性")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 总候选数 | {len(repos)} |")
    lines.append(f"| 高置信度 | {len(high_conf)} |")
    lines.append(f"| 需人工审核 | {len(needs_review)} |")
    lines.append(f"| 信息不足 | {len(unclear)} |")
    lines.append(f"| 已拦截 | {len(blocked)} |")
    lines.append(f"| 常青候选 | {len(evergreen_queue)} |")
    lines.append(f"| 资料库候选 | {len(resource_queue)} |")
    lines.append(f"| GEO候选 | {len(geo_trade_queue)} |")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Main report function
# ═══════════════════════════════════════════════════════════════════════════

def generate_daily_report(
    top5: list[ScoredRepo],
    analyses: dict[str, FDEAnalysis],
    top20: list[ScoredRepo],
    skipped: list[SkippedRecord],
    evergreen: list[ScoredRepo] | None = None,
    resource: list[ScoredRepo] | None = None,
    high_risk: list[ScoredRepo] | None = None,
    obs_stats: dict | None = None,
) -> str:
    if evergreen is None:
        evergreen = []
    if resource is None:
        resource = []
    if high_risk is None:
        high_risk = []

    sections = [
        _format_header(),
        _format_runnable_top5(top5, analyses),
        _format_evergreen_section(evergreen),
        _format_resource_section(resource),
        _format_high_risk_section(high_risk),
        _format_candidate_table(top5, top20, evergreen, resource),
        _format_platform_picks_section(top20),
        _format_skipped_section(skipped),
        _format_confidence_queue(top20, analyses),  # Phase 6: human review queues
        _format_source_section(obs_stats),
    ]
    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 8: Daily Brief (one-screen decision workbench)
# ═══════════════════════════════════════════════════════════════════════════

def generate_daily_brief(
    top5: list,
    all_scored: list,
    evergreen: list,
    resource: list,
    high_risk: list,
    obs_stats: dict | None = None,
    failure_summary: str = "",
) -> str:
    """Generate Phase 8 daily_brief — "一屏工作台" for 30-60 min workflow.

    7 sections designed to fit on one screen and guide the daily decision process.
    """
    if obs_stats is None:
        obs_stats = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    fetched = obs_stats.get("fetched", 0)
    enriched = obs_stats.get("enriched", 0)
    failed = obs_stats.get("failed", 0)

    # Compute pipeline health
    enrich_rate = (enriched / max(1, fetched) * 100) if fetched > 0 else 0
    is_healthy = enrich_rate >= 80 and failed <= 2

    lines = [
        f"# Daily Brief — {today}",
        "",
        "> 一屏工作台 · 30-60分钟完成每日选题决策",
        "",
    ]

    # ── Section 0: Decision Summary (top of screen) ──────────────────
    top5_count = len(top5)
    lines.append("## 今日决策摘要")
    lines.append("")

    if top5:
        r = top5[0]
        bv = score_business_value(r)
        pf = score_platform_fit(r)
        risk = assess_risk(r)
        evidence = bv.evidence if hasattr(bv, 'evidence') else {}
        lines.append(f"**最推荐项目**: `{r.full_name}`")
        lines.append(f"**为什么是它**: {evidence.get('one_liner', bv.summary)}")
        lines.append(f"**优先发布平台**: {pf.best_platform}（适配度 {pf.best_platform_score:.0f}/100）")
        if pf.reasons and pf.best_platform in ("小红书", "抖音", "视频号", "公众号", "外贸/GEO"):
            plat_key_map = {"小红书": "xiaohongshu", "抖音": "douyin", "视频号": "videohao",
                           "公众号": "wechat", "外贸/GEO": "geo"}
            plat_key = plat_key_map.get(pf.best_platform, "")
            if plat_key and plat_key in pf.reasons:
                lines.append(f"**平台理由**: {pf.reasons[plat_key]}")
        lines.append(f"**选题分**: {r.score:.0f} | 商业价值: {bv.total:.0f} | 风险: {risk.overall}")

        # LLM recommendation
        llm_suggestion = "建议接 LLM" if (top5_count >= 3 and is_healthy) else ("条件接入" if top5_count > 0 else "不建议接 LLM")
        lines.append(f"**是否建议接 LLM**: {llm_suggestion}")

        # Estimated time
        lines.append(f"**预计人工耗时**: 30-45 分钟（含内容包生成 + 审核 + 发布）")
    else:
        lines.append("**最推荐项目**: 无 — 今日高置信选题不足")
        lines.append("**建议**: 检查 review_queue 是否有可提升的候选，或扩展搜索关键词")
    lines.append("")

    # ── Section 0b: What NOT to do today ──
    dont_do = []
    if high_risk:
        dont_do.append(f"**{len(high_risk)} 个高风险项目已拦截** — 不要尝试发布: {', '.join(r.full_name for r in high_risk[:3])}")
    if evergreen[:3] and top5:
        dont_do.append(f"**常青项目不建议今天做** — 如 {evergreen[0].full_name}，留到专题日深度拆解")
    if resource[:3]:
        dont_do.append(f"**资料库项目不建议单独推** — 如 {resource[0].full_name}，放到合集/盘点里用")
    if dont_do:
        lines.append("**今天不建议做的项目**:")
        for item in dont_do:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 1: Today Overview ───────────────────────────────────
    health_icon = "✓" if is_healthy else "⚠"
    lines.append("## 一、今日概览")
    lines.append("")
    lines.append(f"| 指标 | 值 | 状态 |")
    lines.append(f"|------|----|------|")
    lines.append(f"| 抓取数 | {fetched} | — |")
    lines.append(f"| 入库数 | {enriched} | — |")
    lines.append(f"| 入库率 | {enrich_rate:.0f}% | {health_icon} |")
    lines.append(f"| 失败数 | {failed} | {'OK' if failed <= 2 else 'CHECK'} |")
    lines.append(f"| 管道状态 | {'HEALTHY' if is_healthy else 'DEGRADED'} | {health_icon} |")
    lines.append("")

    # ── Section 2: Top 5 Picks ──────────────────────────────────────
    lines.append("## 二、Top 5 高置信选题")
    lines.append("")
    if top5_count >= 5:
        lines.append(f"> 今日完整覆盖 {top5_count} 个高置信选题。")
        lines.append("")
    elif top5_count > 0:
        lines.append(f"> **今日高置信主选题不足（仅 {top5_count}/5），建议从审核队列中补充。**")
        lines.append("")
    else:
        lines.append("> **今日高置信主选题不足，无 Top 5 推荐。请检查 review_queue 是否有可提升的候选。**")
        lines.append("")

    if top5:
        lines.append("| # | 项目 | 选题分 | 商业 | 最佳平台 | 建议操作 |")
        lines.append("|---|------|--------|------|----------|----------|")
        for i, r in enumerate(top5[:5], 1):
            bv = score_business_value(r)
            pf = score_platform_fit(r)
            action = f"`python run.py content {r.full_name}`"
            lines.append(f"| {i} | **{r.full_name}** | {r.score:.0f} | {bv.total:.0f} | {pf.best_platform} | {action} |")
        lines.append("")
        # Recommended repo for content pack
        if top5:
            r = top5[0]
            lines.append(f"> **建议优先生成**: `{r.full_name}` → `python run.py content {r.full_name}`")
            lines.append("")
    else:
        lines.append("| - | 无高置信选题 | - | - | - | 请检查 review_queue |")
        lines.append("")

    # ── Section 3: Needs Human Review ───────────────────────────────
    needs_review = [r for r in all_scored if r.pool in ("review",)]
    review_count = len(needs_review)
    lines.append("## 三、需人工审核")
    lines.append("")
    if review_count > 0:
        lines.append(f"> 共 **{review_count}** 个候选需要人工确认。")
        lines.append(f"> 详见: `data/reports/review_queue_{today}.md`")
        lines.append("")
        lines.append("| 项目 | 选题分 | 原因 |")
        lines.append("|------|--------|------|")
        for r in needs_review[:5]:
            reason = "信息不足" if r.content_type == "unclear" else (r.filter_reason or "待审核")
            lines.append(f"| {r.full_name} | {r.score:.0f} | {reason} |")
        lines.append("")
    else:
        lines.append("> 无需人工审核的候选。")
        lines.append("")

    # ── Section 4: Risk Summary ─────────────────────────────────────
    lines.append("## 四、风险拦截摘要")
    lines.append("")
    if high_risk:
        lines.append(f"> 今日拦截 **{len(high_risk)}** 个高风险项目。")
        lines.append("")
        for r in high_risk[:5]:
            risk = assess_risk(r)
            lines.append(f"- 已拦截: **{r.full_name}** — {r.filter_reason or risk.overall}")
        lines.append("")
    else:
        lines.append("> 今日无高风险项目被拦截。")
        lines.append("")

    # ── Section 5: Pipeline Health ──────────────────────────────────
    lines.append("## 五、管道健康度")
    lines.append("")
    lines.append(f"| 检查项 | 状态 |")
    lines.append(f"|--------|------|")
    lines.append(f"| 抓取成功率 | {'PASS' if enrich_rate >= 80 else 'WARN'} ({enrich_rate:.0f}%) |")
    lines.append(f"| 常青分流 | {'OK' if evergreen else 'N/A'} ({len(evergreen)}个) |")
    lines.append(f"| 资料库分流 | {'OK' if resource else 'N/A'} ({len(resource)}个) |")
    lines.append(f"| 风险拦截 | {'OK' if high_risk else 'N/A'} ({len(high_risk)}个) |")
    if failure_summary:
        lines.append(f"| failure_summary | 见下方 |")
    else:
        lines.append(f"| 错误记录 | 无严重错误 |")
    lines.append("")
    if failure_summary:
        lines.append(f"```")
        lines.append(failure_summary)
        lines.append(f"```")
        lines.append("")

    # ── Section 6: Time Breakdown ───────────────────────────────────
    lines.append("## 六、预计耗时分解")
    lines.append("")
    lines.append("| 步骤 | 预估耗时 | 说明 |")
    lines.append("|------|----------|------|")
    lines.append("| 1. 查看 daily_brief | 2-3 分钟 | 一眼看清今日选题全貌 |")
    lines.append("| 2. 审核 review_queue | 5-10 分钟 | 检查需人工确认的候选，完成8项清单 |")
    lines.append("| 3. 选取最终选题 | 2-3 分钟 | 从 Top 5 + 审核通过的候选中选择 1-3 个 |")
    lines.append("| 4. 生成内容包 | 15-30 分钟 | `python run.py content owner/repo` × N |")
    lines.append("| 5. 发布内容 | 5-10 分钟 | 将内容包发布到各平台 |")
    lines.append("| 6. 标记已完成 | 1 分钟 | 更新 seen_repos 状态 |")
    lines.append(f"| **总计** | **30-57 分钟** | 符合 30-60 分钟工作流目标 |")
    lines.append("")

    # ── Section 7: Quick Actions ────────────────────────────────────
    lines.append("## 七、快速操作")
    lines.append("")
    lines.append("```bash")
    lines.append("# 环境健康检查")
    lines.append("python run.py doctor")
    lines.append("")
    lines.append("# 查看完整报告")
    lines.append(f"cat data/reports/daily_report_{today}.md")
    lines.append("")
    lines.append("# 查看人工审核队列")
    lines.append(f"cat data/reports/review_queue_{today}.md")
    lines.append("")
    lines.append("# 为 Top 1 选题生成内容包")
    if top5:
        lines.append(f"python run.py content {top5[0].full_name}")
    else:
        lines.append("python run.py content owner/repo")
    lines.append("")
    lines.append("# 运行质量门")
    lines.append("python run.py quality-gate")
    lines.append("```")
    lines.append("")

    # ── Section 8: Post-Run Summary (Phase 9) ────────────────────────
    lines.append("## 八、运行后摘要")
    lines.append("")
    # LLM recommendation
    lines.append("### 今日是否建议接 LLM")
    lines.append("")
    if top5_count >= 3 and is_healthy:
        lines.append("> **建议接 LLM**：有足够高置信选题且管道健康，LLM 可生成高质量内容包。")
        llm_ready = "yes"
    elif top5_count > 0:
        lines.append("> **条件接入**：选题数量不足但可用，建议先用 --no-llm 验证 1-2 个选题后再接 LLM。")
        llm_ready = "conditional"
    else:
        lines.append("> **不建议接 LLM**：选题不足或管道异常，先排查问题。")
        llm_ready = "no"
    lines.append("")
    # Recommended repo
    lines.append("### 建议生成内容包的 repo")
    lines.append("")
    if top5:
        r = top5[0]
        pf = score_platform_fit(r)
        lines.append(f"- **首选**: `{r.full_name}` → `python run.py content {r.full_name}`")
        lines.append(f"  - 选题分: {r.score:.0f} | 最佳平台: {pf.best_platform}")
        if len(top5) > 1:
            r2 = top5[1]
            lines.append(f"- **备选**: `{r2.full_name}` → `python run.py content {r2.full_name}`")
    else:
        lines.append("- 无推荐 — 今日高置信选题不足")
    lines.append("")
    # Estimated human time
    lines.append("### 预计人工耗时")
    lines.append("")
    review_min = min(10, len(needs_review) * 1 if 'needs_review' in dir() else 5)
    content_min = min(30, top5_count * 10) if top5 else 15
    total_min = 5 + review_min + 3 + content_min + 10 + 1
    lines.append(f"- 查看 brief + 审核队列: ~{5 + review_min} 分钟")
    lines.append(f"- 选取选题: ~3 分钟")
    lines.append(f"- 生成内容包: ~{content_min} 分钟")
    lines.append(f"- 发布: ~10 分钟")
    lines.append(f"- **预计总计: ~{total_min} 分钟**")
    lines.append("")
    # remaining risks
    lines.append("### 剩余关注点")
    lines.append("")
    risks = []
    if top5_count < 5:
        risks.append(f"高置信选题仅 {top5_count}/5 个，建议扩展搜索关键词")
    if not is_healthy:
        risks.append("管道健康度下降，检查网络和 GitHub API 状态")
    if high_risk:
        risks.append(f"有 {len(high_risk)} 个高风险项目被拦截，确认无漏网")
    if needs_review:
        risks.append(f"{len(needs_review)} 个候选待人工审核")
    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("- 无明显风险")
    lines.append("")

    lines.append("---")
    lines.append(f"生成时间：{now}")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 8: Review Queue Report (human review pipeline)
# ═══════════════════════════════════════════════════════════════════════════

REVIEW_QUEUE_CHECKLIST = [
    "1. 选题是否符合账号定位（AI布道/工具拆解/出海GEO）？",
    "2. 项目README是否清晰说明用途和核心功能？",
    "3. 许可证是否允许内容引用（MIT/Apache/CC）？",
    "4. Star数是否在合理范围（<100需人工确认质量，>50000可能是过气热点）？",
    "5. 最近一周是否有commit或release？（确认项目仍在活跃）",
    "6. 有没有竞品账号已经做过类似内容？（避免重复选题）",
    "7. 项目是否涉及版权/隐私/NSFW/政治敏感内容？",
    "8. 是否值得分配30-60分钟制作完整内容包？",
]

REVIEW_QUEUE_ACTIONS = [
    ("approve_for_content_pack", "采用 — 直接生成内容包，建议接 LLM"),
    ("review_manually", "人工审核 — 补充信息后再决定是否采用"),
    ("save_for_later", "存档备查 — 有价值但不适合今天做，归入常青池"),
    ("reject", "拒绝 — 不相关或质量不达标，不入库"),
    ("blocked_do_not_publish", "拦截 — 高风险/敏感内容，禁止发布"),
]


def generate_review_queue(
    top5: list,
    evergreen: list,
    resource: list,
    high_risk: list,
    all_scored: list,
    analyses: dict | None = None,
) -> str:
    """Generate Phase 8 review queue report for human decision making.

    Args:
        top5: Top 5 runnable projects
        evergreen: Evergreen candidate repos
        resource: Resource candidate repos
        high_risk: Blocked/skipped repos
        all_scored: All scored repos (top20 pool)
        analyses: Optional LLM analyses keyed by full_name

    Returns:
        Markdown report string.
    """
    if analyses is None:
        analyses = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        f"# 人工审核队列 — {today}",
        "",
        f"生成时间：{now}",
        "",
        "> 本报告列出今日所有候选项目，按置信度分级，供人工审核决策。",
        "> 每个候选标注了需要人工检查的关键点。",
        "",
        "---",
        "",
    ]

    # ── Section 0: Most Recommended Today ─────────────────────────
    lines.append("## 零、今日最推荐发布")
    lines.append("")
    if top5:
        best = top5[0]
        bv = score_business_value(best)
        pf = score_platform_fit(best)
        risk = assess_risk(best)
        reasons = []
        if best.score >= 70:
            reasons.append(f"高选题分({best.score:.0f}/100)")
        if best.stars >= 1000:
            reasons.append(f"高Star数({best.stars})")
        if best.license:
            reasons.append(f"许可证明确({best.license})")
        if best.topics:
            ai_topics = [t for t in best.topics if any(k in t.lower() for k in ("ai", "llm", "ml", "agent", "gpt"))]
            if ai_topics:
                reasons.append(f"AI相关话题({', '.join(ai_topics[:3])})")
        if (best.readme or "").strip() and len(best.readme or "") > 500:
            reasons.append("README 质量高")

        risk_points = []
        if risk.overall == "medium":
            risk_points.append("风险中等级，建议人工确认")
        elif risk.overall == "high":
            risk_points.append("高风险，不建议发布")
        if best.stars < 100:
            risk_points.append("低 Star 数，质量待验证")
        if not best.license:
            risk_points.append("许可证不明，商用需注意")
        if best.content_type == "unclear":
            risk_points.append("README 信息不足，需人工补充")

        platforms = pf.best_platform or "深度分析"
        suitable = [platforms]
        if pf.xiaohongshu >= 60:
            suitable.append("小红书")
        if pf.douyin >= 60:
            suitable.append("抖音")
        if pf.wechat >= 60:
            suitable.append("公众号")

        needs_edit = "是" if (risk_points or best.content_type == "unclear") else "否"
        ready_for_content = "是" if (best.score >= 65 and risk.overall in ("low", "none")) else "需人工审核后决定"

        lines.append(f"| 项目 | [{best.full_name}]({best.url}) |")
        lines.append(f"| 评分 | {best.score:.0f}/100 |")
        lines.append(f"| 为什么推荐 | {'；'.join(reasons) if reasons else '规则综合评分最高'} |")
        lines.append(f"| 风险点 | {'；'.join(risk_points) if risk_points else '无重大风险'} |")
        lines.append(f"| 适合平台 | {'、'.join(suitable)} |")
        lines.append(f"| 是否需要人工改稿 | {needs_edit} |")
        lines.append(f"| 是否可进入 content 生成 | {ready_for_content} |")
        if ready_for_content == "是":
            lines.append(f"| 操作 | `python run.py content {best.full_name}` |")
        lines.append("")
    else:
        lines.append("> 今日无高置信度 Top 5 选题，无法推荐。")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、高置信度 Top 5（可直接采用）")
    lines.append("")
    if top5:
        lines.append("| # | 项目 | Pool | 置信度 | 选题分 | 建议操作 | 需检查什么 |")
        lines.append("|---|------|------|--------|--------|----------|------------|")
        for i, r in enumerate(top5[:5], 1):
            bv = score_business_value(r)
            risk = assess_risk(r)
            checks = []
            if risk.overall == "medium":
                checks.append("风险中等级")
            if r.stars < 100:
                checks.append("低star验证质量")
            if not r.license:
                checks.append("许可证不明")
            if r.content_type == "unclear":
                checks.append("README信息不足")
            check_str = "、".join(checks) if checks else "无特别关注点"
            lines.append(
                f"| {i} | [{r.full_name}]({r.url}) | {r.pool} | 高 | {r.score:.0f} | 采用 | {check_str} |"
            )
        lines.append("")
    else:
        lines.append("> 今日无高置信度 Top 5 选题。")
        lines.append("")

    # ── Category 2: Needs Human Review ──────────────────────────────
    lines.append("## 二、需要人工审核")
    lines.append("")
    needs_review = [r for r in all_scored if r.pool in ("review",) and r.full_name not in {t.full_name for t in top5}]
    # Also include any with risk=medium and not in other pools
    for r in all_scored:
        risk = assess_risk(r)
        if risk.overall == "medium" and r.pool == "top5" and r.full_name not in {t.full_name for t in top5}:
            if r not in needs_review:
                needs_review.append(r)

    if needs_review:
        lines.append("| # | 项目 | Pool | 置信度 | 选题分 | 风险 | 需检查什么 | 建议操作 |")
        lines.append("|---|------|------|--------|--------|------|------------|----------|")
        for i, r in enumerate(needs_review[:15], 1):
            risk = assess_risk(r)
            checks = []
            actions = []
            if r.content_type == "unclear":
                checks.append("README信息不足")
                actions.append("补充信息后采用")
            if risk.overall in ("medium", "high"):
                checks.append(f"风险={risk.overall}")
                actions.append("人工确认风险")
            if r.stars < 100:
                checks.append("低star验证")
            if not r.license:
                checks.append("许可证不明")
            check_str = "、".join(checks) if checks else "常规审核"
            action_str = "、".join(actions) if actions else "审核后决定"
            conf = "中" if r.content_type == "unclear" else "中高"
            lines.append(
                f"| {i} | [{r.full_name}]({r.url}) | {r.pool} | {conf} | {r.score:.0f} | {risk.overall} | {check_str} | {action_str} |"
            )
        lines.append("")
    else:
        lines.append("> 今日无需人工审核的候选。")
        lines.append("")

    # ── Category 3: Blocked Candidates ──────────────────────────────
    lines.append("## 三、已拦截项目（不建议采用）")
    lines.append("")
    if high_risk:
        for i, r in enumerate(high_risk[:10], 1):
            risk = assess_risk(r)
            reason = r.filter_reason or "高风险项目"
            lines.append(f"### 🚫 {r.full_name} — 已拦截")
            lines.append("")
            lines.append(f"| 项目 | {r.full_name} |")
            lines.append(f"| 拦截原因 | {reason} |")
            lines.append(f"| 风险等级 | {risk.overall} |")
            lines.append(f"| 建议 | 不发布。此项目不符合安全策略，已自动拦截。 |")
            # Show what keywords triggered the block
            if hasattr(r, 'ai_evidence') and isinstance(r.ai_evidence, list) and r.ai_evidence:
                keywords = [str(k) for k in r.ai_evidence[:5] if not str(k).startswith("WEAK:")]
                if keywords:
                    lines.append(f"| 触发信号 | {', '.join(keywords)} |")
            elif hasattr(r, 'ai_evidence') and isinstance(r.ai_evidence, dict):
                keywords = r.ai_evidence.get("risk_keywords", [])
                if keywords:
                    lines.append(f"| 触发关键词 | {', '.join(keywords[:5])} |")
            lines.append("")
        lines.append("")
    else:
        lines.append("> 今日无被拦截项目。")
        lines.append("")

    # ── Category 4: Evergreen Candidates ────────────────────────────
    lines.append("## 四、常青候选（归档备查，非日常选题）")
    lines.append("")
    if evergreen:
        lines.append("| # | 项目 | Stars | 选题分 | 降权原因 | 建议操作 |")
        lines.append("|---|------|-------|--------|----------|----------|")
        for i, r in enumerate(evergreen[:10], 1):
            bv = score_business_value(r)
            reason = r.demotion_reason or "常青项目自动降权"
            lines.append(
                f"| {i} | [{r.full_name}]({r.url}) | {r.stars} | {r.score:.0f} | {reason} | 降级为常青候选 |"
            )
        lines.append("")
    else:
        lines.append("> 今日无常青候选。")
        lines.append("")

    # ── Category 5: Resource Candidates ─────────────────────────────
    lines.append("## 五、资料库候选（工具盘点/资源推荐）")
    lines.append("")
    if resource:
        lines.append("| # | 项目 | Stars | 类型 | 选题分 | 建议操作 |")
        lines.append("|---|------|-------|------|--------|----------|")
        for i, r in enumerate(resource[:10], 1):
            ct = {"awesome_list": "合集", "tutorial_guide": "教程"}.get(r.content_type, r.content_type)
            lines.append(
                f"| {i} | [{r.full_name}]({r.url}) | {r.stars} | {ct} | {r.score:.0f} | 降级为资料库 |"
            )
        lines.append("")
    else:
        lines.append("> 今日无资料库候选。")
        lines.append("")

    # ── Category 6: GEO Trade Candidates ────────────────────────────
    lines.append("## 六、外贸/GEO 选题候选")
    lines.append("")
    geo_candidates = []
    for r in all_scored:
        pf = score_platform_fit(r)
        if pf.geo_trade >= 70 and r.pool not in ("blocked", "resource"):
            geo_candidates.append((r, pf.geo_trade))
    geo_candidates.sort(key=lambda x: -x[1])

    if geo_candidates:
        lines.append("| # | 项目 | GEO 适配度 | 选题分 | 建议操作 |")
        lines.append("|---|------|-----------|--------|----------|")
        for i, (r, geo_score) in enumerate(geo_candidates[:5], 1):
            lines.append(
                f"| {i} | [{r.full_name}]({r.url}) | {geo_score:.0f}/100 | {r.score:.0f} | 采用（GEO方向） |"
            )
        lines.append("")
    else:
        lines.append("> 今日无高适配度 GEO 候选。")
        lines.append("")

    # ── 5 Suggested Actions ─────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 建议操作（5项）")
    lines.append("")
    for action, desc in REVIEW_QUEUE_ACTIONS:
        lines.append(f"- **{action}**：{desc}")
    lines.append("")

    # ── 8-Question Human Review Checklist ───────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 人工审核清单（8项检查）")
    lines.append("")
    lines.append("在决定是否采用某个选题前，请逐项确认：")
    lines.append("")
    for item in REVIEW_QUEUE_CHECKLIST:
        lines.append(f"- [ ] {item}")
    lines.append("")

    # ── Summary Stats ───────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 队列统计")
    lines.append("")
    lines.append(f"| 队列 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 高置信度 Top 5 | {len(top5[:5])} |")
    lines.append(f"| 需人工审核 | {len(needs_review)} |")
    lines.append(f"| 已拦截 | {len(high_risk)} |")
    lines.append(f"| 常青候选 | {len(evergreen)} |")
    lines.append(f"| 资料库候选 | {len(resource)} |")
    lines.append(f"| GEO 候选 | {len(geo_candidates)} |")
    lines.append(f"| **总计** | **{len(top5[:5]) + len(needs_review) + len(high_risk) + len(evergreen) + len(resource) + len(geo_candidates)}** |")
    lines.append("")

    return "\n".join(lines)


def generate_candidate_report(repos: list[ScoredRepo]) -> str:
    sorted_repos = sorted(repos, key=lambda r: r.score, reverse=True)
    top20 = sorted_repos[:20]

    lines = ["# GitHub AI 项目候选列表\n"]
    lines.append(f"生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    lines.append("## Top 20 候选项目\n")
    lines.append("| # | 项目 | Stars | 选题分 | 商业价值 | 最佳平台 | 类型 | 描述 |")
    lines.append("|---|------|-------|--------|----------|----------|------|------|")
    for i, repo in enumerate(top20, 1):
        bv = score_business_value(repo)
        pf = score_platform_fit(repo)
        desc = (repo.description or "")[:50]
        lines.append(f"| {i} | {repo.full_name} | {repo.stars} | {repo.score} | {bv.total} | {pf.best_platform} | {_badge(repo.content_type)} | {desc} |")
    if not repos:
        lines.append("| - | 暂无数据 | - | - | - | - | - | - |")

    lines.append("")
    lines.append(_format_platform_picks_section(top20))
    lines.append("")
    lines.append(_format_source_section())

    return "\n".join(lines)
