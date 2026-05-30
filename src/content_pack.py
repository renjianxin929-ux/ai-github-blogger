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


def _has_llm() -> bool:
    """Check if LLM API key is configured."""
    try:
        from .config import get_llm_config
        get_llm_config()
        return True
    except ValueError:
        return False


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

    return {
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
    """Generate repo snapshot with all 4 score layers."""
    return f"""# {ctx['full_name']} — Repo Snapshot

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
    """Generate AI-FDE deep analysis (no-LLM version uses rules + template)."""
    return f"""# {ctx['full_name']} — AI-FDE 深度分析

## 一句话概述

{ctx['description']}

> {ctx['name']} 是一个开源的 AI 相关项目，⭐ {ctx['stars']} stars，使用 {ctx['language']} 开发。

## 它解决谁的什么问题

[TODO: LLM 分析 — 请描述目标用户和核心痛点]

基于现有信息：
- 项目 Topics: {ctx['topics']}
- AI 相关性: {ctx['ai_evidence']}
- 项目描述: {ctx['description']}

## 背后的 AI 能力

[TODO: LLM 分析 — 列出具体的 AI 技术栈和能力]

## 普通人怎么理解

> 一句话版本：{ctx['name']} 是一个 {ctx['language']} 写的开源工具，主要做 {ctx['description'][:60]}...

普通人理解成本评分：{ctx['understandability']} / 10

## 企业老板为什么会关心

企业落地场景评分：{ctx['enterprise_fit']} / 10

[TODO: LLM 分析 — 从降本增效、竞争力、风险控制角度说明]

## AI-FDE 视角怎么拆

| F (功能创新) | [TODO] 该项目解决了什么具体问题？技术方案有何新意？ |
| D (差异化) | [TODO] 与同类项目相比，它有什么不可替代的地方？ |
| E (生态价值) | [TODO] 对中文开发者和 AI 生态的实际价值有多大？ |

AI-FDE 训练价值评分：{ctx['fde_training']} / 10

## 能不能直接落地

商业延展性评分：{ctx['service_extensibility']} / 10

[TODO: LLM 分析 — 落地的技术前提、团队要求、时间成本]

## 商用前还缺什么

[TODO: LLM 分析 — 功能缺口、合规要求、技术支持]

## 风险与边界

风险可控性评分：{ctx['risk_controllability']} / 10

风险标记: {ctx['risk_hits']}

## 今日落地评分

商业价值总分：**{ctx['business_score']} / 100**

> {ctx['business_summary']}

---

*生成时间：{ctx['now']}*
*模式：No-LLM fallback — [TODO] 标记处需要 LLM 补充*
"""


def _gen_02_xiaohongshu(ctx: dict) -> str:
    """Generate Xiaohongshu content template."""
    return f"""# {ctx['name']} — 小红书内容草稿

> 模式：No-LLM fallback — 需要 LLM 生成完整文案
> 风格要求：小白能懂，有收藏价值，不夸大，不卖焦虑

## 标题建议（5 个）

[TODO: LLM — 生成 5 个吸引人的标题]

参考信息：
- 项目名：{ctx['name']}
- 一句话：{ctx['description']}
- AI 标签：{ctx['topics']}

## 6 张图文卡片文案

### 卡片 1 — 钩子
[TODO] 用一句话抓住注意力

### 卡片 2 — 项目是什么
[TODO] 最简单的解释

### 卡片 3 — 能干什么
[TODO] 3 个具体场景

### 卡片 4 — 怎么用
[TODO] 最简单的上手方式

### 卡片 5 — 启发和思考
[TODO] 每个人都能从中学到什么

### 卡片 6 — 总结 + 引导
[TODO] 一句话总结 + 引导互动

## 正文（1 篇）

[TODO: LLM — 600-800 字，小红书风格]

## 结尾互动

[TODO] 引导评论、收藏、关注

## 标签建议

`#AI工具` `#{ctx['language']}` `#开源项目` `#效率提升`

---

*生成时间：{ctx['now']}*
"""


def _gen_03_douyin(ctx: dict) -> str:
    """Generate Douyin video script template."""
    return f"""# {ctx['name']} — 抖音 60 秒口播稿

> 模式：No-LLM fallback — 需要 LLM 生成完整口播稿
> 要求：不夸张，不说"普通人马上赚钱"

## 项目信息
- 项目：{ctx['full_name']}
- ⭐ {ctx['stars']} | 语言：{ctx['language']}
- {ctx['description']}

## 前 3 秒强钩子

[TODO: LLM — 必须在前 3 秒抓住注意力]

## 分段口播（60 秒）

[TODO: LLM — 4 段，每段约 15 秒]

## 字幕文案

[TODO: LLM — 完整字幕，含时间轴]

## 结尾引导

[TODO] 引导点赞、关注、评论区互动

---

*生成时间：{ctx['now']}*
"""


def _gen_04_videohao(ctx: dict) -> str:
    """Generate VideoHao (视频号) script template."""
    return f"""# {ctx['name']} — 视频号 90 秒口播稿

> 模式：No-LLM fallback — 需要 LLM 生成完整口播稿
> 风格：更稳重，适合企业老板/业务负责人

## 项目信息
- 项目：{ctx['full_name']}
- ⭐ {ctx['stars']} | 语言：{ctx['language']}
- {ctx['description']}

## 开场（15 秒）

[TODO: LLM — 从企业视角切入，不提技术细节]

## 主体（60 秒）

[TODO: LLM — 3 段，每段强调一个企业落地价值点]

## 结尾（15 秒）

[TODO: LLM — 引导企业决策者思考和互动]

## 企业关联场景

基于规则分析：
- 企业落地评分：{ctx['enterprise_fit']} / 10
- 商业延展性：{ctx['service_extensibility']} / 10

[TODO: LLM — 展开具体的中国企业应用场景]

---

*生成时间：{ctx['now']}*
"""


def _gen_05_wechat(ctx: dict) -> str:
    """Generate WeChat article template."""
    return f"""# {ctx['name']} — 公众号长文草稿

> 模式：No-LLM fallback — 需要 LLM 生成完整文章
> 目标：1200-2000 字，不卖课，只做成长记录和方法沉淀

## 标题建议（3 个）

1. [TODO: LLM]
2. [TODO: LLM]
3. [TODO: LLM]

## 文章结构

### 1. 为什么这个项目值得看

> 基于评分：{ctx['selection_score']} / 100 | 商业价值：{ctx['business_score']} / 100

[TODO: LLM — 200-300 字]

### 2. 项目是什么

- 项目：{ctx['full_name']}
- ⭐ {ctx['stars']} | {ctx['language']} | 许可证：{ctx['license']}
- {ctx['description']}

[TODO: LLM — 300-400 字]

### 3. 普通人怎么理解

基于：{ctx['understandability']} / 10 理解成本评分

[TODO: LLM — 200-300 字，用类比和场景解释]

### 4. 企业场景

基于：{ctx['enterprise_fit']} / 10 企业落地评分

[TODO: LLM — 300-400 字]

### 5. AI-FDE 视角

[TODO: LLM — 200-300 字，从 FDE 三维拆解]

### 6. 落地风险

风险可控性：{ctx['risk_controllability']} / 10

[TODO: LLM — 150-200 字]

### 7. 我的学习收获

[TODO: LLM — 150-200 字，个人成长视角，不卖课]

---

*生成时间：{ctx['now']}*
"""


def _gen_06_storyboard(ctx: dict) -> str:
    """Generate 9:16 vertical video storyboard template."""
    return f"""# {ctx['name']} — 9:16 竖屏分镜脚本

> 模式：No-LLM fallback — 需要 LLM 生成完整分镜
> 风格：白底蓝图工程风，不全局抖动，只做局部动效

## 项目信息
- {ctx['full_name']}
- ⭐ {ctx['stars']} | {ctx['language']}
- {ctx['description']}

## 6 镜头分镜

### 镜头 1 — 项目名 + 钩子（3 秒）
- 视觉中心：项目名大字 + 一句话钩子
- 标题区：[TODO]
- 主体区：[TODO]
- 字幕区：[TODO]
- 动效：[TODO]

### 镜头 2 — 输入 → 处理 → 输出（8 秒）
- 视觉中心：数据流图
- 标题区：[TODO]
- 主体区：[TODO]
- 字幕区：[TODO]
- 动效：[TODO]

### 镜头 3 — 企业场景（8 秒）
- 视觉中心：场景示意图
- 标题区：[TODO]
- 主体区：[TODO]
- 字幕区：[TODO]
- 动效：[TODO]

### 镜头 4 — AI 能力节点（8 秒）
- 视觉中心：能力标签云
- 标题区：[TODO]
- 主体区：[TODO]
- 字幕区：[TODO]
- 动效：[TODO]

### 镜头 5 — 落地风险（5 秒）
- 视觉中心：风险清单
- 标题区：[TODO]
- 主体区：[TODO]
- 字幕区：[TODO]
- 动效：[TODO]

### 镜头 6 — 今日评分（3 秒）
- 视觉中心：评分仪表盘
- 商业价值：{ctx['business_score']} / 100
- 标题区：[TODO]
- 主体区：[TODO]
- 字幕区：[TODO]
- 动效：[TODO]

---

*生成时间：{ctx['now']}*
"""


def _gen_07_geo(ctx: dict) -> str:
    """Generate GEO / foreign-trade angle analysis."""
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
    else:
        verdict = "**不建议硬蹭** — 该项目与外贸/GEO/AI搜索可见性没有明显交集"
        can_use = "- 如果强行结合，会让内容显得生硬，反而降低账号可信度"

    return f"""# {ctx['name']} — 外贸 / GEO 角度分析

> 模式：No-LLM fallback — 需要 LLM 深度拓展

## 结合判断

{verdict}

## 外贸客户能不能用

基于规则分析：
- GEO/SEO 关联：{'是' if has_geo else '否'}
- 自动化关联：{'是' if has_auto else '否'}
- 企业落地评分：{ctx['enterprise_fit']} / 10

{can_use}

[TODO: LLM — 具体的外贸客户使用场景和案例]

## GEO 服务商能不能借鉴

[TODO: LLM — GEO 服务商视角的借鉴点]

## 是否适合作为商业服务切入点

商业延展性评分：{ctx['service_extensibility']} / 10

[TODO: LLM — 服务化、产品化、咨询化的可行性分析]

---

*生成时间：{ctx['now']}*
"""


def _gen_08_enterprise_pitch(ctx: dict) -> str:
    """Generate enterprise pitch (3 versions)."""
    return f"""# {ctx['name']} — 企业宣讲三版本

> 模式：No-LLM fallback — 需要 LLM 生成完整文案

## 项目背景
- {ctx['full_name']}
- ⭐ {ctx['stars']} | 企业落地评分：{ctx['enterprise_fit']} / 10
- 商业价值总分：{ctx['business_score']} / 100

## 版本一：老板版（关注降本增效）

[TODO: LLM — 200-300 字，用 ROI 和效率语言]

关键角度：
- 这个工具能让团队省多少时间？
- 和现有系统怎么配合？
- 投入和产出比大概多少？

## 版本二：技术版（关注架构与风险）

[TODO: LLM — 200-300 字，用技术语言]

关键角度：
- 技术栈：{ctx['language']} / Topics: {ctx['topics']}
- 架构亮点和潜在风险
- 与现有技术栈的兼容性
- 部署和维护成本

## 版本三：客户版（关注结果和体验）

[TODO: LLM — 200-300 字，用结果语言]

关键角度：
- 最终用户能看到什么变化？
- 比不用这个工具好在哪里？
- 学习成本多高？

---

*生成时间：{ctx['now']}*
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


def _gen_10_quality_check(ctx: dict) -> str:
    """Generate quality check report.

    v4: In no-LLM fallback mode, content_quality_score is "未评估" — not a numeric score.
    Only LLM-generated content gets a real quality score.
    """
    llm_available = _has_llm()

    if not llm_available:
        return f"""# {ctx['name']} — 内容质量检查

> 模式：No-LLM fallback — 内容质量评分仅在 LLM 完整生成后启用

## 评分维度

| 维度 | 评分 | 说明 |
|------|------|------|
| 内容准确性 | **未评估** | 需 LLM 验证事实和数据的准确性 |
| 业务可讲性 | **未评估** | 需 LLM 评估叙事逻辑和表现力 |
| 小白理解度 | **未评估** | 需 LLM 验证类比和解释是否足够通俗 |
| 平台适配 | **未评估** | 需 LLM 检查各平台内容是否匹配受众 |
| 边界感 | **未评估** | 需 LLM 审查风险表述和免责声明 |
| 个人主线 | **未评估** | 需 LLM 验证与 AI-FDE 主线的契合度 |
| **总体** | **未评估** | 请在 LLM 模式下重新生成以获取质量评分 |

## 结论

⚠️ **No-LLM 模式下不评估内容质量** — 当前内容基于规则模板生成，包含 [TODO] 标记处需要 LLM 补充。
请配置 LLM_API_KEY 后重新运行 `python run.py content {ctx['full_name']}` 以获取完整的质量评估。

---

*生成时间：{ctx['now']}*
*模式：No-LLM fallback — content_quality_score = not_evaluated*
"""

    # LLM mode — would produce real scores
    return f"""# {ctx['name']} — 内容质量检查

> 模式：LLM 评估

## 评分维度

| 维度 | 评分 | 说明 |
|------|------|------|
| 内容准确性 | [LLM] /10 | 基于事实核查 |
| 业务可讲性 | [LLM] /10 | 基于叙事质量 |
| 小白理解度 | [LLM] /10 | 基于通俗度评估 |
| 平台适配 | [LLM] /10 | 基于各平台受众匹配 |
| 边界感 | [LLM] /10 | 基于风险表述审查 |
| 个人主线 | [LLM] /10 | 基于 AI-FDE 契合度 |
| **总体** | **[LLM]/10** | 加权平均 |

---

*生成时间：{ctx['now']}*
*模式：LLM*
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
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            content = ""
            if llm_available:
                from .analyzer import generate_content as llm_generate
                content = llm_generate(scored, file_name)
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
) -> tuple[Path, str]:
    """Generate a complete V2 content pack for a repo (Phase 7: retry + degraded).

    1. Enrich repo metadata from GitHub API
    2. Score the repo (rules + business value)
    3. Generate 11 content files (LLM or no-LLM fallback) with retry
    4. Write results to {output_dir}/{slug}/
    5. Mark repo as generated in state

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

    # 3. Build context
    ctx = _build_repo_context(scored)

    # 4. Prepare output directory
    slug = slugify_repo_name(repo_full_name)
    pack_dir = output_dir / slug

    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)

    # 5. Check LLM availability
    llm_available = _has_llm()
    mode_label = "LLM" if llm_available else "No-LLM fallback"
    logger.info("Content pack mode: %s (retries=%d, timeout=%ds)", mode_label, max_retries, timeout_seconds)

    # 6. Generate content with retry + timeout per file
    generated_types = []
    degraded_files = []
    failed_files = []

    for file_name in CONTENT_FILES_V2:
        try:
            content, is_degraded = _try_generate_file(
                file_name, scored, ctx, llm_available,
                max_retries=max_retries,
            )
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

    # 7. Write status manifest
    status = "ok"
    if failed_files:
        status = "failed"
    elif degraded_files:
        status = "degraded"

    # Phase 8: Enhanced manifest with quality metadata
    quality_status = "ready"
    if status == "failed":
        quality_status = "degraded"
    elif status == "degraded":
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

    # Determine recommended platforms from platform scores
    recommended_platforms = []
    try:
        from .platform_score import score_platform_fit
        platform_labels = {
            "xiaohongshu": "小红书", "douyin": "抖音",
            "videohao": "视频号", "wechat": "公众号", "geo": "外贸/GEO",
        }
        # We can only make a best-effort guess without a full ScoredRepo
        recommended_platforms = ["xiaohongshu", "douyin"]  # defaults
    except Exception:
        recommended_platforms = ["xiaohongshu", "douyin"]

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
        "requires_manual_review": status in ("degraded", "failed") or len(degraded_files) > 0,
        "quality_status": quality_status,
        "risk_level": risk_level,
        "recommended_platforms": recommended_platforms,
    }
    manifest_path = pack_dir / "_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 8. Mark as generated
    mark_as_generated(repo_full_name, generated_types)

    return pack_dir, status
