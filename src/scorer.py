"""Rule-based scoring engine for GitHub repos (v4).

4-layer scoring architecture:
  1. repo_selection_score — "今天适不适合做内容" (0-100)
  2. business_value_score — "商业价值有多大" (0-100, in business_score.py)
  3. platform_fit_score — "适合哪个平台" (per-platform 0-100, in platform_score.py)
  4. risk_score — "风险多高" (per-category, in risk_score.py)
  5. content_quality_score — "内容质量" (LLM only, "未评估" in fallback)

Plus: classification, AI eligibility gate, evergreen demotion, pool routing.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import (
    AI_ELIGIBILITY_KEYWORDS,
    AWESOME_LIST_INDICATORS,
    EVERGREEN_STAR_THRESHOLD,
    FRAMEWORK_INDICATORS,
    HIGH_RISK_KEYWORDS,
    KNOWN_EVERGREEN,
    NON_AI_DISQUALIFIERS,
    TUTORIAL_INDICATORS,
)
from .enricher import EnrichedRepo


@dataclass
class ScoredRepo:
    """An EnrichedRepo with a computed score, classification, and metadata."""
    full_name: str
    name: str
    description: str
    url: str
    language: str
    stars: int
    forks: int
    updated_at: str
    topics: list[str]
    license: str
    readme: str
    contributors_count: int
    score: float = 0.0
    subscores: dict = field(default_factory=dict)
    # ── v4 classification fields ──
    content_type: str = "unclear"
    ai_evidence: list[str] = field(default_factory=list)
    risk_level: str = "none"
    filter_reason: str = ""
    demotion_reason: str = ""
    # ── v4 pool assignment ──
    pool: str = ""  # top5 / evergreen / resource / blocked / review


def _parse_days_ago(updated_at: str) -> int | None:
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - updated).days
    except (ValueError, TypeError):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# repo_selection_score — "今天适不适合做内容" (0-100)
# ═════════════════════════════════════════════════════════════════════════════

def _score_ai_relevance(repo: EnrichedRepo) -> float:
    """AI相关性 (20 pts) — topic/description keyword matching."""
    text = f"{repo.name or ''} {repo.description or ''} {' '.join(repo.topics or [])}".lower()
    score = 0.0
    for kw in ("agent", "rag", "mcp", "browser-use", "ai-search", "geo"):
        if kw in text:
            score += 5.0
    for kw in ("llm", "ai", "automation", "workflow", "prompt", "function-calling",
               "knowledge-base", "enterprise-search", "document-ai"):
        if kw in text:
            score += 2.5
    for kw in ("langchain", "llamaindex", "dify", "n8n", "vector-database",
               "search", "scrap", "crawl", "scrape"):
        if kw in text:
            score += 1.0
    return min(20.0, score)


def _score_recency(repo: EnrichedRepo) -> float:
    """近期活跃度/时效性 (15 pts)."""
    days = _parse_days_ago(repo.updated_at)
    if days is None:
        return 3.0
    if days <= 3:
        return 15.0
    elif days <= 7:
        return 12.0
    elif days <= 30:
        return 8.0
    elif days <= 90:
        return 4.0
    else:
        return 0.0


def _score_clarity(repo: EnrichedRepo) -> float:
    """项目清晰度 (15 pts) — README quality + description clarity."""
    score = 3.0
    readme = repo.readme or ""
    if len(readme) > 500:
        score += 4.0
    elif len(readme) > 100:
        score += 2.0
    if re.search(r"^#{1,3}\s", readme, re.MULTILINE):
        score += 3.0
    if re.search(r"[一-鿿]", readme):
        score += 2.0
    desc = repo.description or ""
    if 20 < len(desc) < 150:
        score += 3.0
    return min(15.0, score)


def _score_runnability(repo: EnrichedRepo) -> float:
    """可运行/可展示程度 (15 pts)."""
    score = 3.0
    all_text = f"{repo.name or ''} {repo.description or ''} {repo.readme or ''}".lower()
    install_signals = ("installation", "pip install", "npm install", "docker",
                       "docker-compose", "quick start", "getting started")
    hits = sum(1 for s in install_signals if s in all_text)
    score += min(6.0, hits * 1.5)
    demo_signals = ("demo", "playground", "try it", "live demo", "screenshot", "gif")
    demo_hits = sum(1 for s in demo_signals if s in all_text)
    score += min(4.0, demo_hits * 1.0)
    if repo.stars >= 1000:
        score += 2.0
    return min(15.0, score)


def _score_tellability(repo: EnrichedRepo) -> float:
    """内容可讲性 (15 pts) — does this make a good story?"""
    score = 4.0
    text = f"{repo.name or ''} {repo.description or ''} {' '.join(repo.topics or [])}".lower()
    hot = {"agent", "browser-use", "mcp", "rag", "geo", "ai-search"}
    hot_hits = sum(1 for t in hot if t in text)
    score += min(6.0, hot_hits * 1.5)
    desc = repo.description or ""
    if len(desc) > 30:
        score += 2.0
    if len(repo.topics) >= 4:
        score += 2.0
    if any(k in text for k in ("solve", "problem", "automate", "simplify", "解决")):
        score += 1.0
    return min(15.0, score)


def _score_community(repo: EnrichedRepo) -> float:
    """社区信号 (10 pts) — stars + contributors + forks."""
    score = 0.0
    if repo.stars >= 50000:
        score += 3.0
    elif repo.stars >= 5000:
        score += 5.0
    elif repo.stars >= 1000:
        score += 4.0
    elif repo.stars >= 100:
        score += 2.0
    else:
        score += 1.0
    if repo.contributors_count >= 5:
        score += 3.0
    elif repo.contributors_count >= 2:
        score += 1.5
    if repo.forks >= 1000:
        score += 2.0
    elif repo.forks >= 100:
        score += 1.0
    return min(10.0, score)


def _score_risk_controllable(repo: EnrichedRepo) -> float:
    """风险可控性 (10 pts) — higher = safer to recommend."""
    score = 7.0
    if repo.license:
        score += 1.5
    if repo.contributors_count >= 3:
        score += 0.5
    text = f"{repo.name or ''} {repo.description or ''} {repo.readme or ''}".lower()
    risk_hits = [kw for kw in HIGH_RISK_KEYWORDS if kw in text]
    if risk_hits:
        score -= len(risk_hits) * 3.0
    unmaintained = ("deprecated", "unmaintained", "archived", "abandoned")
    if any(k in text for k in unmaintained):
        score -= 2.0
    return max(0.0, min(10.0, score))


# ═════════════════════════════════════════════════════════════════════════════
# Content classification & filtering (unchanged from v3)
# ═════════════════════════════════════════════════════════════════════════════

def _build_search_text(repo) -> str:
    return f"{repo.name or ''} {repo.description or ''} {' '.join(repo.topics or [])}".lower()


def _build_all_text(repo) -> str:
    readme = (repo.readme or "").lower()
    return f"{_build_search_text(repo)} {readme}"


def _build_metadata_text(repo) -> str:
    return _build_search_text(repo)


def check_high_risk(repo) -> tuple[bool, list[str]]:
    all_text = _build_all_text(repo)
    hits = [kw for kw in HIGH_RISK_KEYWORDS if kw in all_text]
    return len(hits) > 0, hits


def check_ai_eligibility(repo) -> tuple[bool, list[str]]:
    """Check AI eligibility with tiered evidence strength.

    Returns (eligible, evidence_list).
    Evidence may include a 'WEAK:' prefix for borderline matches
    (≤2 keyword hits, none from STRONG_AI_SIGNALS).
    """
    text = _build_search_text(repo)
    for kw in NON_AI_DISQUALIFIERS:
        if kw in text:
            return False, [f"非AI内容标记: {kw}"]

    all_evidence = [kw for kw in AI_ELIGIBILITY_KEYWORDS if kw in text]
    if not all_evidence:
        return False, []

    # Check AI substance: ≤2 weak generic matches without strong signals → borderline
    from .config import STRONG_AI_SIGNALS
    has_strong = any(kw in text for kw in STRONG_AI_SIGNALS)
    if not has_strong and len(all_evidence) <= 2:
        return True, ["WEAK:" + ew for ew in all_evidence]
    return True, all_evidence


def _check_is_hype(repo) -> bool:
    """Detect hype projects with no real code/substance."""
    from .config import HYPE_INDICATORS
    text = _build_all_text(repo).lower()
    hype_hits = [kw for kw in HYPE_INDICATORS if kw in text]
    if not hype_hits:
        return False
    # Hype only matters when there's no real runnable code
    has_runnable = _check_is_runnable(repo)
    readme_len = len(repo.readme or "")
    has_substance = has_runnable or readme_len > 800
    return not has_substance  # hype without substance = flagged


def _check_is_awesome_list(repo) -> bool:
    text = _build_metadata_text(repo).lower()
    name_lower = (repo.name or "").lower()
    if name_lower.startswith("awesome-") or name_lower.startswith("awesome_"):
        return True
    for ind in AWESOME_LIST_INDICATORS:
        if ind in text:
            return True
    return False


def _check_is_tutorial(repo) -> bool:
    text = _build_metadata_text(repo).lower()
    for ind in TUTORIAL_INDICATORS:
        if ind in text:
            return True
    topics = [t.lower() for t in (repo.topics or [])]
    for t in ("tutorial", "course", "beginner", "guide", "book", "education", "lesson"):
        if t in topics:
            return True
    return False


def _check_is_framework(repo) -> bool:
    if repo.full_name in KNOWN_EVERGREEN:
        return True
    # v7: Also match by repo name (e.g. "ai-ml-ops/mlflow" → "mlflow" matches "mlflow/mlflow")
    name_lower = (repo.name or "").lower()
    for full in KNOWN_EVERGREEN:
        if "/" in full and full.split("/")[1] == name_lower:
            return True
    text = _build_metadata_text(repo).lower()
    for ind in FRAMEWORK_INDICATORS:
        if ind in text:
            return True
    return False


def _check_is_runnable(repo) -> bool:
    all_text = _build_all_text(repo)
    runnable_signals = [
        "installation", "install", "getting started", "quick start",
        "docker", "npm install", "pip install", "docker-compose",
        "demo", "live demo", "try it", "playground",
        "npx ", "git clone", "yarn add", "pnpm", "quickstart",
    ]
    hits = sum(1 for s in runnable_signals if s in all_text)
    return hits >= 2


def classify_content_type(repo) -> str:
    if repo.full_name in KNOWN_EVERGREEN or _is_known_evergreen_by_name(repo):
        return "framework_tool"
    is_risk, _ = check_high_risk(repo)
    if is_risk:
        return "high_risk"
    if _check_is_awesome_list(repo):
        return "awesome_list"
    if _check_is_tutorial(repo):
        return "tutorial_guide"
    if _check_is_hype(repo):
        return "unclear"  # hype without substance → unclear, not runnable
    if _check_is_framework(repo):
        return "framework_tool"
    if _check_is_runnable(repo):
        return "runnable_project"
    return "unclear"


def check_evergreen_demotion(repo) -> tuple[bool, str]:
    # v7: Check full_name AND name (e.g. "ai-ml-ops/mlflow" → "mlflow")
    if repo.full_name in KNOWN_EVERGREEN:
        return True, f"已知常青项目（{repo.stars/1000:.0f}K stars），进入常青基础设施候选池"
    if _is_known_evergreen_by_name(repo):
        return True, f"已知常青项目（按名称匹配，{repo.stars/1000:.0f}K stars），进入常青基础设施候选池"
    if repo.stars <= EVERGREEN_STAR_THRESHOLD:
        return False, ""
    days_ago = _parse_days_ago(repo.updated_at)
    topics_str = " ".join(repo.topics or []).lower()
    desc_name = f"{repo.name} {repo.description}".lower()
    core_niches = {"geo", "ai-search", "browser-use"}
    has_core = any(t in topics_str or t in desc_name for t in core_niches)
    if days_ago is not None and days_ago <= 3 and has_core:
        return False, ""
    return True, f"常青项目（{repo.stars/1000:.0f}K stars），进入常青基础设施候选池"


def _is_known_evergreen_by_name(repo) -> bool:
    """Check if repo.name matches known evergreen, even if full_name differs."""
    name_lower = (repo.name or "").lower()
    for full in KNOWN_EVERGREEN:
        if "/" in full and full.split("/")[1] == name_lower:
            return True
    return False


def apply_classification_and_filters(scored: list[ScoredRepo]) -> dict:
    """Classify, gate-check, and demote all scored repos into pools.

    Returns:
      {
        "runnable_top5": [...],
        "evergreen_candidates": [...],
        "resource_candidates": [...],
        "high_risk_skipped": [...],
        "all_classified": [...],
      }
    """
    result = {
        "runnable_top5": [],
        "evergreen_candidates": [],
        "resource_candidates": [],
        "high_risk_skipped": [],
        "all_classified": [],
    }

    for repo in scored:
        content_type = classify_content_type(repo)
        repo.content_type = content_type

        is_ai, ai_evidence = check_ai_eligibility(repo)
        repo.ai_evidence = ai_evidence

        is_risk, risk_hits = check_high_risk(repo)
        repo.risk_level = "high" if is_risk else ("low" if repo.stars < 100 or repo.contributors_count <= 1 else "none")

        if content_type == "high_risk":
            repo.filter_reason = f"高风险关键词: {', '.join(risk_hits)}"
            repo.pool = "blocked"
            result["high_risk_skipped"].append(repo)
            continue

        if not is_ai:
            repo.filter_reason = "未通过AI相关性检查，缺少AI/LLM/Agent等关键词"
            if content_type == "awesome_list":
                repo.demotion_reason = "awesome list 非单个可拆解项目"
                repo.pool = "resource"
                result["resource_candidates"].append(repo)
            elif content_type == "tutorial_guide":
                repo.demotion_reason = "教程/面试类项目，非AI-FDE专题"
                repo.pool = "resource"
                result["resource_candidates"].append(repo)
            else:
                repo.filter_reason += "；内容类型不匹配"
                repo.pool = "review"
            continue

        # v7: Weak AI signal — route to review regardless of content_type,
        # unless it's a known framework/evergreen or awesome_list/tutorial.
        # Previously only caught unclear content; now catches runnable_project
        # with weak AI signals too (e.g. qgis with "geo", yoast with "seo").
        weak_ai = all(str(ew).startswith("WEAK:") for ew in ai_evidence)
        if weak_ai and content_type not in ("framework_tool", "awesome_list", "tutorial_guide"):
            if _check_is_framework(repo):
                pass  # fall through to framework_tool handling
            else:
                repo.filter_reason = "AI信号弱（仅含泛化AI关键词），需人工审核确认选题价值"
                repo.pool = "review"
                result["all_classified"].append(repo)
                continue

        if content_type == "awesome_list":
            repo.demotion_reason = "项目合集/awesome list，进入资料库候选"
            repo.pool = "resource"
            result["resource_candidates"].append(repo)
            continue

        if content_type == "tutorial_guide":
            ai_fde_indicators = ["ai-agent", "rag", "llm-app", "ai-application",
                                  "prompt-engineering", "langchain", "function-calling",
                                  "claude", "openai", "quickstart",
                                  "anthropic", "deepseek", "gemini", "mcp",
                                  "browser-use", "workflow", "orchestration"]
            all_text = _build_all_text(repo)
            if any(ind in all_text for ind in ai_fde_indicators):
                repo.demotion_reason = "AI-FDE教程，降权处理"
                repo.score *= 0.7
            else:
                repo.demotion_reason = "教程/面试类项目，进入资料库候选"
                repo.pool = "resource"
                result["resource_candidates"].append(repo)
                continue

        if content_type == "framework_tool":
            should_demote, demote_reason = check_evergreen_demotion(repo)
            if should_demote:
                repo.demotion_reason = demote_reason
                repo.pool = "evergreen"
                result["evergreen_candidates"].append(repo)
                continue

        if content_type == "unclear":
            # v7: Hype without substance → review, not top5
            if _check_is_hype(repo):
                repo.filter_reason = "疑似hype项目（夸大宣传+信息不足），需人工审核"
                repo.pool = "review"
                result["all_classified"].append(repo)
                continue
            repo.score *= 0.85
            repo.demotion_reason = "项目信息不足（content_type: unclear），降权处理"

        repo.pool = "top5"
        result["runnable_top5"].append(repo)

    result["runnable_top5"].sort(key=lambda r: r.score, reverse=True)
    result["evergreen_candidates"].sort(key=lambda r: r.score, reverse=True)
    result["resource_candidates"].sort(key=lambda r: r.score, reverse=True)
    result["high_risk_skipped"].sort(key=lambda r: r.score, reverse=True)
    result["all_classified"] = scored

    return result


# ═════════════════════════════════════════════════════════════════════════════
# Core scoring — repo_selection_score (v4)
# ═════════════════════════════════════════════════════════════════════════════

def score_repo(repo: EnrichedRepo) -> ScoredRepo:
    """Compute repo_selection_score (0-100) across 7 dimensions, then apply dedup penalty.

    Dimensions and weights:
      AI相关性 20, 近期活跃度/时效性 15, 项目清晰度 15,
      可运行/可展示程度 15, 内容可讲性 15, 社区信号 10, 风险可控性 10
    """
    subscores = {
        "ai_relevance": _score_ai_relevance(repo),
        "recency": _score_recency(repo),
        "clarity": _score_clarity(repo),
        "runnability": _score_runnability(repo),
        "tellability": _score_tellability(repo),
        "community": _score_community(repo),
        "risk_controllable": _score_risk_controllable(repo),
    }

    total = sum(subscores.values())
    total = max(0.0, min(100.0, total))
    total *= getattr(repo, "_dedup_penalty", 1.0)

    return ScoredRepo(
        full_name=repo.full_name,
        name=repo.name,
        description=repo.description,
        url=repo.url,
        language=repo.language,
        stars=repo.stars,
        forks=repo.forks,
        updated_at=repo.updated_at,
        topics=repo.topics,
        license=repo.license,
        readme=repo.readme,
        contributors_count=repo.contributors_count,
        score=round(total, 2),
        subscores=subscores,
    )


def rank_repos(scored: list[ScoredRepo], limit: int = 20) -> list[ScoredRepo]:
    ranked = sorted(scored, key=lambda r: r.score, reverse=True)
    return ranked[:limit]
