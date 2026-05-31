"""Content Pack V2 — 11-file structured content generation.

Supports both LLM-powered and no-LLM fallback modes.
- With LLM: generates full deep content for all 11 files
- Without LLM: generates data-filled templates with [TODO] markers

Output: data/content_packs/{owner__repo}/
"""
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .business_score import score_business_value
from .config import CONTENT_PACKS_DIR
from .dedup import mark_as_generated, slugify_repo_name
from .enricher import enrich_repo
from .platform_score import score_platform_fit
from .risk_score import assess_risk
from .scorer import (
    ScoredRepo,
    classify_content_type,
    check_ai_eligibility,
    check_high_risk,
    score_repo,
)

logger = logging.getLogger(__name__)

# V2 content file list (in order)
CONTENT_FILES_V2 = [
    "00_repo_snapshot",
    "01_ai_fde_deep_analysis",
    "02_xiaohongshu",
    "03_douyin_video",
    "04_videohao_script",
    "05_wechat_article",
    "06_storyboard",
    "07_geo_angle",
    "08_enterprise_pitch",
    "09_risk_review",
    "10_quality_check",
]

# Map every content pack output filename → template filename (without .md extension)
CONTENT_PACK_TEMPLATE_MAP = {
    "00_repo_snapshot": "00_repo_snapshot",
    "01_ai_fde_deep_analysis": "ai_fde_analysis",
    "02_xiaohongshu": "xiaohongshu",
    "03_douyin_video": "douyin",
    "04_videohao_script": "video_script",
    "05_wechat_article": "wechat_article",
    "06_storyboard": "storyboard",
    "07_geo_angle": "07_geo_angle",
    "08_enterprise_pitch": "08_enterprise_pitch",
    "09_risk_review": "risk_review",
    "10_quality_check": "quality_check",
}


def _has_llm() -> bool:
    """Check if LLM API key is configured."""
    try:
        from .config import get_llm_config
        get_llm_config()
        return True
    except ValueError:
        return False


# Research brief header used in all no-LLM files
RESEARCH_BRIEF_HEADER = (
    "> ⚠️ 研究简报模式 — LLM 不可用，内容由规则自动生成\n"
    "> 这不是可发布文章。请用下方素材在 30 分钟内人工补写。\n"
)


def _check_llm_health(timeout: int = 10) -> tuple:
    """Actually test LLM API connectivity with a minimal request.

    Returns (available: bool, mode: str, statuses: list[dict]).
    mode is "full_llm" or "structured_fallback".
    """
    import time
    import requests
    from .config import get_llm_providers

    providers = get_llm_providers()
    if not providers:
        return False, "structured_fallback", []

    statuses = []
    for p in providers:
        try:
            t0 = time.monotonic()
            resp = requests.post(
                p["base_url"].rstrip("/") + "/chat/completions",
                json={
                    "model": p["model"],
                    "messages": [{"role": "user", "content": "OK"}],
                    "max_tokens": 5,
                    "temperature": 0,
                },
                headers={
                    "Authorization": f"Bearer {p['api_key']}",
                    "Content-Type": "application/json",
                },
                timeout=(3, timeout),
            )
            latency = (time.monotonic() - t0) * 1000
            resp.raise_for_status()
            statuses.append({"provider": p["name"], "available": True, "latency_ms": latency})
            return True, "full_llm", statuses
        except Exception as e:
            statuses.append({"provider": p["name"], "available": False, "error": str(e)[:100]})

    return False, "structured_fallback", statuses


def _build_research_brief_sections(ctx: dict) -> dict:
    """Build 10 high-density info items from rule-based data.

    Used by all no-LLM research brief generators. No TODOs.
    """
    full_name = ctx.get("full_name", "未知")
    name = ctx.get("name", full_name)
    desc = ctx.get("description", "暂无描述")
    stars = ctx.get("stars", "0")
    language = ctx.get("language", "未知")
    license_name = ctx.get("license", "未指定")
    topics = ctx.get("topics", "无")
    ai_evidence = ctx.get("ai_evidence", "暂无")

    # 1. One-liner
    one_liner = desc

    # 2. Problem solved
    problem_solved = ctx.get("business_summary", f"{name} 是一个 {language} 开源项目，解决 AI 相关场景需求。")

    # 3. Target audience
    risk_overall = ctx.get("risk_overall", "low")
    if risk_overall == "low":
        target = "AI 技术爱好者、开发者、技术决策者"
    else:
        target = "有技术背景的开发者、企业技术团队（需注意使用边界）"

    # 4. Core features (from topics + ai_evidence)
    features = [t.strip() for t in topics.split(",") if t.strip()][:5]
    features_str = "、".join(features) if features else f"基于 README 描述：{desc[:100]}"

    # 5. Why worth attention
    sel_score = ctx.get("selection_score", "N/A")
    reasons = []
    try:
        if int(stars) > 10000:
            reasons.append(f"高 Star 数（{stars}）")
    except ValueError:
        pass
    if license_name not in ("未指定", ""):
        reasons.append(f"许可证明确（{license_name}）")
    if ai_evidence and ai_evidence != "暂无":
        reasons.append(f"AI 相关证据：{ai_evidence[:80]}")
    if ctx.get("platform_best"):
        reasons.append(f"最适合发布平台：{ctx['platform_best']}")
    why_worth = "；".join(reasons) if reasons else f"选题评分 {sel_score}/100，建议进一步评估"

    # 6. Comparison with similar projects
    comparison = f"与同类项目相比，{name} 的特点是：{desc[:150]}。具体差异化需人工判断。"

    # 7. Potential risks
    risk_warnings = ctx.get("risk_warnings", [])
    if isinstance(risk_warnings, str):
        risk_warnings = [risk_warnings]
    if risk_warnings and risk_warnings != ["无"]:
        risks_str = "；".join(str(w) for w in risk_warnings if w and w != "无")
    else:
        risks_str = "未检测到明显风险信号，但建议发布前人工确认许可证和内容合规性"

    # 8. Suitable platforms
    platforms = []
    for pkey, plabel in [("platform_wechat", "公众号"), ("platform_xhs", "小红书"),
                          ("platform_douyin", "抖音"), ("platform_videohao", "视频号"),
                          ("platform_geo", "外贸/GEO")]:
        try:
            score = float(ctx.get(pkey, "0"))
            if score >= 70:
                platforms.append(f"{plabel}({score:.0f})")
            elif score >= 50:
                platforms.append(f"{plabel}({score:.0f}, 需调整)")
        except (ValueError, TypeError):
            pass
    platforms_str = "、".join(platforms) if platforms else ctx.get("platform_best", "公众号")

    # 9. Human writing prompts
    best_platform = ctx.get("platform_best", "公众号")
    writing_prompt = (
        f"建议围绕 {name} 写一篇 {best_platform} 内容。核心角度："
        f"用「今天我拆了一个开源项目」的学习视角切入，"
        f"先解释 {desc[:60]}，再展开 3 个落地场景，最后总结风险边界。"
    )

    # 10. Re-usable LLM prompt
    llm_prompt = (
        f"你是一个专注于 AI-FDE（功能创新/差异化/生态价值）的技术博主。"
        f"请为开源项目 {full_name}（{desc}，{stars} stars，{language}，许可证：{license_name}）"
        f"写一篇{best_platform}风格的内容。"
        f"要求：不写软文，不卖课，用学习笔记视角，诚实标注风险。"
        f"素材：核心功能包括 {features_str}。风险提示：{risks_str}。"
    )

    return {
        "one_liner": one_liner,
        "problem_solved": problem_solved,
        "target_audience": target,
        "core_features": features_str,
        "why_worth_attention": why_worth,
        "comparison": comparison,
        "potential_risks": risks_str,
        "suitable_platforms": platforms_str,
        "human_writing_prompt": writing_prompt,
        "reusable_llm_prompt": llm_prompt,
    }


def _build_repo_context(repo: ScoredRepo) -> dict:
    """Build a rich context dict from a scored repo for template filling.

    Includes all 4 score layers: repo_selection, business_value, platform_fit, risk.
    """
    is_risk, risk_hits = check_high_risk(repo)
    is_ai, ai_evidence = check_ai_eligibility(repo)
    content_type = classify_content_type(repo)
    business = score_business_value(repo)
    platform = score_platform_fit(repo)
    risk_profile = assess_risk(repo)

    readme = repo.readme or ""
    readme_excerpt = readme[:1500]

    # Derive repo identity anchors for LLM prompt grounding
    from .analyzer import (
        _derive_confirmed_features,
        _derive_unsupported_features,
        _derive_risk_boundaries,
    )
    confirmed_features = _derive_confirmed_features(repo)
    unsupported_features = _derive_unsupported_features(repo)
    risk_boundaries = _derive_risk_boundaries(repo)

    return {
        # ── Repo identity anchors (prevents hallucination) ──
        "confirmed_features": confirmed_features,
        "unsupported_features": unsupported_features,
        "risk_boundaries": risk_boundaries,
        # ── Fields ──
        "full_name": repo.full_name,
        "name": repo.name,
        "description": repo.description or "暂无描述",
        "url": repo.url,
        "language": repo.language or "未知",
        "stars": str(repo.stars),
        "forks": str(repo.forks),
        "updated_at": repo.updated_at[:10] if repo.updated_at else "未知",
        "topics": ", ".join(repo.topics) if repo.topics else "无",
        "license": repo.license or "未指定",
        "readme_excerpt": readme_excerpt,
        "contributors_count": str(repo.contributors_count),
        # ── Layer 1: Repo Selection Score ──
        "selection_score": str(repo.score),
        "selection_subscores": repo.subscores,
        # ── Layer 2: Business Value Score ──
        "business_score": str(business.total),
        "business_summary": business.summary,
        "understandability": str(business.subscores.get("understandability", 5)),
        "enterprise_fit": str(business.subscores.get("enterprise_fit", 5)),
        "fde_training": str(business.subscores.get("fde_training", 5)),
        "service_extensibility": str(business.subscores.get("service_extensibility", 5)),
        "workflow_integration": str(business.subscores.get("workflow_integration", 5)),
        "risk_controllability": str(business.subscores.get("risk_controllability", 5)),
        # ── Layer 3: Platform Fit Scores ──
        "platform_xhs": str(platform.xiaohongshu),
        "platform_douyin": str(platform.douyin),
        "platform_videohao": str(platform.videohao),
        "platform_wechat": str(platform.wechat),
        "platform_geo": str(platform.geo_trade),
        "platform_best": platform.best_platform,
        "geo_verdict": platform.geo_verdict,
        # ── Layer 4: Risk Profile ──
        "risk_overall": risk_profile.overall,
        "risk_blocked": str(risk_profile.blocked),
        "risk_warnings": risk_profile.warnings,
        "risk_disclaimers": risk_profile.must_include_disclaimers,
        "risk_license": risk_profile.license_risk,
        "risk_data_privacy": risk_profile.data_privacy_risk,
        "risk_account_auto": risk_profile.account_automation_risk,
        "risk_scraping": risk_profile.scraping_platform_risk,
        "risk_deepfake": risk_profile.deepfake_impersonation_risk,
        "risk_spam": risk_profile.spam_phishing_malware_risk,
        "risk_hype": risk_profile.hype_risk,
        "risk_misuse": risk_profile.client_misuse_risk,
        "risk_license_detail": risk_profile.license_detail,
        # ── Legacy ──
        "content_type": content_type,
        "risk_level": repo.risk_level or ("high" if is_risk else "none"),
        "is_high_risk": str(is_risk),
        "risk_hits": ", ".join(risk_hits) if risk_hits else "无",
        "ai_evidence": ", ".join(ai_evidence) if ai_evidence else "暂无",
        "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# File generators (no-LLM fallback mode)
# ═════════════════════════════════════════════════════════════════════════════

def _gen_00_snapshot(ctx: dict) -> str:
    """Generate repo snapshot with all 4 score layers (research brief mode)."""
    return f"""# {ctx['full_name']} — Repo Snapshot

{RESEARCH_BRIEF_HEADER}

## 基本信息

| 字段 | 值 |
|------|----|
| 项目名 | [{ctx['full_name']}]({ctx['url']}) |
| 描述 | {ctx['description']} |
| Stars | {ctx['stars']} |
| Forks | {ctx['forks']} |
| 语言 | {ctx['language']} |
| Topics | {ctx['topics']} |
| 许可证 | {ctx['license']} |
| 最近更新 | {ctx['updated_at']} |
| 贡献者数 | {ctx['contributors_count']} |

## 分类 & 风险

| 字段 | 值 |
|------|----|
| Content Type | {ctx['content_type']} |
| Risk Level | {ctx['risk_level']} |
| High Risk Flags | {ctx['risk_hits']} |
| AI 相关性证据 | {ctx['ai_evidence']} |

## Layer 1 — 选题评分 (Repo Selection Score)

**{ctx['selection_score']} / 100**

| 维度 | 分数 (max) |
|------|-----------|
| AI 相关性 | {ctx['selection_subscores'].get('ai_relevance', '-')} / 20 |
| 近期活跃度 | {ctx['selection_subscores'].get('recency', '-')} / 15 |
| 项目清晰度 | {ctx['selection_subscores'].get('clarity', '-')} / 15 |
| 可运行/可展示 | {ctx['selection_subscores'].get('runnability', '-')} / 15 |
| 内容可讲性 | {ctx['selection_subscores'].get('tellability', '-')} / 15 |
| 社区信号 | {ctx['selection_subscores'].get('community', '-')} / 10 |
| 风险可控性 | {ctx['selection_subscores'].get('risk_controllable', '-')} / 10 |

## Layer 2 — 商业价值评分 (Business Value Score)

**{ctx['business_score']} / 100**

| 维度 | 分数 (0-10) |
|------|------------|
| 普通人理解成本 | {ctx['understandability']} |
| 企业落地场景 | {ctx['enterprise_fit']} |
| AI-FDE 训练价值 | {ctx['fde_training']} |
| 商业服务延展 | {ctx['service_extensibility']} |
| 业务流程结合度 | {ctx['workflow_integration']} |
| 风险可控性 | {ctx['risk_controllability']} |

> {ctx['business_summary']}

## Layer 3 — 平台适配评分 (Platform Fit Score)

| 平台 | 分数 (0-100) |
|------|-------------|
| 小红书 | {ctx['platform_xhs']} |
| 抖音 | {ctx['platform_douyin']} |
| 视频号 | {ctx['platform_videohao']} |
| 公众号 | {ctx['platform_wechat']} |
| 外贸/GEO | {ctx['platform_geo']} |
| **最佳平台** | **{ctx['platform_best']}** |

> GEO 判断：{ctx['geo_verdict']}

## Layer 4 — 风险画像 (Risk Profile)

| 维度 | 等级 |
|------|------|
| 综合风险 | **{ctx['risk_overall']}** |
| 许可证风险 | {ctx['risk_license']} |
| 数据隐私 | {ctx['risk_data_privacy']} |
| 账号自动化 | {ctx['risk_account_auto']} |
| 爬虫/平台规则 | {ctx['risk_scraping']} |
| 深伪/冒充 | {ctx['risk_deepfake']} |
| 垃圾/钓鱼 | {ctx['risk_spam']} |
| 夸大宣传 | {ctx['risk_hype']} |
| 客户端滥用 | {ctx['risk_misuse']} |

## README 摘要

```
{ctx['readme_excerpt'][:2000]}
```

---

*生成时间：{ctx['now']}*
*模式：No-LLM（规则生成）*
"""


def _gen_01_fde_analysis(ctx: dict) -> str:
    """Research brief: AI-FDE deep analysis with rule-filled data, no TODOs."""
    b = _build_research_brief_sections(ctx)
    return f"""# {ctx['full_name']} — AI-FDE 深度分析（研究简报）

{RESEARCH_BRIEF_HEADER}

## 一句话概述

{b['one_liner']}

> {ctx['name']} 是一个开源的 AI 相关项目，⭐ {ctx['stars']} stars，使用 {ctx['language']} 开发。

## 项目解决的问题

{b['problem_solved']}

## 目标用户

{b['target_audience']}

## 核心功能

{b['core_features']}

AI 相关性证据：{ctx['ai_evidence']}

## AI-FDE 视角拆解

| F (功能创新) | {ctx['name']} 在 {ctx['language']} 技术栈上提供了 {ctx['description'][:80]} 等能力。具体创新点需人工从 README 中提取。 |
| D (差异化) | {b['comparison'][:120]} |
| E (生态价值) | 对中文开发者和 AI 生态的实际价值需结合安装量、社区活跃度、被依赖程度判断。 |

AI-FDE 训练价值评分：{ctx['fde_training']} / 10

## 企业落地

企业落地场景评分：{ctx['enterprise_fit']} / 10
商业延展性评分：{ctx['service_extensibility']} / 10
风险可控性评分：{ctx['risk_controllability']} / 10

## 潜在风险

{b['potential_risks']}

## 商业价值总分：{ctx['business_score']} / 100

---

*生成时间：{ctx['now']}*
*模式：structured_fallback — 规则生成研究简报*
"""


def _gen_02_xiaohongshu(ctx: dict) -> str:
    """Research brief: Xiaohongshu content with platform analysis, no TODOs."""
    b = _build_research_brief_sections(ctx)
    xhs_score = ctx.get('platform_xhs', 'N/A')
    return f"""# {ctx['name']} — 小红书内容（研究简报）

{RESEARCH_BRIEF_HEADER}

## 平台适配评分

小红书适配度：**{xhs_score} / 100**

## 项目信息

- 项目：{ctx['full_name']}
- ⭐ {ctx['stars']} | {ctx['language']} | 许可证：{ctx['license']}
- {b['one_liner']}

## 标题方案（3 个，规则生成）

1. 拆解 {ctx['name']}：{b['one_liner'][:40]}...
2. GitHub {ctx['stars']} stars 的 {ctx['language']} 开源工具，解决什么问题？
3. 今天拆了一个 AI 开源项目：{ctx['name']}，适合什么场景？

## 为什么适合/不适合小红书

- 视觉吸引力：{'高 — 项目有 demo/截图/示例' if ctx.get('platform_xhs', '0') > '70' else '中 — 需要自行设计视觉卡片'}
- 收藏价值：{'高 — 实用工具类，有可复用的方法论' if ctx.get('platform_xhs', '0') > '60' else '中 — 适合做知识科普'}
- 小白友好度：{'高' if float(ctx.get('understandability', '5')) > 7 else '中 — 需要额外解释技术概念'}

## 写作角度建议

{b['human_writing_prompt']}

## 标签建议

`#AI工具` `#{ctx['language']}` `#开源项目` `#效率提升` `#AI学习笔记`

## 可复制给 LLM 的二次生成 Prompt

```
{b['reusable_llm_prompt']}
要求输出 6 张小红书图文卡片（钩子→是什么→能干什么→怎么用→启发→总结），600-800 字，小白能懂，有收藏价值，不夸大不卖焦虑。
```

---

*生成时间：{ctx['now']}*
*模式：structured_fallback — 规则生成研究简报*
"""


def _gen_03_douyin(ctx: dict) -> str:
    """Research brief: Douyin video script with platform analysis, no TODOs."""
    b = _build_research_brief_sections(ctx)
    return f"""# {ctx['name']} — 抖音视频（研究简报）

{RESEARCH_BRIEF_HEADER}

## 平台适配
- 抖音适配度：{ctx.get('platform_douyin', 'N/A')} / 100
- 项目：{ctx['full_name']} | ⭐ {ctx['stars']} | {ctx['language']}
- 一句话：{b['one_liner'][:100]}

## 前 3 秒钩子建议
"{ctx['name']}：{b['one_liner'][:60]}"
提示：用具体数字（{ctx['stars']} stars）或反常识点开头，避免"今天给大家推荐一个工具"。

## 60 秒口播结构
- 0-3s：钩子（用一句话制造好奇心）
- 3-15s：这个项目是什么（不超过 2 句话）
- 15-35s：能解决什么具体问题（1-2 个场景）
- 35-50s：同类对比 + 风险提醒
- 50-60s：结尾引导（点赞/关注/评论区）

## 核心功能（可做视觉素材）
{b['core_features']}

## 可复制给 LLM 的二次生成 Prompt

```
{b['reusable_llm_prompt']}
要求输出 60 秒抖音口播稿，含时间轴，前 3 秒强钩子，口语化，不夸大。
```

---

*生成时间：{ctx['now']}*
*模式：structured_fallback*
"""


def _gen_04_videohao(ctx: dict) -> str:
    """Research brief: VideoHao script with platform analysis, no TODOs."""
    b = _build_research_brief_sections(ctx)
    return f"""# {ctx['name']} — 视频号（研究简报）

{RESEARCH_BRIEF_HEADER}

## 平台适配
- 视频号适配度：{ctx.get('platform_videohao', 'N/A')} / 100
- 项目：{ctx['full_name']} | ⭐ {ctx['stars']} | {ctx['language']}
- 一句话：{b['one_liner'][:100]}

## 企业视角开场建议
"今天拆一个 {ctx['language']} 开源项目 {ctx['name']}，它能帮企业解决..."

## 90 秒口播结构（企业决策者向）
- 0-15s：从企业痛点切入（不堆技术术语）
- 15-45s：3 个落地价值点（降本/增效/竞争力）
- 45-75s：落地条件和风险
- 75-90s：下一步行动建议

## 企业相关数据
- 企业落地评分：{ctx['enterprise_fit']} / 10
- 商业延展性：{ctx['service_extensibility']} / 10

## 可复制给 LLM 的二次生成 Prompt

```
{b['reusable_llm_prompt']}
要求输出 90 秒视频号口播稿，面向企业决策者，稳重专业，强调落地价值，不提技术细节。
```

---

*生成时间：{ctx['now']}*
*模式：structured_fallback*
"""


def _gen_05_wechat(ctx: dict) -> str:
    """Research brief: WeChat article with complete 10-item research brief, no TODOs."""
    b = _build_research_brief_sections(ctx)
    return f"""# {ctx['name']} — 公众号文章（研究简报）

{RESEARCH_BRIEF_HEADER}

## 项目基本信息

| 字段 | 值 |
|------|----|
| 项目 | [{ctx['full_name']}]({ctx['url']}) |
| ⭐ Stars | {ctx['stars']} |
| 语言 | {ctx['language']} |
| 许可证 | {ctx['license']} |
| 最近更新 | {ctx['updated_at']} |

## 1. 项目一句话解释

{b['one_liner']}

## 2. 项目解决的问题

{b['problem_solved']}

## 3. 目标用户

{b['target_audience']}

## 4. 核心功能列表

{b['core_features']}

## 5. 为什么值得关注

{b['why_worth_attention']}

选题评分：{ctx['selection_score']} / 100 | 商业价值：{ctx['business_score']} / 100

## 6. 和同类项目的区别

{b['comparison']}

## 7. 潜在风险

{b['potential_risks']}

风险可控性评分：{ctx['risk_controllability']} / 10

## 8. 适合平台

{b['suitable_platforms']}

最佳平台：**{ctx['platform_best']}**

## 9. 人工写作提示词

{b['human_writing_prompt']}

理解成本评分：{ctx['understandability']} / 10
企业落地评分：{ctx['enterprise_fit']} / 10

## 10. 可复制给 LLM 的二次生成 Prompt

```
{b['reusable_llm_prompt']}
要求输出 1200-2000 字公众号长文，以「我今天拆了一个项目」的学习视角，分 7 段（为什么值得看→项目是什么→怎么理解→企业场景→AI-FDE 拆解→风险→学习收获），不写软文不卖课，诚实标注风险边界。
```

## 文章结构建议

1. **为什么这个项目值得看**（200-300 字）：用评分数据 + 一句话引出
2. **项目是什么**（300-400 字）：从 {b['one_liner'][:60]} 展开
3. **普通人怎么理解**（200-300 字）：用类比解释 {ctx['name']}
4. **企业场景**（300-400 字）：对应的商业落地可能性
5. **AI-FDE 视角**（200-300 字）：从功能创新/差异化/生态价值三维拆解
6. **落地风险**（150-200 字）：诚实标注边界
7. **我的学习收获**（150-200 字）：个人成长视角

---

*生成时间：{ctx['now']}*
*模式：structured_fallback — 规则生成研究简报*
"""


def _gen_06_storyboard(ctx: dict) -> str:
    """Research brief: Storyboard with shot structure framework, no TODOs."""
    b = _build_research_brief_sections(ctx)
    return f"""# {ctx['name']} — 分镜脚本框架（研究简报）

{RESEARCH_BRIEF_HEADER}

## 项目信息
- {ctx['full_name']}
- ⭐ {ctx['stars']} | {ctx['language']}
- {b['one_liner'][:120]}

## 分镜结构（6 镜 × 35 秒）

| 镜号 | 时长 | 主题 | 视觉建议 |
|------|------|------|----------|
| 1 | 3s | 钩子 | 项目名大字 + 一句话钩子：「{b['one_liner'][:50]}」 |
| 2 | 8s | 输入→输出 | 数据流图/架构图，展示 {ctx['name']} 的核心工作流 |
| 3 | 8s | 企业场景 | {b['target_audience'][:40]} 的使用场景示意 |
| 4 | 8s | AI 能力 | 标签云：{b['core_features'][:60]} |
| 5 | 5s | 风险边界 | 风险清单 + 免责声明：「{b['potential_risks'][:60]}」 |
| 6 | 3s | 评分 | 商业价值 {ctx['business_score']}/100 仪表盘 + 引导关注 |

## 视觉风格
- 白底蓝图工程风
- 不全局抖动，只做局部动效
- 中文字幕，底部 1/3 区域

## 可复制给 LLM 的二次生成 Prompt

```
{b['reusable_llm_prompt']}
要求输出 6 镜头分镜脚本（9:16 竖屏），白底蓝图工程风，每镜含标题区/主体区/字幕区/动效说明。
```

---

*生成时间：{ctx['now']}*
*模式：structured_fallback*
"""


def _gen_07_geo(ctx: dict) -> str:
    """Research brief: GEO angle analysis — honest about fit, no forced GEO."""
    text = f"{ctx.get('name', '')} {ctx.get('description', '')} {ctx.get('topics', '')}".lower()
    has_geo = any(k in text for k in ("geo", "seo", "外贸", "ai-search", "search"))
    has_auto = any(k in text for k in ("automation", "workflow", "n8n", "dify"))

    if has_geo or has_auto:
        verdict = "**可以结合** — 该项目与外贸/GEO/AI搜索可见性有明确交集"
        details = []
        if has_geo:
            details.append("- 项目直接关联 GEO/SEO 话题，可产出外贸内容")
        if has_auto:
            details.append("- 项目的自动化能力可转化为外贸工作流方案")
        can_use = "\n".join(details) if details else "- 需要进一步分析具体结合方式"
        geo_recommend = "可以尝试制作 GEO/外贸角度内容，但需要人工补充具体的外贸场景案例。"
    else:
        verdict = "**不建议硬蹭** — 该项目与外贸/GEO/AI搜索可见性没有明显交集"
        can_use = "- 如果强行结合，会让内容显得生硬，反而降低账号可信度。建议放弃 GEO 角度，聚焦项目本身的技术或应用价值。"
        geo_recommend = "不建议从 GEO/外贸角度切入。建议选择更匹配的平台（如公众号、小红书）来制作内容。"

    return f"""# {ctx['name']} — 外贸 / GEO 角度分析（研究简报）

{RESEARCH_BRIEF_HEADER}

## 结合判断

{verdict}

## GEO 适配度分析

- GEO/SEO 关联：{'是' if has_geo else '否'}
- 自动化关联：{'是' if has_auto else '否'}
- 企业落地评分：{ctx['enterprise_fit']} / 10
- 平台 GEO 评分：{ctx.get('platform_geo', 'N/A')} / 100

{can_use}

## 建议

{geo_recommend}

## 可复制给 LLM 的二次生成 Prompt

```
外贸/GEO 角度分析开源项目 {ctx['full_name']}（{ctx['description']}，{ctx['stars']} stars）。
{'该项目与 GEO/外贸有交集。' if has_geo or has_auto else '该项目与 GEO/外贸无明显交集，不建议硬蹭。'}
请从外贸客户使用场景、GEO 服务商借鉴角度、商业服务切入点三维度分析。
```

---

*生成时间：{ctx['now']}*
*模式：structured_fallback*
"""


def _gen_08_enterprise_pitch(ctx: dict) -> str:
    """Research brief: Enterprise pitch with business evidence, no TODOs."""
    b = _build_research_brief_sections(ctx)
    return f"""# {ctx['name']} — 企业宣讲（研究简报）

{RESEARCH_BRIEF_HEADER}

## 项目背景
- {ctx['full_name']}
- ⭐ {ctx['stars']} | {ctx['language']} | 许可证：{ctx['license']}
- 企业落地评分：{ctx['enterprise_fit']} / 10
- 商业价值总分：{ctx['business_score']} / 100

## 版本一：老板版素材（降本增效视角）

核心卖点：{b['problem_solved'][:150]}
目标场景：{b['target_audience']}
关键问题：
- 这个工具能让团队省多少时间？（需人工评估）
- 和现有系统怎么配合？（技术栈：{ctx['language']}）
- 投入和产出比大概多少？（取决于部署规模和场景）

## 版本二：技术版素材（架构与风险视角）

技术栈：{ctx['language']} / Topics: {ctx['topics']}
核心竞争力：{b['comparison'][:150]}
关键问题：
- 与现有技术栈的兼容性（{ctx['language']} 生态）
- 部署和维护成本（许可证：{ctx['license']}）
- 潜在风险：{b['potential_risks'][:120]}

## 版本三：客户版素材（结果和体验视角）

核心价值：{b['one_liner'][:150]}
关键问题：
- 最终用户能看到什么变化？（取决于具体应用场景）
- 比不用这个工具好在哪里？（效率提升/质量提升/成本降低）
- 学习成本多高？（理解成本评分：{ctx['understandability']}/10）

## 可复制给 LLM 的二次生成 Prompt

```
{b['reusable_llm_prompt']}
请生成三个版本的企业宣讲稿：老板版（ROI语言，200-300字）、技术版（架构语言，200-300字）、客户版（结果语言，200-300字）。
```

---

*生成时间：{ctx['now']}*
*模式：structured_fallback*
"""


def _gen_09_risk_review(ctx: dict) -> str:
    """Generate risk review using new risk_score.py profile."""
    risk_overall = ctx.get("risk_overall", "low")
    risk_blocked = ctx.get("risk_blocked", "False") == "True"

    # License risk
    license_detail = ctx.get("risk_license_detail", "")
    if not license_detail:
        license_str = ctx.get("license", "未指定")
        if not license_str or license_str == "未指定":
            license_risk = "⚠️ **中风险** — 未指定许可证，商用前需确认版权归属"
        elif license_str in ("MIT", "Apache-2.0", "BSD-3-Clause", "Unlicense"):
            license_risk = f"✅ **低风险** — {license_str} 是宽松开源许可证"
        elif license_str in ("GPL-3.0", "GPL-2.0", "AGPL-3.0"):
            license_risk = f"⚠️ **中风险** — {license_str} 有 Copyleft 限制，商用需评估"
        else:
            license_risk = f"⚠️ 需确认 — {license_str}，请阅读完整条款"
    else:
        license_risk = license_detail

    # Per-category risks from risk_score.py
    def _label(level: str) -> str:
        return {"low": "✅ 低风险", "medium": "⚠️ 中风险", "high": "🔴 高风险"}.get(level, "⚪ 未知")

    warnings = ctx.get("risk_warnings", [])
    disclaimers = ctx.get("risk_disclaimers", [])

    warning_lines = "\n".join(f"- {w}" for w in warnings) if warnings else "- 未检测到具体风险信号"
    disclaimer_lines = "\n".join(f"- {d}" for d in disclaimers) if disclaimers else "- 无需额外免责声明"

    if risk_blocked:
        recommend = "❌ **禁止发布** — 属于高风险项目类型，不推荐作为任何选题"
        reason = "项目匹配了 blocked 关键词，存在严重的合规/道德风险"
    elif risk_overall == "high":
        recommend = "⚠️ **谨慎发布** — 风险较高，需要添加充分的边界提醒"
        reason = "综合风险评估为 high"
    elif risk_overall == "medium":
        recommend = "⚠️ **可发布但需注意** — 存在一定风险，需添加边界提醒"
        reason = "综合风险评估为 medium"
    else:
        recommend = "✅ **可以发布** — 风险可控"
        reason = "综合风险评估为 low"

    return f"""# {ctx['name']} — 风险审查

> 基于 8 维度风险评估（risk_score.py v4）

## 综合风险

**{risk_overall.upper()}** — {reason}

## License 风险

{license_risk}

## 8 维度风险详情

| 维度 | 等级 |
|------|------|
| 数据隐私 | {_label(ctx.get('risk_data_privacy', 'low'))} |
| 账号自动化 | {_label(ctx.get('risk_account_auto', 'low'))} |
| 爬虫/平台规则 | {_label(ctx.get('risk_scraping', 'low'))} |
| 深伪/冒充 | {_label(ctx.get('risk_deepfake', 'low'))} |
| 垃圾/钓鱼/恶意 | {_label(ctx.get('risk_spam', 'low'))} |
| 夸大宣传 | {_label(ctx.get('risk_hype', 'low'))} |
| 客户端滥用 | {_label(ctx.get('risk_misuse', 'low'))} |

## 风险警告

{warning_lines}

## 是否建议发布

{recommend}

## 必须加的边界提醒

{disclaimer_lines}
- 本项目基于公开的 GitHub 仓库信息分析，不构成投资或商业建议
- 使用前请自行验证项目的安全性、合规性和功能完整性
- 如果涉及 API Key 或用户数据，务必阅读项目的安全文档

---

*生成时间：{ctx['now']}*
"""


def _no_llm_quality_check(ctx: dict) -> str:
    """Structured fallback quality check — honest about LLM unavailability."""
    b = _build_research_brief_sections(ctx)
    return f"""# 发布前质量检查报告

**项目**：{ctx['full_name']}
**检查时间**：{ctx['now']}

---

## 0. 生成模式

- **llm_status**: unavailable
- **content_mode**: structured_fallback
- **publishable**: no
- **推荐发布**: revise_first
- **阻断数**: 0 (无 TODO，但内容为规则生成)
- **需人工审核**: yes
- **缺失段落**: 所有需要 LLM 写作的内容段落
- **不可发布原因**: LLM API 不可用，内容为规则自动生成的研究简报，不是可发布文章

---

## 1. 总结结论

- **是否建议发布**：🔴 不建议 — LLM 不可用，内容为研究简报
- **总分**：≤75 / 100 (structured_fallback 上限)
- **内容质量**：规则数据准确，但缺少 AI 写作的叙事逻辑和表现力
- **发布前必须**：使用 LLM 模式重新生成，或基于研究简报人工写作

---

## 2. 素材完整度

| 项目 | 状态 |
|------|------|
| 项目一句话解释 | ✅ {b['one_liner'][:60]} |
| 项目解决的问题 | ✅ 已提供 |
| 目标用户 | ✅ {b['target_audience'][:40]} |
| 核心功能 | ✅ {b['core_features'][:60]} |
| 为什么值得关注 | ✅ 已提供 |
| 同类项目对比 | ✅ 已提供 |
| 潜在风险 | ✅ 已提供 |
| 适合平台 | ✅ {b['suitable_platforms'][:60]} |
| 人工写作提示词 | ✅ 已提供 |
| LLM 二次生成 Prompt | ✅ 已提供 |

---

## 3. 发布建议

- **小红书**：❌ 不建议（需人工补写完整 6 张卡片文案）
- **公众号**：❌ 不建议（需人工补写 1200-2000 字长文）
- **视频号**：❌ 不建议（需人工补写完整口播稿）
- **外贸/GEO**：❌ 不建议
- 是否需要人工补充观点：是（所有内容段落均需人工写作或 LLM 重新生成）

---

## 4. 下一步

1. 如果 LLM 恢复：运行 `python run.py content {ctx['full_name']}` 重新生成完整内容包
2. 如果需要人工写：打开 `05_wechat_article.md`，使用研究简报中的 10 项素材在 30 分钟内补写
3. 人工写完后：通读确认无夸大表述、无虚假信息、有风险边界提醒

---

## 5. 最终结论

**需人工改稿** — LLM 不可用，当前为研究简报模式。素材完整可供人工 30 分钟内补写，但不能直接发布。

---

*生成时间：{ctx['now']}*
*模式：structured_fallback*
"""


def _gen_10_quality_check(ctx: dict) -> str:
    """Generate quality check report with llm_status/content_mode/publishable fields."""
    no_llm_override = ctx.get("no_llm")
    if no_llm_override:
        return _no_llm_quality_check(ctx)

    llm_available, llm_mode, _ = _check_llm_health(timeout=10)

    if not llm_available:
        return _no_llm_quality_check(ctx)

    return f"""# 发布前质量检查报告

**项目**：{ctx['full_name']}
**检查时间**：{ctx['now']}

---

## 0. 生成模式

- **llm_status**: available
- **content_mode**: full_llm
- **publishable**: pending (待 reviewer 管线确认)
- **推荐发布**: pending
- **阻断数**: 0
- **需人工审核**: yes (建议通读所有文件)
- **缺失段落**: 无

---

## 1. 总结结论

LLM 可用，完整内容已生成。请通读所有文件确认质量后发布。

---

*生成时间：{ctx['now']}*
*模式：full_llm*
"""


# ═════════════════════════════════════════════════════════════════════════════
# Content pack generator
# ═════════════════════════════════════════════════════════════════════════════

def _get_generator(file_name: str):
    """Map file name to its no-LLM generator function."""
    generators = {
        "00_repo_snapshot": _gen_00_snapshot,
        "01_ai_fde_deep_analysis": _gen_01_fde_analysis,
        "02_xiaohongshu": _gen_02_xiaohongshu,
        "03_douyin_video": _gen_03_douyin,
        "04_videohao_script": _gen_04_videohao,
        "05_wechat_article": _gen_05_wechat,
        "06_storyboard": _gen_06_storyboard,
        "07_geo_angle": _gen_07_geo,
        "08_enterprise_pitch": _gen_08_enterprise_pitch,
        "09_risk_review": _gen_09_risk_review,
        "10_quality_check": _gen_10_quality_check,
    }
    return generators.get(file_name)


import time

def _try_generate_file(
    file_name: str, scored: ScoredRepo, ctx: dict, llm_available: bool,
    max_retries: int = 3, retry_delay: float = 2.0,
) -> tuple[str, bool]:
    """Generate a single content file with retry logic.

    Returns (content, is_degraded). On total failure, content is an error
    placeholder with source_status=degraded marker.

    Missing templates are detected early and logged specifically.
    """
    from pathlib import Path as _Path
    _templates_dir = _Path(__file__).resolve().parent.parent / "templates"
    actual_template = CONTENT_PACK_TEMPLATE_MAP.get(file_name, file_name)
    template_path = _templates_dir / f"{actual_template}.md"
    template_missing = not template_path.exists()

    if template_missing and llm_available:
        # Cannot generate via LLM without template — skip retries
        from datetime import datetime as _dt
        degraded_content = (
            f"# {file_name}\n\n"
            f"> **source_status: degraded — missing_template**\n"
            f"> 模板文件 `templates/{actual_template}.md` 不存在，无法生成\n"
            f"> 生成时间: {_dt.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"[TODO: 创建 templates/{actual_template}.md 模板文件]\n"
        )
        return degraded_content, True

    last_error = None
    for attempt in range(max_retries):
        try:
            content = ""
            if llm_available:
                from .analyzer import generate_content as llm_generate
                content = llm_generate(scored, file_name, ctx=ctx)
                if not content or not content.strip():
                    gen_func = _get_generator(file_name)
                    content = gen_func(ctx) if gen_func else f"# {file_name}\n\n[TODO: LLM生成空内容，需手动补充]\n"
            else:
                gen_func = _get_generator(file_name)
                if gen_func:
                    content = gen_func(ctx)
                else:
                    content = f"# {file_name}\n\n[TODO: 需要配置 LLM_API_KEY 生成完整内容]\n"

            if content.strip():
                return content, False
            else:
                last_error = ValueError("empty content")
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.info("Retry %d/%d for %s: %s", attempt + 1, max_retries, file_name, e)
                time.sleep(retry_delay * (attempt + 1))  # exponential backoff
            else:
                logger.warning("All %d retries exhausted for %s: %s", max_retries, file_name, e)

    # All retries exhausted — degraded content
    from datetime import datetime as dt_local
    degraded_content = (
        f"# {file_name}\n\n"
        f"> **source_status: degraded** — 生成经 {max_retries} 次重试后仍失败\n"
        f"> 最后错误: {last_error}\n"
        f"> 生成时间: {dt_local.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"[TODO: 手动补充此文件内容]\n"
    )
    return degraded_content, True


def generate_content_pack(
    repo_full_name: str, output_dir: Path | None = None,
    max_retries: int = 3, timeout_seconds: float = 120.0,
    dry_run: bool = False,
) -> tuple[Path, str]:
    """Generate a complete V2 content pack for a repo (Phase 7: retry + degraded).

    1. Enrich repo metadata from GitHub API
    2. Score the repo (rules + business value)
    3. Generate 11 content files (LLM or no-LLM fallback) with retry
    4. Write results to {output_dir}/{slug}/
    5. Mark repo as generated in state

    If dry_run=True: no LLM calls, no file writes — estimate only.
    Returns (pack_dir, status) where status is "ok", "degraded", or "failed".
    """
    import signal

    if output_dir is None:
        output_dir = CONTENT_PACKS_DIR

    # 1. Enrich
    enriched = enrich_repo(repo_full_name)
    if enriched is None:
        raise ValueError(f"无法获取仓库信息：{repo_full_name}")

    # 2. Score (rules + classification)
    scored = score_repo(enriched)
    scored.content_type = classify_content_type(scored)
    is_risk, risk_hits = check_high_risk(scored)
    scored.risk_level = "high" if is_risk else "none"
    _, scored.ai_evidence = check_ai_eligibility(scored)

    # 2.5. Risk gate — refuse to generate content for blocked/high-risk repos
    if is_risk or scored.risk_level == "high":
        slug = slugify_repo_name(repo_full_name)
        pack_dir = output_dir / slug
        logger.warning(
            "BLOCKED %s: high-risk project (%s)",
            repo_full_name, ", ".join(risk_hits[:3]),
        )
        # Write a minimal rejection notice instead of full content pack
        pack_dir.mkdir(parents=True, exist_ok=True)
        rejection_path = pack_dir / "00_REJECTED.md"
        rejection_path.write_text(
            f"# ⛔ 内容生成已拒绝\n\n"
            f"**项目**：{repo_full_name}\n"
            f"**原因**：高风险项目 — {', '.join(risk_hits[:5])}\n"
            f"**风险等级**：high / blocked\n\n"
            f"根据系统安全策略，不对高风险项目（deepfake/phishing/malware等）生成发布内容。\n",
            encoding="utf-8",
        )
        return pack_dir, "blocked"

    # 3. Build context
    ctx = _build_repo_context(scored)

    # Determine project type for boundary-driven reviewer checks
    from .reviewer import classify_project_type as _classify_project_type
    ctx["project_type"] = _classify_project_type(
        repo_full_name=repo_full_name,
        topics=scored.topics,
        description=scored.description or "",
        ctx=ctx,
    )

    # 4. Dry-run early return — no LLM, no file writes
    if dry_run:
        slug = slugify_repo_name(repo_full_name)
        pack_dir = output_dir / slug
        llm_available = _has_llm()
        mode = "LLM" if llm_available else "No-LLM"
        logger.info("Dry-run: would generate %d files in %s mode for %s",
                     len(CONTENT_FILES_V2), mode, repo_full_name)
        return pack_dir, "ok"

    # 4. Prepare output directory
    slug = slugify_repo_name(repo_full_name)
    pack_dir = output_dir / slug

    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)

    # 5. Check LLM availability — actual health check, not just key existence
    llm_available, llm_mode, llm_statuses = _check_llm_health(timeout=10)
    mode_label = "full_llm" if llm_available else "structured_fallback"
    logger.info("Content pack mode: %s (retries=%d, timeout=%ds)", mode_label, max_retries, timeout_seconds)
    if not llm_available and llm_statuses:
        for s in llm_statuses:
            logger.warning("LLM provider %s: %s", s["provider"],
                           "available" if s["available"] else f"unavailable ({s['error']})")

    # 6. Generate content with retry + reviewer pipeline per file
    generated_types = []
    degraded_files = []
    failed_files = []
    reviewer_regenerated: dict[str, int] = {}  # file_name → regeneration attempts

    # Files that get full reviewer scrutiny (long-form content)
    REVIEWER_CONTENT_FILES = {
        "01_ai_fde_deep_analysis", "02_xiaohongshu", "05_wechat_article", "07_geo_angle",
    }
    # Files that get light reviewer (exaggerated claims only, no disclaimer requirement)
    REVIEWER_LIGHT_FILES = {
        "03_douyin_video", "04_videohao_script",
    }

    # Only run reviewer pipeline when LLM is available
    _reviewer_available = False
    if llm_available:
        try:
            from . import reviewer  # noqa: F811
            _reviewer_available = True
        except ImportError:
            logger.warning("Reviewer module not available, skipping post-generation checks")

    for file_name in CONTENT_FILES_V2:
        try:
            content, is_degraded = _try_generate_file(
                file_name, scored, ctx, llm_available,
                max_retries=max_retries,
            )

            # ── Reviewer pipeline (LLM mode, content files only) ──
            if llm_available and _reviewer_available and not is_degraded:
                is_content_file = file_name in REVIEWER_CONTENT_FILES
                is_light_file = file_name in REVIEWER_LIGHT_FILES

                if is_content_file or is_light_file:
                    outcome = reviewer.run_reviewer_pipeline(
                        file_name, content, repo_full_name, ctx=ctx,
                        project_type=ctx.get("project_type", "generic"),
                        strict_mode=is_content_file,
                    )

                    if outcome.needs_regeneration:
                        logger.warning(
                            "Reviewer: %s core checks failed (%s), regenerating...",
                            file_name, ", ".join(outcome.core_checks_failed),
                        )
                        # Regenerate once
                        reviewer_regenerated[file_name] = 1
                        content2, degraded2 = _try_generate_file(
                            file_name, scored, ctx, llm_available,
                            max_retries=1,
                        )
                        if not degraded2:
                            outcome2 = reviewer.run_reviewer_pipeline(
                                file_name, content2, repo_full_name, ctx=ctx,
                                project_type=ctx.get("project_type", "generic"),
                                strict_mode=is_content_file,
                            )
                            if outcome2.passed:
                                content = content2
                                logger.info("Reviewer: %s passed on regeneration", file_name)
                            else:
                                logger.warning(
                                    "Reviewer: %s still failing after regeneration — %s",
                                    file_name, ", ".join(outcome2.core_checks_failed),
                                )
                                is_degraded = True
                        else:
                            is_degraded = True

            filepath = pack_dir / f"{file_name}.md"
            filepath.write_text(content, encoding="utf-8")

            if is_degraded:
                degraded_files.append(file_name)
                logger.warning("Degraded %s for %s", file_name, repo_full_name)
            else:
                generated_types.append(file_name)
                logger.info("Generated %s for %s (%s)", file_name, repo_full_name, mode_label)
        except Exception as e:
            logger.error("Failed %s for %s: %s", file_name, repo_full_name, e)
            failed_files.append(file_name)

    # 7. Run comprehensive quality review and write 10_quality_check.md
    quality_report = None
    requires_manual_review = False
    if llm_available and _reviewer_available:
        try:
            quality_report = reviewer.quality_review(pack_dir, repo_full_name, ctx=ctx)
            reviewer.write_quality_report(pack_dir, quality_report)
            logger.info(
                "Quality review: score=%d, recommendation=%s, blocking=%d",
                quality_report.overall_score,
                quality_report.publish_recommendation,
                len(quality_report.blocking_issues),
            )
            if quality_report.publish_recommendation == "no":
                requires_manual_review = True
        except Exception as e:
            logger.warning("Quality review failed: %s", e)

    # 8. Write status manifest
    # Phase 15 statuses: ok_full_llm / ok_structured_fallback / degraded / failed
    if failed_files:
        status = "failed"
    elif degraded_files:
        status = "degraded"
    elif not llm_available:
        status = "ok_structured_fallback"
    else:
        status = "ok_full_llm"

    # Phase 11: Quality status with reviewer integration
    quality_status = "ready"
    if status == "failed":
        quality_status = "degraded"
    elif status == "degraded":
        quality_status = "needs_review"
    elif requires_manual_review:
        quality_status = "needs_review"

    # Determine risk level from repo context
    risk_level = "none"
    risk_profile = ctx.get("risk_profile", {})
    if isinstance(risk_profile, dict):
        risk_overall = risk_profile.get("overall", "")
        if risk_overall in ("blocked", "high"):
            risk_level = "high"
        elif risk_overall == "medium":
            risk_level = "medium"
        elif risk_overall == "low":
            risk_level = "low"

    # Determine recommended platforms from context
    recommended_platforms = [ctx.get("platform_best", "xiaohongshu")]
    if quality_report:
        recommended_platforms = [quality_report.recommended_platform]

    # Detect missing fields
    missing_fields = []
    ctx_readme = ctx.get("readme", "")
    if not ctx_readme or len(str(ctx_readme)) < 100:
        missing_fields.append("readme_content")
    if not ctx.get("license"):
        missing_fields.append("license")
    if not ctx.get("language"):
        missing_fields.append("language")

    manifest = {
        "repo": repo_full_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": mode_label,
        "files_generated": len(generated_types),
        "files_degraded": len(degraded_files),
        "files_failed": len(failed_files),
        "generated": generated_types,
        "degraded": degraded_files,
        "failed": failed_files,
        "max_retries": max_retries,
        "timeout_seconds": timeout_seconds,
        # Phase 8 enhanced fields
        "llm_mode": "disabled" if not llm_available else ("enabled" if status == "ok" else "fallback"),
        "missing_fields": missing_fields,
        "requires_manual_review": requires_manual_review or status in ("degraded", "failed") or len(degraded_files) > 0,
        "quality_status": quality_status,
        "risk_level": risk_level,
        "recommended_platforms": recommended_platforms,
        # Phase 11: Reviewer stats
        "reviewer_regenerated": reviewer_regenerated,
        "quality_review_score": quality_report.overall_score if quality_report else None,
        "quality_review_recommendation": quality_report.publish_recommendation if quality_report else None,
    }
    manifest_path = pack_dir / "_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 9. Mark as generated
    mark_as_generated(repo_full_name, generated_types)

    return pack_dir, status
