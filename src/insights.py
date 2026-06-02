"""Post-publish insights layer — Phase 25.

Read-only analysis engine. Reads metrics_history and publish_history,
produces evidence-backed recommendations. Never modifies scores or state.

Every suggestion includes its evidence source: which data, which repo,
which platform, which date range.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PLATFORM_LABELS: dict[str, str] = {
    "wechat": "公众号", "xiaohongshu": "小红书",
    "douyin": "抖音", "videohao": "视频号", "geo": "GEO",
}

MIN_ENTRIES_FOR_CONFIDENCE = 3
MIN_DAYS_FOR_TREND = 7


# ═══════════════════════════════════════════════════════════════
# Data loaders (lazy import to avoid circular deps)
# ═══════════════════════════════════════════════════════════════

def _load_metrics() -> dict:
    try:
        from .metrics import load_metrics_history
        return load_metrics_history()
    except Exception:
        return {}


def _load_publish_history() -> dict:
    try:
        from .publish_history import get_publish_history
        return get_publish_history()
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
# Section 1: Overall Summary
# ═══════════════════════════════════════════════════════════════

def _section_overall(metrics: dict, pubhist: dict) -> list[str]:
    lines: list[str] = []
    lines.append("── 1. 总体表现摘要 ──")
    lines.append("")

    published_repos = set(pubhist.keys())
    metrics_repos = set(metrics.keys())
    repos_with_data = published_repos & metrics_repos
    published_no_data = published_repos - metrics_repos

    all_metric_entries = []
    for rname, entries in metrics.items():
        for e in entries:
            all_metric_entries.append({**e, "_repo": rname})

    lines.append(f"  已发布项目:     {len(published_repos)} 个")
    lines.append(f"  有表现数据:     {len(repos_with_data)} 个")

    if published_no_data:
        lines.append(f"  已发布无数据:   {len(published_no_data)} 个 "
                     f"({', '.join(sorted(published_no_data)[:3])})")

    if not all_metric_entries:
        lines.append("")
        lines.append("  ⚠️ 暂无任何表现数据，无法生成复盘建议。")
        lines.append("  依据: metrics_history 为空")
        lines.append("")
        return lines

    total_views = sum(e.get("views", 0) for e in all_metric_entries)
    avg_engagement = (sum(e.get("engagement_rate", 0) for e in all_metric_entries)
                      / len(all_metric_entries))
    avg_lead = (sum(e.get("lead_rate", 0) for e in all_metric_entries)
                / len(all_metric_entries))

    lines.append(f"  总记录数:       {len(all_metric_entries)} 条")
    lines.append(f"  总浏览量:       {total_views:,}")
    lines.append(f"  平均互动率:     {avg_engagement:.2%}")
    lines.append(f"  平均线索率:     {avg_lead:.2%}")
    lines.append(f"  依据: {len(all_metric_entries)} 条 metrics 记录")

    # Best platform by total views
    by_platform: dict[str, dict] = {}
    for e in all_metric_entries:
        p = e["platform"]
        if p not in by_platform:
            by_platform[p] = {"views": 0, "engagement": 0, "leads": 0, "count": 0}
        by_platform[p]["views"] += e.get("views", 0)
        by_platform[p]["engagement"] += e.get("engagement_rate", 0)
        by_platform[p]["leads"] += e.get("lead_rate", 0)
        by_platform[p]["count"] += 1

    for p in by_platform:
        n = by_platform[p]["count"]
        by_platform[p]["engagement"] = by_platform[p]["engagement"] / n if n else 0
        by_platform[p]["leads"] = by_platform[p]["leads"] / n if n else 0

    if by_platform:
        best_views = max(by_platform.items(), key=lambda x: x[1]["views"])
        best_eng = max(by_platform.items(), key=lambda x: x[1]["engagement"])
        pl = PLATFORM_LABELS.get(best_views[0], best_views[0])
        el = PLATFORM_LABELS.get(best_eng[0], best_eng[0])
        lines.append(f"  最高浏览平台:   {pl} ({best_views[1]['views']:,} 总浏览)")
        lines.append(f"  最高互动平台:   {el} ({best_eng[1]['engagement']:.2%})")

    # Best repo
    best_repo = max(all_metric_entries, key=lambda e: (
        e.get("engagement_rate", 0), e.get("views", 0)))
    lines.append(f"  最佳表现项目:   {best_repo['_repo']} "
                 f"(互动率 {best_repo.get('engagement_rate', 0):.2%}, "
                 f"浏览 {best_repo.get('views', 0):,})")
    lines.append("")
    return lines


# ═══════════════════════════════════════════════════════════════
# Section 2: Platform Performance
# ═══════════════════════════════════════════════════════════════

def _section_platforms(metrics: dict, pubhist: dict) -> list[str]:
    lines: list[str] = []
    lines.append("── 2. 平台表现建议 ──")
    lines.append("")

    all_entries = []
    for rname, entries in metrics.items():
        for e in entries:
            all_entries.append({**e, "_repo": rname})

    if not all_entries:
        lines.append("  暂无数据。")
        lines.append("  依据: metrics_history 为空")
        lines.append("")
        return lines

    # Aggregate per platform from BOTH metrics and publish_history
    platform_data: dict[str, dict] = {}
    for p in ["wechat", "xiaohongshu", "douyin", "videohao", "geo"]:
        metric_entries = [e for e in all_entries if e["platform"] == p]
        pub_count = sum(1 for entries in pubhist.values()
                       for e in entries if e.get("platform") == p)

        avg_eng = (sum(e.get("engagement_rate", 0) for e in metric_entries)
                   / len(metric_entries)) if metric_entries else 0
        avg_lead = (sum(e.get("lead_rate", 0) for e in metric_entries)
                    / len(metric_entries)) if metric_entries else 0
        total_views = sum(e.get("views", 0) for e in metric_entries)

        label = PLATFORM_LABELS.get(p, p)

        # Recommendation logic
        if len(metric_entries) == 0:
            recommendation = "观望 — 尚未录入表现数据"
            icon = "⏳"
            reason = f"依据: {label} 已发布 {pub_count} 次，但无表现数据录入"
        elif len(metric_entries) < MIN_ENTRIES_FOR_CONFIDENCE:
            recommendation = "观察中 — 数据不足以判断"
            icon = "👀"
            reason = (f"依据: {label} 仅 {len(metric_entries)} 条数据 "
                     f"(需 ≥{MIN_ENTRIES_FOR_CONFIDENCE} 条才能稳定判断)")
        elif avg_eng >= 0.08 and avg_lead >= 0.01:
            recommendation = "✅ 适合继续做 — 互动和线索表现均好"
            icon = "✅"
            reason = (f"依据: {label} {len(metric_entries)} 条数据, "
                     f"均互动率 {avg_eng:.2%}, 均线索率 {avg_lead:.2%}, "
                     f"总浏览 {total_views:,}")
        elif avg_eng >= 0.05:
            recommendation = "⚠️ 谨慎加码 — 互动尚可但线索偏低"
            icon = "⚠️"
            reason = (f"依据: {label} {len(metric_entries)} 条数据, "
                     f"均互动率 {avg_eng:.2%}, 均线索率 {avg_lead:.2%}")
        else:
            recommendation = "🔴 暂不建议加码 — 互动和线索均偏低"
            icon = "🔴"
            reason = (f"依据: {label} {len(metric_entries)} 条数据, "
                     f"均互动率 {avg_eng:.2%}, 均线索率 {avg_lead:.2%}")

        lines.append(f"  {icon} {label}: {recommendation}")
        lines.append(f"    {reason}")

    lines.append("")
    return lines


# ═══════════════════════════════════════════════════════════════
# Section 3: Repo Review
# ═══════════════════════════════════════════════════════════════

def _section_repos(metrics: dict, pubhist: dict) -> list[str]:
    lines: list[str] = []
    lines.append("── 3. Repo 复盘建议 ──")
    lines.append("")

    if not pubhist:
        lines.append("  暂无已发布项目。")
        lines.append("  依据: publish_history 为空")
        lines.append("")
        return lines

    all_repos = set(pubhist.keys())
    reviewed: list[dict] = []

    for repo in sorted(all_repos):
        pub_entries = pubhist[repo]
        metric_entries = metrics.get(repo, [])

        pub_platforms = [e.get("platform", "?") for e in pub_entries]
        pub_scores = [e.get("publishability_score", 0) or 0 for e in pub_entries]
        pub_types = [e.get("source_mode", "unknown") for e in pub_entries]

        metric_platforms = [e.get("platform", "?") for e in metric_entries]
        total_views = sum(e.get("views", 0) for e in metric_entries)
        avg_eng = (sum(e.get("engagement_rate", 0) for e in metric_entries)
                   / len(metric_entries)) if metric_entries else 0

        # Determine recommendations
        suggestions: list[str] = []

        # Can it be re-created?
        if total_views > 1000 and avg_eng > 0.05:
            suggestions.append("✅ 值得二创 — 互动好，可做深度/对比/系列内容")
        elif total_views > 0:
            suggestions.append("📋 可考虑二创 — 已有表现数据，可优化后再发")

        # Cross-platform re-publish?
        missing_platforms = set(["wechat", "xiaohongshu", "douyin", "videohao", "geo"]) - set(pub_platforms)
        if missing_platforms and avg_eng > 0.03:
            mp = ", ".join(PLATFORM_LABELS.get(p, p) for p in sorted(missing_platforms)[:2])
            suggestions.append(f"🔄 可换平台再发: {mp}")

        # Should it be in review list?
        if not metric_entries and len(pub_entries) > 0:
            suggestions.append("📝 已发布但无表现数据，建议录入 metrics")

        avg_score = sum(pub_scores) / len(pub_scores) if pub_scores else 0
        if avg_score > 70 and avg_eng < 0.03 and metric_entries:
            suggestions.append("⚠️ 高分低表现 — publishing_score 高但实际互动低，需警惕")

        reviewed.append({
            "repo": repo,
            "published_count": len(pub_entries),
            "metric_count": len(metric_entries),
            "total_views": total_views,
            "avg_engagement": avg_eng,
            "avg_score": avg_score,
            "platforms": pub_platforms,
            "suggestions": suggestions,
        })

    # Sort: repos with data first, then by engagement
    reviewed.sort(key=lambda r: (
        r["metric_count"] > 0,
        r["avg_engagement"],
        r["total_views"],
    ), reverse=True)

    for r in reviewed[:10]:
        pl_str = ", ".join(PLATFORM_LABELS.get(p, p) for p in r["platforms"])
        lines.append(f"  📌 {r['repo']}")
        lines.append(f"     发布: {r['published_count']} 次 ({pl_str})")
        views_part = f" | 浏览: {r['total_views']:,}" if r['metric_count'] > 0 else ""
        eng_part = f" | 互动率: {r['avg_engagement']:.2%}" if r['metric_count'] > 0 else ""
        lines.append(f"     评分: {r['avg_score']:.0f}/100{views_part}{eng_part}")
        if r["suggestions"]:
            for s in r["suggestions"]:
                lines.append(f"     {s}")
        else:
            lines.append(f"     → 暂无特别建议，继续积累数据")
        lines.append("")

    if len(reviewed) > 10:
        lines.append(f"  ... 共 {len(reviewed)} 个项目，以上展示前 10")
        lines.append("")

    lines.append("")
    return lines


# ═══════════════════════════════════════════════════════════════
# Section 4: Tomorrow's Topic Suggestions
# ═══════════════════════════════════════════════════════════════

def _section_tomorrow(metrics: dict, pubhist: dict,
                      repo_filter: str | None = None) -> list[str]:
    lines: list[str] = []
    lines.append("── 4. 明日选题建议 ──")
    lines.append("")

    if not metrics:
        lines.append("  暂无足够数据给出选题建议。")
        lines.append("  依据: metrics_history 为空")
        lines.append("  建议: 至少录入 3 条表现数据后再来看")
        lines.append("")
        return lines

    # Aggregate by source_mode (proxy for content_type)
    by_type: dict[str, dict] = {}
    for repo, pub_entries in pubhist.items():
        metric_entries = metrics.get(repo, [])
        if not metric_entries:
            continue
        source_mode = pub_entries[0].get("source_mode", "unknown") if pub_entries else "unknown"
        if source_mode not in by_type:
            by_type[source_mode] = {"count": 0, "views": 0, "engagement": 0,
                                    "leads": 0, "repos": []}
        for e in metric_entries:
            by_type[source_mode]["count"] += 1
            by_type[source_mode]["views"] += e.get("views", 0)
            by_type[source_mode]["engagement"] += e.get("engagement_rate", 0)
            by_type[source_mode]["leads"] += e.get("lead_rate", 0)
        by_type[source_mode]["repos"].append(repo)

    for ct in by_type:
        n = by_type[ct]["count"]
        by_type[ct]["engagement"] = by_type[ct]["engagement"] / n if n else 0
        by_type[ct]["leads"] = by_type[ct]["leads"] / n if n else 0

    # Also aggregate by platform for priority
    by_platform: dict[str, float] = {}
    for repo, entries in metrics.items():
        for e in entries:
            p = e["platform"]
            by_platform[p] = max(by_platform.get(p, 0), e.get("engagement_rate", 0))

    sorted_types = sorted(by_type.items(),
                          key=lambda t: t[1]["engagement"], reverse=True)

    if sorted_types:
        best = sorted_types[0]
        lines.append(f"  📈 优先选型: {best[0]}")
        lines.append(f"     依据: {best[1]['count']} 条数据, "
                     f"平均互动率 {best[1]['engagement']:.2%}, "
                     f"覆盖 {len(best[1]['repos'])} 个项目")
        lines.append(f"     示例: {', '.join(best[1]['repos'][:3])}")

        if len(sorted_types) > 1:
            worst = sorted_types[-1]
            if worst[0] != best[0]:
                lines.append(f"  📉 建议谨慎: {worst[0]}")
                lines.append(f"     依据: {worst[1]['count']} 条数据, "
                            f"平均互动率仅 {worst[1]['engagement']:.2%}")

    # Platform priority
    if by_platform:
        sorted_plat = sorted(by_platform.items(), key=lambda x: x[1], reverse=True)
        best_plat = sorted_plat[0]
        pl_label = PLATFORM_LABELS.get(best_plat[0], best_plat[0])
        lines.append(f"  📊 优先平台: {pl_label}")
        lines.append(f"     依据: 历史最高互动率 {best_plat[1]:.2%}")

    # Sample size warning
    total_entries = sum(len(v) for v in metrics.values())
    if total_entries < MIN_ENTRIES_FOR_CONFIDENCE:
        lines.append("")
        lines.append(f"  ⚠️ 样本量警告: 仅 {total_entries} 条数据, "
                    f"建议至少积累 {MIN_ENTRIES_FOR_CONFIDENCE} 条后再做方向判断")

    lines.append("")
    lines.append("  ℹ️ 以上建议不改变系统排序，仅作人工参考。")
    lines.append("")
    return lines


# ═══════════════════════════════════════════════════════════════
# Section 5: Risk Warnings
# ═══════════════════════════════════════════════════════════════

def _section_risks(metrics: dict, pubhist: dict) -> list[str]:
    lines: list[str] = []
    lines.append("── 5. 风险提示 ──")
    lines.append("")

    risks: list[str] = []

    all_entries = []
    for rname, entries in metrics.items():
        for e in entries:
            all_entries.append({**e, "_repo": rname})

    total_metric = len(all_entries)
    total_pub = sum(len(v) for v in pubhist.values())

    # 1. Small sample
    if total_metric < MIN_ENTRIES_FOR_CONFIDENCE:
        risks.append(f"⚠️ 样本过少: {total_metric} 条记录, "
                     f"需 ≥{MIN_ENTRIES_FOR_CONFIDENCE} 条才能稳定判断。"
                     f"依据: metrics_history 条目数")

    # 2. Missing data
    published_repos = set(pubhist.keys())
    metrics_repos = set(metrics.keys())
    no_data = published_repos - metrics_repos
    if no_data:
        risks.append(f"⚠️ 数据不完整: {len(no_data)} 个已发布项目无表现数据 "
                     f"({', '.join(sorted(no_data)[:3])})。"
                     f"依据: 对比 publish_history 与 metrics_history")

    # 3. Single platform bias
    platform_counts: dict[str, int] = {}
    for e in all_entries:
        platform_counts[e["platform"]] = platform_counts.get(e["platform"], 0) + 1
    single_only = [p for p, c in platform_counts.items() if c == 1]
    if single_only and total_metric < 10:
        pl = ", ".join(PLATFORM_LABELS.get(p, p) for p in single_only)
        risks.append(f"⚠️ 单次数据: {pl} 仅 1 条记录，不能过度判断。"
                     f"依据: metrics_history 平台分布")

    # 4. High engagement, low leads
    for e in all_entries:
        if e.get("engagement_rate", 0) > 0.10 and e.get("lead_rate", 0) < 0.005:
            risks.append(f"🔍 高互动低线索: {e['_repo']} → {e['platform']} "
                        f"(互动率 {e['engagement_rate']:.2%}, 线索率 {e['lead_rate']:.2%})。"
                        f"依据: metrics_history 单条记录")
            break  # One example is enough

    # 5. High leads, low views
    for e in all_entries:
        if e.get("lead_rate", 0) > 0.03 and e.get("views", 0) < 200:
            risks.append(f"🔍 高线索低阅读: {e['_repo']} → {e['platform']} "
                        f"(线索率 {e['lead_rate']:.2%}, 浏览 {e.get('views', 0)}). "
                        f"可能样本有偏，需更多数据验证。"
                        f"依据: metrics_history 单条记录")
            break

    # 6. High score, low performance
    for repo, pub_entries in pubhist.items():
        metric_entries = metrics.get(repo, [])
        if not metric_entries:
            continue
        avg_pub_score = sum(e.get("publishability_score", 0) or 0
                           for e in pub_entries) / len(pub_entries)
        avg_eng = sum(e.get("engagement_rate", 0)
                     for e in metric_entries) / len(metric_entries)
        if avg_pub_score > 70 and avg_eng < 0.03:
            risks.append(f"⚠️ {repo}: publishability_score 高 ({avg_pub_score:.0f}) "
                        f"但互动率低 ({avg_eng:.2%})，scoring 可能需人工校准。"
                        f"依据: 对比 publish_history.score 与 metrics_history.engagement_rate")
            break

    if not risks:
        lines.append("  ✅ 当前无明显风险。")
    else:
        for r in risks:
            lines.append(f"  {r}")

    lines.append("")
    return lines


# ═══════════════════════════════════════════════════════════════
# Core generator
# ═══════════════════════════════════════════════════════════════

def generate_insights(repo: str | None = None) -> str:
    """Generate the full post-publish insights report."""
    metrics = _load_metrics()
    pubhist = _load_publish_history()

    # Filter by repo if specified
    if repo:
        rkey = repo.strip().lower()
        metrics = {rkey: metrics.get(rkey, [])} if rkey in metrics else {}
        pubhist = {rkey: pubhist.get(rkey, [])} if rkey in pubhist else {}

    sep = "=" * 64
    lines: list[str] = []
    lines.append(sep)
    title = f"  AI GitHub Blogger — Post-Publish Insights"
    if repo:
        title += f" ({repo})"
    lines.append(title)
    lines.append(sep)
    lines.append("")

    # Build all 5 sections
    lines.extend(_section_overall(metrics, pubhist))
    lines.extend(_section_platforms(metrics, pubhist))
    lines.extend(_section_repos(metrics, pubhist))
    lines.extend(_section_tomorrow(metrics, pubhist, repo_filter=repo))
    lines.extend(_section_risks(metrics, pubhist))

    lines.append(sep)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Workbench / Dashboard integration helpers
# ═══════════════════════════════════════════════════════════════

def insights_summary_for_workbench() -> list[str]:
    """Compact insights section for workbench output."""
    metrics = _load_metrics()

    all_entries = []
    for rname, entries in metrics.items():
        for e in entries:
            all_entries.append({**e, "_repo": rname})

    lines: list[str] = []

    if not all_entries:
        lines.append("  暂无发布后数据，请先使用 record-metrics 录入。")
        lines.append("  依据: metrics_history 为空")
        return lines

    # Aggregate by type
    pubhist = _load_publish_history()
    by_type: dict[str, dict] = {}
    for repo, pub_entries in pubhist.items():
        metric_entries = metrics.get(repo, [])
        if not metric_entries:
            continue
        ct = pub_entries[0].get("source_mode", "unknown") if pub_entries else "unknown"
        if ct not in by_type:
            by_type[ct] = {"count": 0, "engagement": 0}
        for e in metric_entries:
            by_type[ct]["count"] += 1
            by_type[ct]["engagement"] += e.get("engagement_rate", 0)

    for ct in by_type:
        n = by_type[ct]["count"]
        by_type[ct]["engagement"] = by_type[ct]["engagement"] / n if n else 0

    sorted_types = sorted(by_type.items(),
                          key=lambda t: t[1]["engagement"], reverse=True)

    if sorted_types:
        best = sorted_types[0]
        lines.append(f"  📈 高互动方向: {best[0]} "
                    f"(均互动率 {best[1]['engagement']:.2%}, {best[1]['count']} 条)")
        lines.append(f"     依据: metrics_history 按 content_type 聚合")
        if len(sorted_types) > 1:
            worst = sorted_types[-1]
            if worst[0] != best[0]:
                lines.append(f"  📉 低互动方向: {worst[0]} "
                            f"(均互动率 {worst[1]['engagement']:.2%})")

    # Best platform
    by_platform: dict[str, float] = {}
    for e in all_entries:
        p = e["platform"]
        if p not in by_platform:
            by_platform[p] = 0
        by_platform[p] += e.get("engagement_rate", 0)
    for p in by_platform:
        n = sum(1 for e in all_entries if e["platform"] == p)
        by_platform[p] = by_platform[p] / n if n else 0

    if by_platform:
        best_p = max(by_platform.items(), key=lambda x: x[1])
        lines.append(f"  📊 优先平台: {PLATFORM_LABELS.get(best_p[0], best_p[0])} "
                    f"(均互动率 {best_p[1]:.2%})")
        lines.append(f"     依据: metrics_history 按 platform 聚合")

    # Risk shorthand
    total_entries = len(all_entries)
    if total_entries < MIN_ENTRIES_FOR_CONFIDENCE:
        lines.append(f"  ⚠️ 仅 {total_entries} 条数据，建议积累更多后再做方向判断")
        lines.append(f"     依据: metrics_history 总记录数 < {MIN_ENTRIES_FOR_CONFIDENCE}")

    # Repo re-create suggestions
    repos_with_data = [(r, sum(e.get("engagement_rate", 0)
                     for e in entries) / len(entries))
                     for r, entries in metrics.items() if entries]
    repos_with_data.sort(key=lambda x: x[1], reverse=True)
    if repos_with_data:
        best_repo = repos_with_data[0]
        if best_repo[1] > 0.05:
            lines.append(f"  🔄 值得二创: {best_repo[0]} "
                        f"(互动率 {best_repo[1]:.2%})")
            lines.append(f"     依据: metrics_history 单项目表现")

    return lines


def insights_trend_for_dashboard() -> list[str]:
    """Compact trend summary for dashboard integration."""
    metrics = _load_metrics()

    all_entries = []
    for rname, entries in metrics.items():
        for e in entries:
            all_entries.append({**e, "_repo": rname})

    lines: list[str] = []

    if not all_entries:
        lines.append("  暂无表现数据。")
        return lines

    total_entries = len(all_entries)
    total_repos = len(set(e["_repo"] for e in all_entries))
    total_views = sum(e.get("views", 0) for e in all_entries)
    avg_eng = sum(e.get("engagement_rate", 0) for e in all_entries) / total_entries
    avg_lead = sum(e.get("lead_rate", 0) for e in all_entries) / total_entries

    lines.append(f"  {total_repos} 个项目, {total_entries} 条记录, "
                f"总浏览 {total_views:,}")
    lines.append(f"  均互动率 {avg_eng:.2%} | 均线索率 {avg_lead:.2%}")

    # Trend: entries over time (last 30 days)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=30)).isoformat()
    recent = [e for e in all_entries
              if e.get("recorded_at", "")[:10] >= cutoff[:10]]
    if recent:
        lines.append(f"  近 30 天: {len(recent)} 条记录")

    lines.append(f"  依据: metrics_history ({total_entries} 条)")

    return lines


# ═══════════════════════════════════════════════════════════════
# CLI handler
# ═══════════════════════════════════════════════════════════════

def cmd_insights(repo: str | None = None) -> int:
    """Print the insights report. Always returns 0 (read-only)."""
    print(generate_insights(repo=repo))
    return 0
