"""LLM analysis via OpenAI-compatible /chat/completions API."""
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

import requests

from .config import (
    FDE_DIMENSIONS,
    LLM_TIMEOUT,
    TEMPLATES_DIR,
    get_llm_config,
)
from .scorer import ScoredRepo

logger = logging.getLogger(__name__)


@dataclass
class FDEAnalysis:
    """AI-FDE analysis result for a repository."""
    F: str  # Feature / functional innovation
    D: str  # Differentiation
    E: str  # Ecosystem value
    overall_score: int  # 1-10


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call OpenAI-compatible /chat/completions and return message content."""
    config = get_llm_config()
    url = config["base_url"].rstrip("/") + "/chat/completions"

    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }

    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _build_fde_prompt(repo: ScoredRepo) -> tuple[str, str]:
    """Build system + user prompts for AI-FDE analysis."""
    system_prompt = (
        "你是一个资深技术分析师，擅长评估开源项目的创新性、差异化和生态价值。"
        "请用中文回复，输出严格的 JSON 格式，不要包含 markdown 代码块标记。"
    )

    # Truncate readme for prompt size control
    readme_excerpt = (repo.readme or "")[:3000]

    user_prompt = f"""请从 F（功能创新）、D（差异化）、E（生态价值）三个维度分析以下 GitHub 开源项目。

项目名称：{repo.full_name}
描述：{repo.description}
语言：{repo.language}
Stars：{repo.stars}
Forks：{repo.forks}
最近更新：{repo.updated_at}
Topics：{", ".join(repo.topics)}
许可证：{repo.license}
贡献者数：{repo.contributors_count}
当前评分：{repo.score}/100

README 摘要：
{readme_excerpt}

F 维度定义：{FDE_DIMENSIONS["F"]}
D 维度定义：{FDE_DIMENSIONS["D"]}
E 维度定义：{FDE_DIMENSIONS["E"]}

请输出 JSON：
{{
  "F": "功能创新分析（2-3句话）",
  "D": "差异化分析（2-3句话）",
  "E": "生态价值分析（2-3句话）",
  "overall_score": 8
}}
overall_score 为 1-10 的综合评分。"""

    return system_prompt, user_prompt


def _parse_fde_response(text: str) -> FDEAnalysis:
    """Parse LLM response text into FDEAnalysis. Handles markdown code blocks."""
    # Try to extract JSON from markdown code blocks first
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    data = json.loads(text)
    return FDEAnalysis(
        F=data.get("F", ""),
        D=data.get("D", ""),
        E=data.get("E", ""),
        overall_score=int(data.get("overall_score", 5)),
    )


def ai_fde_analyze(repo: ScoredRepo) -> FDEAnalysis:
    """Run AI-FDE analysis on a scored repo. Returns fallback on error."""
    try:
        system_prompt, user_prompt = _build_fde_prompt(repo)
        response_text = _call_llm(system_prompt, user_prompt)
        return _parse_fde_response(response_text)
    except Exception as e:
        logger.warning("AI-FDE analysis failed for %s: %s", repo.full_name, e)
        return FDEAnalysis(
            F=f"分析失败（{repo.full_name}）：API 调用出错，请稍后重试。",
            D=f"分析失败（{repo.full_name}）：API 调用出错，请稍后重试。",
            E=f"分析失败（{repo.full_name}）：API 调用出错，请稍后重试。",
            overall_score=0,
        )


def generate_content(repo: ScoredRepo, template_name: str, ctx: dict | None = None) -> str:
    """Load a template, format it with repo data, and generate content via LLM.

    Template files should use $variable_name placeholders matching ScoredRepo fields
    and context dict keys.  The system prompt includes repo identity anchors
    (confirmed features, risk boundaries) to prevent cross-project hallucination.
    """
    from .content_pack import CONTENT_PACK_TEMPLATE_MAP

    # Resolve output filename → actual template filename
    actual_template = CONTENT_PACK_TEMPLATE_MAP.get(template_name, template_name)
    template_path = TEMPLATES_DIR / f"{actual_template}.md"

    if not template_path.exists():
        logger.warning("Missing template for %s: %s not found", template_name, template_path.name)
        return ""

    template_content = template_path.read_text(encoding="utf-8")

    # Build template variables from repo + context
    template_vars = {
        "full_name": repo.full_name,
        "name": repo.name,
        "description": repo.description or "",
        "url": repo.url,
        "language": repo.language or "",
        "stars": str(repo.stars),
        "forks": str(repo.forks),
        "updated_at": repo.updated_at or "",
        "topics": ", ".join(repo.topics) if repo.topics else "",
        "license": repo.license or "",
        "readme": (repo.readme or "")[:3000],
        "contributors_count": str(repo.contributors_count),
        "score": str(repo.score),
    }

    # Merge context dict variables if provided
    if ctx:
        for key, value in ctx.items():
            if isinstance(value, (str, int, float)):
                template_vars[key] = str(value)
            elif isinstance(value, list):
                template_vars[key] = "\n".join(f"- {item}" for item in value)

    # Use string.Template for safe substitution
    try:
        user_prompt = Template(template_content).safe_substitute(**template_vars)
    except Exception:
        user_prompt = template_content

    # Build system prompt with repo identity anchors
    system_prompt = _build_system_prompt(repo, ctx or {})

    try:
        return _call_llm(system_prompt, user_prompt)
    except Exception as e:
        logger.warning("Content generation failed for %s/%s: %s", repo.full_name, template_name, e)
        return ""


def _build_system_prompt(repo: ScoredRepo, ctx: dict) -> str:
    """Build a system prompt that anchors the LLM to THIS repo's identity.

    Includes confirmed features, explicit non-features, and risk boundaries
    so the LLM does not hallucinate capabilities from other projects.
    """
    confirmed = ctx.get("confirmed_features") or _derive_confirmed_features(repo)
    unsupported = ctx.get("unsupported_features") or _derive_unsupported_features(repo)
    boundaries = ctx.get("risk_boundaries") or _derive_risk_boundaries(repo)

    parts = [
        "你是「09」，一个专注于 AI-FDE（功能创新/差异化/生态价值）学习的技术博主。",
        "你正在从零到一学习 AI 领域，用拆解开源项目的方式记录成长。",
        "",
        "你的内容风格：",
        "- 不写软文，不写百科介绍，不写工具广告",
        "- 用\"我今天拆了一个项目\"的学习视角",
        "- 技术判断要能翻译成老板听得懂的业务语言",
        "- 对风险边界诚实，不夸大，不回避",
        "",
        "=== 当前项目身份锚定（必须严格遵守） ===",
        f"项目：{repo.full_name}",
        f"一句话描述：{repo.description}",
        "",
        "【确认的真实功能 — 只能围绕这些写】：",
    ]
    for f in confirmed:
        parts.append(f"  - {f}")

    parts.append("")
    parts.append("【明确不属于本项目的概念 — 禁止写入】：")
    for f in unsupported:
        parts.append(f"  - {f}")

    parts.append("")
    parts.append("【风险与法律边界 — 必须遵守】：")
    for b in boundaries:
        parts.append(f"  - {b}")

    parts.append("")
    parts.append("=== 锚定结束 ===")
    parts.append("")
    parts.append("输出要求：严格按用户模板的结构和语气输出。不要引入不属于当前项目的技术概念。")

    return "\n".join(parts)


def _derive_confirmed_features(repo: ScoredRepo) -> list[str]:
    """Derive confirmed features from repo metadata (fallback when ctx doesn't provide them)."""
    topics = [t.lower() for t in (repo.topics or [])]
    desc = (repo.description or "").lower()
    readme = (repo.readme or "").lower()

    features = []
    if any(k in topics or k in desc for k in ("scrap", "crawl", "web-data", "data-extract")):
        features.append("网页抓取/爬取（scrape/crawl）")
    if any(k in topics or k in desc for k in ("search",)):
        features.append("网页搜索（web search）")
    if any(k in topics or k in desc for k in ("markdown", "html-to-markdown")):
        features.append("HTML → Markdown / 结构化数据转换")
    if any(k in topics or k in desc or k in readme for k in ("llm", "ai-agent", "ai-search")):
        features.append("面向 LLM / AI Agent 的数据供给")
    if any(k in topics for k in ("mcp",)):
        features.append("MCP (Model Context Protocol) 集成")
    if any(k in topics or k in desc for k in ("api",)):
        features.append("API-first 设计，支持多语言 SDK")
    if any(k in readme for k in ("docker", "self-host", "self host")):
        features.append("支持 Docker 自托管或云 API")

    if not features:
        features.append(f"基于 README 描述的核心功能：{repo.description}")

    return features


def _derive_unsupported_features(repo: ScoredRepo) -> list[str]:
    """Derive features explicitly NOT belonging to this repo type.

    Uses project-type classification to produce type-specific unsupported lists
    instead of hardcoding for just one project type.
    """
    from .reviewer import classify_project_type as _classify_project_type

    topics = [t.lower() for t in (repo.topics or [])]
    project_type = _classify_project_type(
        repo_full_name=repo.full_name,
        topics=topics,
        description=repo.description or "",
    )

    unsupported_map = {
        "web_scraping_api": [
            "知识库 / RAG 平台 / 向量数据库（与当前项目定位不符）",
            "LLM 推理 / 模型部署 / ChatBot 框架",
            "LangChain / LlamaIndex 等 AI 编排框架",
            "中文分词 / 中文语义理解专用工具",
        ],
        "browser_automation": [
            "GEO 工具 / AI 搜索排名优化工具（与当前项目定位不符）",
            "网页数据抓取 API / 爬虫服务",
            "SEO 优化工具 / 搜索引擎优化平台",
            "能保证 AI 引用 / 排名 / 询盘增长",
        ],
        "rag_engine": [
            "网页抓取 API / 爬虫平台（与当前项目定位不符）",
            "实时搜索替代 / 通用搜索引擎",
            "浏览器自动化工具",
            "能绕过登录 / 绕过风控",
        ],
        "resource_list": [
            "可直接运行的平台 / 产品 / 服务",
            "一键部署 / 生产级基础设施",
            "有 API / SDK 可供调用",
        ],
        "agent_framework": [
            "保证商业落地 / 保证 ROI",
            "绕过登录 / 绕过风控 / 万能爬虫",
            "GEO 排名 / AI 引用保证",
        ],
    }

    unsupported = unsupported_map.get(project_type, [
        "本项目的功能范围以 README 和 Topics 为准，不要引入未提及的技术概念",
    ])

    return unsupported


def _derive_risk_boundaries(repo: ScoredRepo) -> list[str]:
    """Derive risk boundaries based on repo characteristics.

    Uses project-type classification from reviewer module to produce
    type-specific risk boundaries instead of hardcoded per-project rules.
    """
    from .reviewer import classify_project_type as _classify_project_type
    from .reviewer import get_project_boundary

    topics = [t.lower() for t in (repo.topics or [])]
    license_name = (repo.license or "").lower()
    project_type = _classify_project_type(
        repo_full_name=repo.full_name,
        topics=topics,
        description=repo.description or "",
    )

    boundary = get_project_boundary(project_type)

    boundaries = []

    # Allowed claims
    if boundary.allowed_claims:
        boundaries.append(f"可声明范围：{'、'.join(boundary.allowed_claims[:5])}")

    # Forbidden claims
    if boundary.forbidden_claims:
        boundaries.append(f"禁止声明：{'、'.join(boundary.forbidden_claims[:5])}")

    # Expected disclaimers
    if boundary.expected_disclaimers:
        boundaries.extend(boundary.expected_disclaimers)

    # License risks
    if "agpl" in license_name or "gpl" in license_name:
        boundaries.append(f"{repo.license} 许可证有 Copyleft 限制，商用需评估")

    if not license_name:
        boundaries.append("未明确许可证，商用前需确认版权归属")

    if not boundaries:
        boundaries.append("使用前应阅读并遵守目标网站的 robots.txt 和服务条款")

    return boundaries
