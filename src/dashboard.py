"""Daily Dashboard — Phase 22.

Aggregates existing pipeline data into a single read-only overview:
  - Today's Top 5 candidates (from top5 JSON)
  - Publish status & review judgment
  - Next action suggestions
  - Recent publish history
  - System health (doctor + quality gate)
  - Pipeline stats

Zero new dependencies. Read-only. No platform APIs.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date as dt_date, datetime, timedelta, timezone
from pathlib import Path

from .config import REPORTS_DIR, STATE_DIR, CACHE_DIR, PUBLISH_PACKS_DIR

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PUB_A = 75
PUB_B = 60
PUB_C = 40


# ═══════════════════════════════════════════════════════════════
# Internal data loaders
# ═══════════════════════════════════════════════════════════════

def _load_top5(date_str: str, reports_dir: Path | None = None) -> list[dict]:
    """Load today's top5 JSON. Returns [] on missing or corrupt file."""
    rdir = reports_dir or REPORTS_DIR
    path = rdir / f"top5_{date_str}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _load_quality_gate_verdict(reports_dir: Path | None = None) -> dict:
    """Extract quality gate verdict from the latest system_quality_report_v8.md.

    Avoids running the full benchmark suite (~30s) by regex-parsing the
    pre-existing report (~5ms).
    """
    rdir = reports_dir or REPORTS_DIR
    path = rdir / "system_quality_report_v8.md"
    result = {"verdict": "unknown", "score": "N/A", "passed": "?", "total": "?",
              "blocking": 0}

    if not path.exists():
        return result

    try:
        text = path.read_text("utf-8")
    except Exception:
        return result

    # Final Verdict: **PASS**  or  | VERDICT | PASS |
    m = re.search(r"(?:Final Verdict|VERDICT).*?(PASS|CONDITIONAL_PASS|FAIL)", text)
    if m:
        result["verdict"] = m.group(1)

    # | Adjusted Score | 97.3/100 |  or  Adjusted Score: 97.3/100
    m = re.search(r"Adjusted Score.*?([\d.]+)/100", text)
    if m:
        result["score"] = m.group(1)

    # | Passed | 15/15 |  or  Passed: 15/15
    m = re.search(r"Passed.*?(\d+)/(\d+)", text)
    if m:
        result["passed"] = m.group(1)
        result["total"] = m.group(2)

    # Blocking issues: 0
    m = re.search(r"blocking_issues.*?:\s*(\d+)", text, re.IGNORECASE)
    if m:
        result["blocking"] = int(m.group(1))

    return result


def _compute_historical_trends(days: int = 7,
                               reports_dir: Path | None = None) -> dict:
    """Scan past N days of top5 JSONs for trend data."""
    rdir = reports_dir or REPORTS_DIR
    today = dt_date.today()
    total_candidates = 0
    total_pub_score = 0.0
    days_with_top5 = 0

    for i in range(days):
        day = today - timedelta(days=i)
        day_str = day.isoformat()
        data = _load_top5(day_str, reports_dir=rdir)
        if data:
            days_with_top5 += 1
            total_candidates += len(data)
            total_pub_score += sum(r.get("publishability_score", 0) for r in data)

    avg_pub = round(total_pub_score / max(1, total_candidates), 1)

    # Count publishes this week from publish_history
    from .publish_history import get_publish_history
    history = get_publish_history()
    published_count = 0
    week_ago = (today - timedelta(days=days)).isoformat()
    for entries in history.values():
        for entry in entries:
            at = entry.get("published_at", "")
            if at and at[:10] >= week_ago:
                published_count += 1

    return {
        "total_candidates": total_candidates,
        "avg_publishability": avg_pub,
        "published_this_week": published_count,
        "days_with_top5": days_with_top5,
    }


def _collect_doctor_checks(project_root: Path | None = None,
                           state_dir: Path | None = None,
                           cache_dir: Path | None = None,
                           reports_dir: Path | None = None) -> dict[str, str]:
    """Lightweight filesystem-only health checks. No network, no benchmarks."""
    root = project_root or PROJECT_ROOT
    sdir = state_dir or STATE_DIR
    cdir = cache_dir or CACHE_DIR
    rdir = reports_dir or REPORTS_DIR

    checks = {}

    # Python version
    checks["python"] = "pass" if sys.version_info >= (3, 10) else "warn"

    # .env file
    checks["env_file"] = "pass" if (root / ".env").exists() else "warn"

    # GITHUB_TOKEN
    gh_token = os.getenv("GITHUB_TOKEN") or ""
    checks["github_token"] = "pass" if gh_token else "warn"

    # LLM_API_KEY
    llm_key = os.getenv("LLM_API_KEY") or ""
    checks["llm_key"] = "pass" if llm_key else "warn"

    # data/state writable
    try:
        test_file = sdir / ".dash_tmp"
        test_file.write_text("x", encoding="utf-8")
        test_file.unlink()
        checks["state_writable"] = "pass"
    except Exception:
        checks["state_writable"] = "fail"

    # data/cache writable
    try:
        test_file = cdir / ".dash_tmp"
        test_file.write_text("x", encoding="utf-8")
        test_file.unlink()
        checks["cache_writable"] = "pass"
    except Exception:
        checks["cache_writable"] = "fail"

    # Latest daily report
    reports = sorted(rdir.glob("daily_report_*.md")) if rdir.exists() else []
    checks["daily_report"] = "pass" if reports else "warn"

    return checks


# ═══════════════════════════════════════════════════════════════
# Display helpers
# ═══════════════════════════════════════════════════════════════

def _needs_human_review(publishability_score: float) -> tuple[bool, str]:
    """Determine if a candidate needs human review.

    Thresholds (aligned with cmd_daily_workflow):
      >= 75 -> no review needed
      60-74 -> review recommended (marginal)
      < 60  -> review required
    """
    if publishability_score >= PUB_A:
        return False, ""
    elif publishability_score >= PUB_B:
        return True, f"可发布性 {publishability_score:.0f}/100 在 {PUB_B}-{PUB_A - 1} 边界，建议审核"
    else:
        return True, f"可发布性 {publishability_score:.0f}/100 未达标（<{PUB_B}），需人工审核"


def _suggest_platforms(repo: dict) -> list[str]:
    """Rule-based platform suggestions from content_type and topics."""
    content_type = repo.get("content_type", "runnable_project")
    topics = [t.lower() for t in repo.get("topics", [])]

    if content_type in ("awesome_list", "resource_collection"):
        return ["公众号", "GEO"]
    if content_type == "tutorial_guide":
        return ["公众号", "小红书"]
    if content_type == "framework_platform":
        return ["公众号", "GEO"]

    # runnable_project / default
    platforms = ["公众号", "小红书", "抖音", "视频号", "GEO"]
    return platforms


def _next_action(repo: dict, is_published: bool) -> str:
    """Suggest the single most actionable CLI command for a repo."""
    full_name = repo.get("full_name", "owner/repo")
    pub = repo.get("publishability_score", 0) or 0

    if is_published:
        return f"已发布，可追加平台: python run.py mark-published <pack_dir> --platform <name>"

    if pub >= PUB_A:
        return f"python run.py publish-flow {full_name}"
    elif pub >= PUB_B:
        return f"python run.py publish-pack {full_name}"
    elif pub >= PUB_C:
        return f"python run.py review-pack <pack_dir>  # {full_name}"
    else:
        return f"# {full_name} 可发布性 {pub:.0f}<{PUB_C}，建议跳过"


# ═══════════════════════════════════════════════════════════════
# Core formatter
# ═══════════════════════════════════════════════════════════════

def generate_dashboard(date_str: str | None = None) -> str:
    """Generate the complete dashboard Markdown string."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    from .publish_history import is_published, get_publish_history

    top5 = _load_top5(date_str)
    qg = _load_quality_gate_verdict()
    trends = _compute_historical_trends()
    doctor = _collect_doctor_checks()

    lines: list[str] = []
    sep = "=" * 64
    sub = "-" * 32

    lines.append(sep)
    lines.append(f"  AI GitHub Blogger — Daily Dashboard ({date_str})")
    lines.append(sep)
    lines.append("")

    # ── 1. Today's Top Candidates ──
    lines.append(f"── 1. 今日最佳候选 (Top {len(top5)}) ──")
    lines.append("")

    if not top5:
        lines.append("  今日暂无 Top 5 候选数据。")
        lines.append(f"  请先运行: python run.py daily")
        lines.append("")
    else:
        # Table header
        header = f"  {'#':<3} {'项目':<40} {'可发布性':<8} {'选题分':<7} {'Stars':<8} {'类型':<16} {'适合平台':<24} {'状态'}"
        lines.append(header)
        lines.append(f"  {'-' * (len(header) - 2)}")

        for i, repo in enumerate(top5, 1):
            name = repo.get("full_name", "?")
            pub = repo.get("publishability_score", 0) or 0
            score = repo.get("score", 0) or 0
            stars = repo.get("stars", 0) or 0
            ctype = repo.get("content_type", "?")
            platforms = _suggest_platforms(repo)
            published = is_published(name)

            stars_str = f"{stars:,}" if stars else "?"
            pub_str = f"{pub:.0f}/100" if pub else "N/A"
            score_str = f"{score:.0f}" if score else "N/A"
            plat_str = ",".join(platforms[:3])
            if len(platforms) > 3:
                plat_str += ",..."

            if published:
                status = "已发布，跳过"
            elif pub >= PUB_A:
                status = "✅ 推荐"
            elif pub >= PUB_B:
                status = "⚠️ 可观察"
            elif pub >= PUB_C:
                status = "📋 待审核"
            else:
                status = "❌ 不推荐"

            lines.append(
                f"  {i:<3} {name:<40} {pub_str:<8} {score_str:<7} {stars_str:<8} "
                f"{ctype:<16} {plat_str:<24} {status}"
            )

        lines.append("")

    # ── 2. Review Judgment ──
    lines.append(f"── 2. 审核判断 ──")
    lines.append("")

    if not top5:
        lines.append("  无候选数据。")
        lines.append("")
    else:
        review_header = f"  {'项目':<40} {'已发布':<8} {'需审核':<8} {'原因'}"
        lines.append(review_header)
        lines.append(f"  {'-' * (len(review_header) - 2)}")

        for repo in top5:
            name = repo.get("full_name", "?")
            pub = repo.get("publishability_score", 0) or 0
            published = is_published(name)

            if published:
                published_str = "是"
                needs_str = "N/A"
                reason = "已发布"
            else:
                published_str = "否"
                needs, reason = _needs_human_review(pub)
                needs_str = "是" if needs else "否"

            lines.append(f"  {name:<40} {published_str:<8} {needs_str:<8} {reason}")

        lines.append("")

    # ── 3. Next Actions ──
    lines.append(f"── 3. 下一步建议 ──")
    lines.append("")

    actions = set()
    # Always-available commands
    actions.add("python run.py review-queue")
    actions.add("python run.py publish-history")

    if top5:
        for repo in top5:
            name = repo.get("full_name", "")
            published = is_published(name)
            actions.add(_next_action(repo, published))

    for a in sorted(actions):
        lines.append(f"  {a}")

    lines.append("")
    lines.append(f"  doctor:      python run.py doctor")
    lines.append(f"  quality-gate: python run.py quality-gate")
    lines.append("")

    # ── 4. Recent Publish Summary ──
    lines.append(f"── 4. 最近发布摘要 ──")
    lines.append("")

    history = get_publish_history()
    if not history:
        lines.append("  暂无发布记录。")
        lines.append("")
    else:
        all_entries = []
        for repo_name, entries in history.items():
            for e in entries:
                all_entries.append({**e, "_repo": repo_name})

        all_entries.sort(key=lambda e: e.get("published_at", ""), reverse=True)

        # This week count
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        week_count = sum(1 for e in all_entries
                         if e.get("published_at", "") >= week_ago)

        lines.append(f"  本周发布: {week_count} 条  |  历史总计: {len(all_entries)} 条")
        lines.append("")

        recent = all_entries[:5]
        for i, e in enumerate(recent, 1):
            at = e.get("published_at", "?")[:10]
            platform = e.get("platform", "?")
            repo = e.get("_repo", "?")
            url = e.get("url") or ""
            url_str = f" → {url}" if url else ""
            lines.append(f"  {i}. {at}  {repo}  → {platform}{url_str}")

        lines.append("")

    # ── 5. System Health ──
    lines.append(f"── 5. 系统健康 ──")
    lines.append("")

    # Doctor summary
    n_pass = sum(1 for v in doctor.values() if v == "pass")
    n_total = len(doctor)
    n_warn = sum(1 for v in doctor.values() if v == "warn")
    n_fail = sum(1 for v in doctor.values() if v == "fail")
    icon = "✅" if n_fail == 0 else "❌"
    lines.append(f"  Doctor: {icon} {n_pass}/{n_total} pass",)
    if n_warn:
        warns = [k for k, v in doctor.items() if v == "warn"]
        lines.append(f"  Warnings: {', '.join(warns)}")
    if n_fail:
        fails = [k for k, v in doctor.items() if v == "fail"]
        lines.append(f"  Failed: {', '.join(fails)}")

    qg_icon = {"PASS": "✅", "CONDITIONAL_PASS": "⚠️", "FAIL": "❌"}.get(
        qg["verdict"], "❓")
    lines.append(f"  Quality Gate: {qg_icon} {qg['verdict']} "
                 f"({qg['score']}/100, {qg['passed']}/{qg['total']} conditions)")

    if qg.get("blocking", 0) > 0:
        lines.append(f"  ⚠️ Blocking issues: {qg['blocking']}")

    lines.append("")

    # Trend summary
    lines.append(f"  7 天趋势:")
    lines.append(f"    平均可发布性: {trends['avg_publishability']}/100")
    lines.append(f"    候选项目数:   {trends['total_candidates']}")
    lines.append(f"    发布次数:     {trends['published_this_week']}")
    lines.append(f"    有数据天数:   {trends['days_with_top5']}/7")
    lines.append("")

    # ── 6. Pipeline Stats ──
    lines.append(f"── 6. 管线统计 ──")
    lines.append("")

    # Count items from seen_repos / generated_repos
    seen_file = STATE_DIR / "seen_repos.json"
    gen_file = STATE_DIR / "generated_repos.json"
    seen_count = 0
    gen_count = 0
    try:
        if seen_file.exists():
            seen_data = json.loads(seen_file.read_text("utf-8"))
            seen_count = len(seen_data) if isinstance(seen_data, dict) else 0
    except Exception:
        pass
    try:
        if gen_file.exists():
            gen_data = json.loads(gen_file.read_text("utf-8"))
            gen_count = len(gen_data) if isinstance(gen_data, dict) else 0
    except Exception:
        pass

    publish_pack_count = len(list(PUBLISH_PACKS_DIR.iterdir())) if PUBLISH_PACKS_DIR.exists() else 0
    report_count = len(list(REPORTS_DIR.glob("top5_*.json"))) if REPORTS_DIR.exists() else 0

    lines.append(f"  累计发现:   {seen_count} 个项目")
    lines.append(f"  已生成内容: {gen_count} 个内容包")
    lines.append(f"  发布包:     {publish_pack_count} 个")
    lines.append(f"  日报天数:   {report_count} 天")
    lines.append("")

    # ── 7. Post-Publish Metrics Summary (Phase 24) ──
    lines.append(f"── 7. 发布后表现摘要 ──")
    lines.append("")

    try:
        from .metrics import summarize_metrics
        ms = summarize_metrics()
    except Exception:
        ms = {"entry_count": 0}

    if ms.get("entry_count", 0) == 0:
        lines.append("  暂无发布后表现数据。")
        lines.append("  请使用 record-metrics 录入:")
        lines.append("    python run.py record-metrics <owner/repo> --platform wechat --views 100 --likes 5")
    else:
        lines.append(f"  已录入项目:   {ms['repo_count']} 个")
        lines.append(f"  已录入平台:   {ms['platform_count']} 个")
        lines.append(f"  总记录数:     {ms['entry_count']} 条")

        if ms.get("best_views"):
            bv = ms["best_views"]
            lines.append(f"  最高浏览:     {bv['views']:,} ({bv['repo']} → {bv['platform']})")
        if ms.get("best_engagement"):
            be = ms["best_engagement"]
            lines.append(f"  最高互动率:   {be['rate']:.2%} ({be['repo']} → {be['platform']})")
        if ms.get("best_lead"):
            bl = ms["best_lead"]
            lines.append(f"  最高线索率:   {bl['rate']:.2%} ({bl['repo']} → {bl['platform']})")

        if ms.get("recent_entries"):
            lines.append("")
            lines.append("  最近 3 条:")
            for i, e in enumerate(ms["recent_entries"][:3], 1):
                lines.append(f"    {i}. {e['_repo']} → {e['platform']} "
                            f"(浏览 {e.get('views', 0):,}, "
                            f"互动率 {e.get('engagement_rate', 0):.2%}, "
                            f"线索率 {e.get('lead_rate', 0):.2%})")

    lines.append("")

    # ── 8. Post-Publish Insights Trend (Phase 25) ──
    lines.append(f"── 8. 历史表现趋势摘要 ──")
    lines.append("")

    try:
        from .insights import insights_trend_for_dashboard
        trend_lines = insights_trend_for_dashboard()
        lines.extend(trend_lines)
    except Exception:
        lines.append("  趋势数据暂不可用。")
        lines.append("  依据: insights 模块加载失败")

    lines.append("")

    lines.append(sep)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# CLI handler
# ═══════════════════════════════════════════════════════════════

def cmd_dashboard() -> int:
    """Print the daily dashboard to stdout. Always returns 0 (read-only)."""
    print(generate_dashboard())
    return 0
