"""Daily Operator Workbench — Phase 23.

A read-only, guidance-only daily entry point for human operators.
Reads existing pipeline data (top5, publish_history, quality gate) and outputs:
  - Today's decision summary
  - Best candidate with reasoning
  - Platform suggestions
  - Risk warnings
  - Next-step CLI commands
  - Human review checklist

Zero side effects — no LLM calls, no content generation, no file writes
(except optional --output for saving the report).
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date as dt_date, datetime, timedelta, timezone
from pathlib import Path

from .config import REPORTS_DIR, STATE_DIR, PUBLISH_PACKS_DIR

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PUB_A = 75
PUB_B = 60
PUB_C = 40

VALID_PLATFORMS = ["wechat", "xiaohongshu", "douyin", "videohao", "geo"]
PLATFORM_LABELS: dict[str, str] = {
    "wechat": "公众号",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "videohao": "视频号",
    "geo": "GEO",
}


# ═══════════════════════════════════════════════════════════════
# Internal data loaders
# ═══════════════════════════════════════════════════════════════

def _load_top5(date_str: str) -> list[dict]:
    path = REPORTS_DIR / f"top5_{date_str}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _load_publish_history() -> dict:
    path = STATE_DIR / "publish_history.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_published(repo_full_name: str, history: dict | None = None) -> bool:
    if history is None:
        history = _load_publish_history()
    normalized = repo_full_name.strip().lower()
    return normalized in history and len(history[normalized]) > 0


def _load_quality_gate_verdict() -> dict:
    path = REPORTS_DIR / "system_quality_report_v8.md"
    result = {"verdict": "unknown", "score": "N/A", "passed": "?", "total": "?",
              "blocking": 0, "ready_for_llm": "unknown"}

    if not path.exists():
        return result

    try:
        text = path.read_text("utf-8")
    except Exception:
        return result

    m = re.search(r"(?:Final Verdict|VERDICT).*?(PASS|CONDITIONAL_PASS|FAIL)", text)
    if m:
        result["verdict"] = m.group(1)

    m = re.search(r"Adjusted Score.*?([\d.]+)/100", text)
    if m:
        result["score"] = m.group(1)

    m = re.search(r"Passed.*?(\d+)/(\d+)", text)
    if m:
        result["passed"] = m.group(1)
        result["total"] = m.group(2)

    m = re.search(r"blocking_issues.*?:\s*(\d+)", text, re.IGNORECASE)
    if m:
        result["blocking"] = int(m.group(1))

    m = re.search(r"ready_for_llm.*?:\s*(yes|no|conditional)", text, re.IGNORECASE)
    if m:
        result["ready_for_llm"] = m.group(1)

    return result


def _check_llm_available() -> bool:
    import os
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text("utf-8").splitlines():
                    if line.startswith("LLM_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass
    return bool(key)


def _load_review_queue(date_str: str) -> str:
    path = REPORTS_DIR / f"review_queue_{date_str}.md"
    if not path.exists():
        candidates = sorted(REPORTS_DIR.glob("review_queue_*.md"), reverse=True)
        if candidates:
            path = candidates[0]
        else:
            return ""
    try:
        return path.read_text("utf-8")
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════
# Candidate analysis
# ═══════════════════════════════════════════════════════════════

def _classify_candidate(repo: dict, history: dict) -> dict:
    """Analyze a single candidate repo and return its workbench assessment."""
    full_name = repo.get("full_name", "?")
    pub_score = repo.get("publishability_score", 0) or 0
    raw_score = repo.get("score", 0) or 0
    stars = repo.get("stars", 0) or 0
    content_type = repo.get("content_type", "runnable_project")
    topics = repo.get("topics", [])
    description = repo.get("description", "")
    pool = repo.get("pool", "top5")

    published = _is_published(full_name, history)

    # Determine tier
    if published:
        tier = "published"
        tier_icon = "📌"
        tier_label = "已发布，跳过"
    elif pub_score >= PUB_A:
        tier = "recommended"
        tier_icon = "✅"
        tier_label = "推荐发布"
    elif pub_score >= PUB_B:
        tier = "watch"
        tier_icon = "⚠️"
        tier_label = "可观察候选"
    elif pub_score >= PUB_C:
        tier = "review"
        tier_icon = "📋"
        tier_label = "需人工审核"
    else:
        tier = "skip"
        tier_icon = "❌"
        tier_label = f"不推荐（{pub_score:.0f}<{PUB_C}）"

    # Platform suggestions
    platforms = _suggest_platforms(repo)

    # Risks
    risks = []
    if pub_score < PUB_B:
        risks.append(f"可发布性偏低 ({pub_score:.0f}/100)，需人工审核后决定")
    if raw_score < 50:
        risks.append(f"选题参考分较低 ({raw_score:.0f}/100)")
    if pool == "review":
        risks.append("该项目在审核池中，需额外验证")
    if content_type == "unclear":
        risks.append("内容类型不明确，建议人工判断")

    # Reasons (for recommended repos)
    reasons = []
    if tier in ("recommended", "watch"):
        if pub_score >= PUB_A:
            reasons.append(f"可发布性得分高 ({pub_score:.0f}/100)，内容安全且有实用价值")
        elif pub_score >= PUB_B:
            reasons.append(f"可发布性在边界 ({pub_score:.0f}/100)，可观察后决定")
        if raw_score >= 60:
            reasons.append(f"选题参考分 ({raw_score:.0f}/100) 表明社区关注度较高")
        if stars >= 1000:
            reasons.append(f"社区认可度高（{stars:,} stars）")
        if content_type == "runnable_project":
            reasons.append("可运行项目，素材充分适合全平台分发")
        elif content_type == "tutorial_guide":
            reasons.append("教程类内容，适合公众号+小红书分发")
        elif content_type == "framework_platform":
            reasons.append("框架/平台项目，适合公众号+GEO长尾覆盖")
        if description and len(description) > 20:
            reasons.append(f"简介清晰: {description[:100]}")

    return {
        "full_name": full_name,
        "tier": tier,
        "tier_icon": tier_icon,
        "tier_label": tier_label,
        "published": published,
        "publishability_score": pub_score,
        "score": raw_score,
        "stars": stars,
        "content_type": content_type,
        "topics": topics,
        "description": description,
        "pool": pool,
        "platforms": platforms,
        "risks": risks,
        "reasons": reasons,
    }


def _suggest_platforms(repo: dict) -> list[str]:
    content_type = repo.get("content_type", "runnable_project")
    platforms = []
    if content_type in ("awesome_list", "resource_collection"):
        platforms = ["公众号", "GEO"]
    elif content_type == "tutorial_guide":
        platforms = ["公众号", "小红书"]
    elif content_type == "framework_platform":
        platforms = ["公众号", "GEO"]
    else:
        platforms = ["公众号", "小红书", "抖音", "视频号", "GEO"]
    return platforms


def _next_command(repo_name: str, tier: str, pub_score: float) -> str:
    if tier == "published":
        return f"python run.py mark-published <pack_dir> --platform <name>  # 追加平台"
    if tier in ("recommended", "watch"):
        return f"python run.py publish-flow {repo_name}"
    if tier == "review":
        return f"python run.py publish-pack {repo_name}  # 生成后需人工审核"
    return f"# {repo_name} 不推荐发布，建议等待下一轮"


# ═══════════════════════════════════════════════════════════════
# Core generator
# ═══════════════════════════════════════════════════════════════

def generate_workbench(date_str: str | None = None,
                       repo_filter: str | None = None) -> str:
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    top5 = _load_top5(date_str)
    history = _load_publish_history()
    qg = _load_quality_gate_verdict()
    llm_ok = _check_llm_available()

    # Analyze all candidates
    candidates = [_classify_candidate(r, history) for r in top5]

    # Apply repo filter if specified
    if repo_filter:
        normalized = repo_filter.strip().lower()
        candidates = [c for c in candidates if c["full_name"].lower() == normalized]
        if not candidates:
            # Try to load from all repos (not just top5) — check publish history
            extra_candidates = _load_top5(date_str)
            candidates = [_classify_candidate(r, history)
                         for r in extra_candidates
                         if r.get("full_name", "").lower() == normalized]

    published = [c for c in candidates if c["published"]]
    unpublished = [c for c in candidates if not c["published"]]

    recommended = [c for c in unpublished if c["tier"] == "recommended"]
    watch = [c for c in unpublished if c["tier"] == "watch"]
    review = [c for c in unpublished if c["tier"] == "review"]
    skipped = [c for c in unpublished if c["tier"] == "skip"]

    # Pick best candidate: first A-tier, then B, then C
    best = None
    if recommended:
        best = recommended[0]
    elif watch:
        best = watch[0]
    elif review:
        best = review[0]

    sep = "=" * 64
    sub = "-" * 32

    lines: list[str] = []
    lines.append(sep)
    lines.append(f"  AI GitHub Blogger — Daily Workbench ({date_str})")
    lines.append(sep)
    lines.append("")

    # ── Section 1: Decision Summary ──
    lines.append(f"── 1. 今日决策摘要 ──")
    lines.append("")
    qualified = len(recommended) + len(watch)
    total = len(candidates)
    lines.append(f"  候选总数:     {total} 个")
    lines.append(f"  推荐发布:     {len(recommended)} 个 (A级, ≥{PUB_A}分)")
    lines.append(f"  可观察:       {len(watch)} 个 (B级, {PUB_B}-{PUB_A - 1}分)")
    lines.append(f"  需审核:       {len(review)} 个 (C级, {PUB_C}-{PUB_B - 1}分)")
    lines.append(f"  不推荐:       {len(skipped)} 个")
    lines.append(f"  已发布跳过:   {len(published)} 个")
    if published:
        lines.append(f"     → {', '.join(c['full_name'] for c in published)}")
    lines.append("")
    lines.append(f"  LLM 状态:     {'✅ 可用' if llm_ok else '⚠️ 不可用'}")
    qg_icon = {"PASS": "✅", "CONDITIONAL_PASS": "⚠️", "FAIL": "❌"}.get(
        qg["verdict"], "❓")
    lines.append(f"  Quality Gate: {qg_icon} {qg['verdict']} "
                 f"({qg['score']}/100, {qg['passed']}/{qg['total']})")
    lines.append("")

    # ── Section 2: Best Candidate ──
    lines.append(f"── 2. 🏆 今日最推荐 ──")
    lines.append("")

    if best is None:
        lines.append("  ❌ 今日无强推荐项目。")
        lines.append("")
        # Explain why
        if published and not unpublished:
            lines.append("  原因: 所有 Top 5 候选均已发布。")
            lines.append("  建议: 等待下一轮抓取，或手动指定新项目。")
        elif not candidates:
            lines.append("  原因: 今日无 Top 5 候选数据。")
            lines.append(f"  建议: 运行 python run.py daily --no-llm 生成今日数据。")
        else:
            lines.append(f"  原因: 所有未发布候选的可发布性均低于 {PUB_C} 分。")
            lines.append("  建议: 检查管线数据质量，或手动指定候选项目。")
        lines.append("")
    else:
        lines.append(f"  项目:         {best['full_name']}")
        lines.append(f"  可发布性:     {best['publishability_score']:.0f}/100")
        lines.append(f"  选题参考:     {best['score']:.0f}/100")
        lines.append(f"  Stars:        {best['stars']:,}")
        lines.append(f"  类型:         {best['content_type']}")
        lines.append(f"  适合平台:     {', '.join(best['platforms'])}")
        lines.append(f"  状态:         {best['tier_icon']} {best['tier_label']}")
        if best["topics"]:
            lines.append(f"  标签:         {', '.join(best['topics'][:6])}")
        lines.append("")

        if best["reasons"]:
            lines.append("  推荐理由:")
            for i, reason in enumerate(best["reasons"], 1):
                lines.append(f"    {i}. {reason}")
            lines.append("")

    # ── Section 3: All Candidates Table ──
    lines.append(f"── 3. 全部候选 ──")
    lines.append("")

    if not candidates:
        lines.append("  今日无候选数据。")
        lines.append("")
    else:
        header = f"  {'状态':<12} {'项目':<40} {'可发布性':<8} {'选题分':<7} {'Stars':<8} {'类型':<16}"
        lines.append(header)
        lines.append(f"  {'-' * (len(header) - 2)}")
        for c in candidates:
            name = c["full_name"]
            pub_str = f"{c['publishability_score']:.0f}/100"
            score_str = f"{c['score']:.0f}"
            stars_str = f"{c['stars']:,}"
            ctype = c["content_type"]
            lines.append(
                f"  {c['tier_icon']} {c['tier_label']:<9} "
                f"{name:<40} {pub_str:<8} {score_str:<7} {stars_str:<8} {ctype:<16}"
            )
        lines.append("")

    # ── Section 4: Platform Suggestions ──
    lines.append(f"── 4. 平台建议 ──")
    lines.append("")

    if best:
        platforms = best["platforms"]
        content_type = best["content_type"]
        for p in ["公众号", "小红书", "抖音", "视频号", "GEO"]:
            if p in platforms:
                if p == "公众号":
                    lines.append(f"  ✅ {p}: 适合 — 技术深度内容，长文形式")
                elif p == "小红书":
                    lines.append(f"  ✅ {p}: 适合 — 图文卡片+技术要点")
                elif p in ("抖音", "视频号"):
                    lines.append(f"  ✅ {p}: 适合 — 可做演示视频/快速上手")
                elif p == "GEO":
                    lines.append(f"  ✅ {p}: 适合 — 可做长尾搜索关键词覆盖")
            else:
                lines.append(f"  ⏭️ {p}: 跳过 — 内容类型不适合此平台")
        lines.append("")

    # ── Section 5: Risk Warnings ──
    lines.append(f"── 5. 风险提醒 ──")
    lines.append("")

    all_risks = []
    if best and best["risks"]:
        all_risks.extend(best["risks"])
    if qg.get("blocking", 0) > 0:
        all_risks.append(f"Quality Gate 存在 {qg['blocking']} 个阻断问题，建议先解决")
    if qg["verdict"] == "FAIL":
        all_risks.append("Quality Gate 未通过，内容生成可能受影响")
    if not llm_ok:
        all_risks.append("LLM 不可用，内容将进入 structured_fallback 模式")

    if not all_risks:
        lines.append("  ✅ 无阻断风险")
    else:
        for r in all_risks:
            lines.append(f"  ⚠️ {r}")
    lines.append("")

    # ── Section 6: Next Commands ──
    lines.append(f"── 6. 下一步命令 ──")
    lines.append("")

    if best and best["tier"] != "skip":
        lines.append(f"  一键发布流程:   {_next_command(best['full_name'], best['tier'], best['publishability_score'])}")
        if best["tier"] == "recommended":
            lines.append(f"  生成发布包:     python run.py publish-pack {best['full_name']}")
            lines.append(f"  审核发布包:     python run.py review-pack <pack_dir>")
    lines.append("  查看审核队列:   python run.py review-queue")
    lines.append("  查看发布历史:   python run.py publish-history")
    lines.append("  完整工作台视图: python run.py dashboard")
    lines.append("  系统健康检查:   python run.py doctor")
    lines.append("  质量门检查:     python run.py quality-gate")
    lines.append("")

    # ── Section 7: Human Checklist ──
    lines.append(f"── 7. 今日人工检查清单 ──")
    lines.append("")

    checklist = []
    if best and best["tier"] in ("recommended", "watch"):
        checklist.append(f"□ 1. 通读 {best['full_name']} 的 README，确认内容质量和安全")
        checklist.append(f"□ 2. 运行 python run.py publish-flow {best['full_name']}")
        checklist.append("□ 3. 审核 publish_pack 中的 06_review_report.md")
        checklist.append("□ 4. 确认无阻断问题后，运行 python run.py approve-pack <pack_dir>")
    else:
        checklist.append("□ 1. 检查今日 Top 5 列表，手动评估候选项目")
        checklist.append("□ 2. 如果没有合格候选，等待下一轮 daily 抓取")
        checklist.append("□ 3. 检查 Quality Gate 状态，确保系统健康")

    checklist.append("□ 5. 手动复制内容到各平台发布")
    checklist.append("□ 6. 运行 python run.py mark-published <pack_dir> --platform <name>")
    checklist.append("□ 7. 记录发布的 URL 和备注（--url 和 --note）")
    checklist.append("")

    for item in checklist:
        lines.append(f"  {item}")

    lines.append("")
    lines.append(sep)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# CLI handler
# ═══════════════════════════════════════════════════════════════

def cmd_workbench(date_str: str | None = None,
                   repo_filter: str | None = None) -> int:
    print(generate_workbench(date_str=date_str, repo_filter=repo_filter))
    return 0
