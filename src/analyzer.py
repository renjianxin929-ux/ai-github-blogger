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


def generate_content(repo: ScoredRepo, template_name: str) -> str:
    """Load a template, format it with repo data, and generate content via LLM.

    Template files should use $variable_name placeholders matching ScoredRepo fields.
    """
    from .content_pack import CONTENT_PACK_TEMPLATE_MAP

    # Resolve output filename → actual template filename
    actual_template = CONTENT_PACK_TEMPLATE_MAP.get(template_name, template_name)
    template_path = TEMPLATES_DIR / f"{actual_template}.md"

    if not template_path.exists():
        logger.warning("Missing template for %s: %s not found", template_name, template_path.name)
        return ""

    template_content = template_path.read_text(encoding="utf-8")

    # Build template variables from repo fields
    template_vars = {
        "full_name": repo.full_name,
        "name": repo.name,
        "description": repo.description,
        "url": repo.url,
        "language": repo.language,
        "stars": str(repo.stars),
        "forks": str(repo.forks),
        "updated_at": repo.updated_at,
        "topics": ", ".join(repo.topics),
        "license": repo.license,
        "readme": (repo.readme or "")[:3000],
        "contributors_count": str(repo.contributors_count),
        "score": str(repo.score),
    }

    # Use string.Template for safe substitution
    try:
        user_prompt = Template(template_content).safe_substitute(**template_vars)
    except Exception:
        user_prompt = template_content

    system_prompt = (
        "你是一个专业的内容创作者，擅长将技术项目转化为适合不同平台的优质内容。"
        "请严格按照模板要求输出内容，不要自行添加额外章节。"
    )

    try:
        return _call_llm(system_prompt, user_prompt)
    except Exception as e:
        logger.warning("Content generation failed for %s/%s: %s", repo.full_name, template_name, e)
        return ""
