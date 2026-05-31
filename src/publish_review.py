"""Publish review & human editing loop — Phase 18.

Provides 4 commands on top of Phase 17 publish packs:
  - review-pack: comprehensive review report
  - approve-pack: human approval with safety gates
  - reject-pack: rejection with reason
  - revise-pack: revision notes only (no auto-modification)

State machine (one-way):
  review → approved (terminal) — cannot reject/revise after
  review → rejected (terminal) — cannot approve after
  review → revision_notes (repeatable)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# Risk phrases — Phase 18 extensions
# ═════════════════════════════════════════════════════════════════════════════

PHASE18_RISK_PHRASES = [
    ("保证排名", "虚假承诺，无法保证SEO/GEO排名"),
    ("保证询盘", "虚假承诺，无法保证商业询盘"),
    ("保证 AI 引用", "虚假承诺，无法保证LLM引用"),
    ("万能爬虫", "误导性表达，爬虫不可能万能"),
    ("绕过风控", "危险表达，暗示可违法绕过安全措施"),
    ("绕过反爬", "危险表达，暗示可违法绕过反爬"),
    ("绕过登录", "危险表达，暗示可违法绕过认证"),
    ("全自动发布", "误导性表达，暗示无需人工的自动发布"),
    ("任何网站都能", "过于绝对，应改为'大多数公开网页'"),
    ("绝对可以", "过于绝对，需改为合理推断"),
    ("3秒把全网变文档", "夸大速度+能力范围"),
    ("100% 自动化", "过于绝对，技术总有边界"),
]

PHASE18_BANNED_KEYWORDS = [
    "绕过验证码",
    "自动绕过",
    "万能工具",
    "保证收益",
    "零风险",
    "无需人工",
    "无人值守",
    "批量注册",
    "刷量",
    "自动化骚扰",
]

# ═════════════════════════════════════════════════════════════════════════════
# Data classes
# ═════════════════════════════════════════════════════════════════════════════


@dataclass
class FileCheckResult:
    """Result of checking a single file in a publish pack."""
    status: str  # "pass" | "needs_revision" | "fail"
    score: int  # 0-100
    custom_issues: list[str] = field(default_factory=list)
    custom_suggestions: list[str] = field(default_factory=list)


@dataclass
class ReviewReport:
    """Top-level review report for a publish pack."""
    verdict: str  # "ready" | "needs_revision" | "rejected"
    overall_score: int
    file_checks: dict[str, FileCheckResult] = field(default_factory=dict)
    risk_issues: list[str] = field(default_factory=list)
    risk_blocking_count: int = 0
    cta_issues: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    revision_suggestions: list[str] = field(default_factory=list)


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def review_pack(pack_dir: str) -> ReviewReport:
    """Scan a publish pack and produce a comprehensive review report.

    Generates 06_review_report.md in the pack directory.
    Appends to manifest review_history.
    """
    pack = Path(pack_dir)
    manifest = _load_pack_manifest(pack)
    file_checks: dict[str, FileCheckResult] = {}
    blocking_issues: list[str] = []
    risk_issues: list[str] = []
    cta_issues: list[str] = []
    revision_suggestions: list[str] = []
    risk_blocking_count = 0

    # Files expected in a publish pack (from Phase 17)
    expected_files = {
        "01_wechat_ready.md": ("wechat", _check_wechat_article),
        "02_xiaohongshu_ready.md": ("xiaohongshu", _check_xiaohongshu),
        "03_video_script_ready.md": ("video", _check_video_script),
        "04_review_checklist.md": ("checklist", _check_review_checklist),
        "05_next_actions.md": ("next_actions", _check_next_actions),
        "README.md": ("readme", _check_readme),
    }

    for fname, (platform, checker) in expected_files.items():
        fpath = pack / fname
        if not fpath.exists():
            issue = f"缺少文件: {fname}"
            file_checks[fname] = FileCheckResult(
                status="fail", score=0,
                custom_issues=[issue],
                custom_suggestions=[f"重新生成发布包以包含 {fname}"],
            )
            blocking_issues.append(issue)
            continue

        content = fpath.read_text(encoding="utf-8")
        result = checker(content)

        # Cross-cutting: risk boundary check
        risk_findings = _check_risk_boundary(content)
        if risk_findings:
            result.custom_issues.extend(risk_findings)
            for finding in risk_findings:
                risk_issues.append(f"{fname}: {finding}")
                if _is_blocking_risk(finding):
                    risk_blocking_count += 1
                    blocking_issues.append(f"{fname}: [阻断] {finding}")

        # Cross-cutting: CTA check for platform files
        if platform in ("wechat", "xiaohongshu", "video"):
            cta_ok, cta_detail = _check_cta(content, platform)
            if not cta_ok:
                result.custom_issues.append(cta_detail)
                cta_issues.append(f"{fname}: {cta_detail}")

        # Downgrade status if needed
        if result.status == "pass" and result.custom_issues:
            result.status = "needs_revision"
        if any(_is_blocking_risk(i) for i in result.custom_issues):
            result.status = "fail"

        file_checks[fname] = result

    # Aggregate revision suggestions
    for fname, check in file_checks.items():
        for suggestion in check.custom_suggestions:
            revision_suggestions.append(f"{fname}: {suggestion}")

    # Determine verdict
    if blocking_issues:
        verdict = "rejected"
    elif any(c.status == "fail" for c in file_checks.values()):
        verdict = "rejected"
    elif any(c.status == "needs_revision" for c in file_checks.values()):
        verdict = "needs_revision"
    else:
        verdict = "ready"

    # Overall score
    scores = [c.score for c in file_checks.values()]
    overall_score = sum(scores) // len(scores) if scores else 0

    report = ReviewReport(
        verdict=verdict,
        overall_score=overall_score,
        file_checks=file_checks,
        risk_issues=risk_issues,
        risk_blocking_count=risk_blocking_count,
        cta_issues=cta_issues,
        blocking_issues=blocking_issues,
        revision_suggestions=revision_suggestions,
    )

    # Write 06_review_report.md
    report_md = _render_review_report(report, manifest)
    (pack / "06_review_report.md").write_text(report_md, encoding="utf-8")

    # Append to review_history
    _append_review_history(pack, {
        "action": "review",
        "verdict": verdict,
        "overall_score": overall_score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return report


def approve_pack(pack_dir: str) -> dict:
    """Approve a publish pack for publishing.

    Gates:
      1. State gate: must not already be approved or rejected
      2. Quality gate: review must yield verdict=ready + blocking_issues=0

    Updates manifest and generates 07_handoff_summary.md.
    """
    pack = Path(pack_dir)
    manifest = _load_pack_manifest(pack)

    if manifest is None:
        return {"status": "blocked", "reason": "manifest 文件不存在",
                "human_review_status": None}

    # State gate 1: already approved
    current_status = manifest.get("human_review_status", "")
    if current_status == "approved":
        return {"status": "blocked", "reason": "该包已批准，不可重复批准",
                "human_review_status": "approved"}

    # State gate 2: already rejected
    if current_status == "rejected":
        return {"status": "blocked", "reason": "该包已拒绝，不可再批准",
                "human_review_status": "rejected"}

    # Quality gate: run review
    report = review_pack(str(pack))
    if report.verdict != "ready" or report.blocking_issues:
        reason = f"质量闸门未通过: verdict={report.verdict}, blocking_issues={len(report.blocking_issues)}"
        if report.blocking_issues:
            reason += f" ({'; '.join(report.blocking_issues[:3])})"
        return {"status": "blocked", "reason": reason,
                "human_review_status": current_status or None}

    # Approve
    now = datetime.now(timezone.utc).isoformat()
    _update_pack_manifest(pack, {
        "human_review_status": "approved",
        "approved_at": now,
        "approved_by": "human",
    })

    # Generate 07_handoff_summary.md
    handoff = _render_handoff_summary(manifest, now)
    (pack / "07_handoff_summary.md").write_text(handoff, encoding="utf-8")

    _append_review_history(pack, {
        "action": "approve",
        "status": "approved",
        "timestamp": now,
    })

    return {"status": "ok", "human_review_status": "approved",
            "approved_at": now, "approved_by": "human"}


def reject_pack(pack_dir: str, reason: str) -> dict:
    """Reject a publish pack with a reason.

    Gates:
      1. Parameter gate: reason must be non-empty
      2. State gate: must not already be approved

    Preserves all existing files, generates 07_rejection_record.md.
    """
    pack = Path(pack_dir)

    # Parameter gate
    if not reason or not reason.strip():
        return {"status": "blocked", "reason": "拒绝原因不能为空",
                "human_review_status": None}

    manifest = _load_pack_manifest(pack)
    if manifest is None:
        return {"status": "blocked", "reason": "manifest 文件不存在",
                "human_review_status": None}

    # State gate: already approved
    current_status = manifest.get("human_review_status", "")
    if current_status == "approved":
        return {"status": "blocked", "reason": "该包已批准，不可再拒绝",
                "human_review_status": "approved"}

    # Reject
    now = datetime.now(timezone.utc).isoformat()
    _update_pack_manifest(pack, {
        "human_review_status": "rejected",
        "rejected_at": now,
        "rejected_reason": reason.strip(),
    })

    # Generate 07_rejection_record.md
    record = _render_rejection_record(manifest, reason.strip(), now)
    (pack / "07_rejection_record.md").write_text(record, encoding="utf-8")

    _append_review_history(pack, {
        "action": "reject",
        "status": "rejected",
        "reason": reason.strip(),
        "timestamp": now,
    })

    return {"status": "ok", "human_review_status": "rejected",
            "rejected_at": now, "rejected_reason": reason.strip()}


def revise_pack(pack_dir: str) -> dict:
    """Generate revision notes for a publish pack.

    Gate: must not already be approved.

    NEVER modifies 01/02/03/04/05 content files — only generates 07_revision_notes.md.
    """
    pack = Path(pack_dir)
    manifest = _load_pack_manifest(pack)

    if manifest is None:
        return {"status": "blocked", "reason": "manifest 文件不存在",
                "human_review_status": None}

    # State gate: already approved
    current_status = manifest.get("human_review_status", "")
    if current_status == "approved":
        return {"status": "blocked", "reason": "该包已批准，不可再改稿",
                "human_review_status": "approved"}

    # Run review to gather issues
    report = review_pack(str(pack))

    # Collect all issues per file
    all_issues: dict[str, list[str]] = {}
    for fname, check in report.file_checks.items():
        if check.custom_issues or check.custom_suggestions:
            all_issues[fname] = check.custom_issues + check.custom_suggestions

    # Generate revision notes — NO modification to content files
    now = datetime.now(timezone.utc).isoformat()
    notes = _render_revision_notes(manifest, all_issues, report, now)
    (pack / "07_revision_notes.md").write_text(notes, encoding="utf-8")

    _append_review_history(pack, {
        "action": "revise",
        "status": "revision_notes",
        "timestamp": now,
    })

    return {"status": "ok", "notes_file": "07_revision_notes.md",
            "issues_count": sum(len(v) for v in all_issues.values())}


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════


def _load_pack_manifest(pack: Path) -> dict | None:
    """Load the publish pack manifest JSON, or None if missing."""
    manifest_path = pack / "00_publish_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _update_pack_manifest(pack: Path, updates: dict) -> None:
    """Merge updates into the manifest and write back."""
    manifest = _load_pack_manifest(pack) or {}
    manifest.update(updates)
    (pack / "00_publish_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_review_history(pack: Path, entry: dict) -> None:
    """Append an entry to manifest.review_history array."""
    manifest = _load_pack_manifest(pack) or {}
    history = manifest.get("review_history", [])
    if not isinstance(history, list):
        history = []
    history.append(entry)
    manifest["review_history"] = history
    (pack / "00_publish_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# ═════════════════════════════════════════════════════════════════════════════
# Platform checkers
# ═════════════════════════════════════════════════════════════════════════════


def _check_wechat_article(content: str) -> FileCheckResult:
    """Check 公众号文章: title, pain-point, project explanation, tech breakdown,
    personal thread, CTA, risk boundary."""
    issues = []
    suggestions = []
    score = 100

    # Title check — any ## heading within first 30 lines counts
    lines = content.split("\n")
    has_title = False
    for line in lines[:30]:
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("## 发布前"):
            has_title = True
            break
    # Fallback: specific title markers
    if not has_title:
        has_title = any(kw in content[:500] for kw in ["## 标题", "# 标题"])
    if not has_title:
        issues.append("缺少标题/开篇标题（前30行内没有 ## 标题）")
        suggestions.append("添加一个吸引人的标题，不超过64字")
        score -= 20

    # Pain point / opening hook
    has_hook = any(kw in content for kw in ["痛点", "问题", "hook", "钩子", "你有没有", "每天",
                                             "有没有想过", "想象一下", "你每天"])
    if not has_hook:
        issues.append("缺少开头痛点/钩子，难以吸引读者停留")
        suggestions.append("用一个具体场景或痛点开头")
        score -= 15

    # Project explanation
    has_explanation = any(kw in content for kw in ["项目解释", "是什么", "项目介绍", "解决"])
    if not has_explanation:
        issues.append("缺少项目解释段落")
        suggestions.append("用1-2句话说明项目是什么、解决什么问题")
        score -= 15

    # Tech breakdown
    has_tech = any(kw in content for kw in ["技术拆解", "核心能力", "技术架构", "核心功能"])
    if not has_tech:
        issues.append("缺少技术拆解段落")
        suggestions.append("拆解3-5个核心技术能力")
        score -= 15

    # Personal thread
    has_personal = any(kw in content for kw in ["个人", "我学", "我今天", "启发", "心得", "收获",
                                                 "思考", "感悟"])
    if not has_personal:
        issues.append("缺少个人心得/主线")
        suggestions.append("加入'今天学到了什么'的个人感悟")
        score -= 10

    # CTA at end
    last_lines = content.strip().split("\n")[-10:]
    last_text = " ".join(last_lines)
    has_cta = any(kw in last_text for kw in ["关注", "订阅", "点赞", "在看", "分享",
                                              "下期", "明天", "再见"])
    if not has_cta:
        issues.append("结尾缺少 CTA（关注/点赞/转发引导）")
        suggestions.append("在文章末尾添加关注引导语")
        score -= 10

    return FileCheckResult(
        status="pass" if score >= 70 else ("needs_revision" if score >= 40 else "fail"),
        score=max(0, score),
        custom_issues=issues,
        custom_suggestions=suggestions,
    )


def _check_xiaohongshu(content: str) -> FileCheckResult:
    """Check 小红书: title length, emoji, tags, CTA comment guide, no exaggeration."""
    issues = []
    suggestions = []
    score = 100

    # Find title (first meaningful line)
    lines = [l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith("# ")]
    title_line = ""
    for line in lines:
        if line and not line.startswith(">"):
            title_line = line
            break
    if len(title_line) > 80:
        issues.append(f"标题过长（{len(title_line)}字符），建议≤20字")
        suggestions.append("精简标题到20字以内")
        score -= 15

    # Emoji check
    emoji_count = sum(1 for c in content if ord(c) > 0x1F000 or (0x2600 <= ord(c) <= 0x27BF)
                      or (0x1F300 <= ord(c) <= 0x1F9FF))
    if emoji_count < 2:
        issues.append("缺少 emoji 分段，小红书需要视觉节奏")
        suggestions.append("用 emoji 分隔段落，增强可读性")
        score -= 15

    # Tags check
    import re
    tags = re.findall(r'#[^\s#]+', content)
    if len(tags) < 2:
        issues.append("标签不足（建议3-5个）")
        suggestions.append("添加3-5个相关标签")
        score -= 15

    # CTA / comment guide
    has_cta = any(kw in content for kw in ["评论区", "评论区告诉", "留言", "点赞收藏",
                                            "关注我", "记得关注", "评论告诉我", "👇"])
    if not has_cta:
        issues.append("缺少评论区引导语")
        suggestions.append("在末尾添加评论区互动引导")
        score -= 10

    return FileCheckResult(
        status="pass" if score >= 70 else ("needs_revision" if score >= 40 else "fail"),
        score=max(0, score),
        custom_issues=issues,
        custom_suggestions=suggestions,
    )


def _check_video_script(content: str) -> FileCheckResult:
    """Check video script: hook in first seconds, core content, CTA at end."""
    issues = []
    suggestions = []
    score = 100

    # Hook
    has_hook = any(kw in content for kw in ["0-3s", "0-5s", "钩子", "hook", "开头"])
    if not has_hook:
        issues.append("缺少开篇钩子标注（如 【0-3s】）")
        suggestions.append("标注开篇钩子：前3秒抓住注意力")
        score -= 20

    # Core content
    has_core = any(kw in content for kw in ["核心", "3-15s", "3s-15s", "5-20s",
                                             "核心内容", "拆解", "功能"])
    if not has_core:
        issues.append("缺少核心内容段落")
        suggestions.append("添加15-25秒的核心内容讲解")
        score -= 20

    # CTA
    has_cta = any(kw in content for kw in ["CTA", "关注", "搜索", "GitHub", "点赞",
                                            "收藏", "下期", "每天"])
    if not has_cta:
        issues.append("缺少结尾 CTA")
        suggestions.append("在脚本末尾添加关注/搜索引导")
        score -= 20

    return FileCheckResult(
        status="pass" if score >= 60 else ("needs_revision" if score >= 30 else "fail"),
        score=max(0, score),
        custom_issues=issues,
        custom_suggestions=suggestions,
    )


def _check_review_checklist(content: str) -> FileCheckResult:
    """Check 04_review_checklist.md: has publish decision markers."""
    issues = []
    score = 100

    has_publishable = any(kw in content for kw in ["可发布", "publishable"])
    has_revise = any(kw in content for kw in ["修改后发布", "needs_revision", "修改"])
    has_reject = any(kw in content for kw in ["不发布", "reject", "不通过"])

    if not has_publishable:
        issues.append("审稿清单缺少'可发布'选项")
        score -= 15
    if not has_revise:
        issues.append("审稿清单缺少'修改后发布'选项")
        score -= 10
    if not has_reject:
        issues.append("审稿清单缺少'不发布'选项")
        score -= 10

    return FileCheckResult(
        status="pass" if score >= 70 else "needs_revision",
        score=max(0, score),
        custom_issues=issues,
        custom_suggestions=[],
    )


def _check_next_actions(content: str) -> FileCheckResult:
    """Check 05_next_actions.md: has publishing steps."""
    score = 100
    issues = []

    has_steps = any(kw in content for kw in ["今天", "发布", "下一步"])
    if not has_steps:
        issues.append("缺少发布步骤或下一步计划")
        score -= 30

    return FileCheckResult(
        status="pass" if score >= 70 else "needs_revision",
        score=max(0, score),
        custom_issues=issues,
        custom_suggestions=[],
    )


def _check_readme(content: str) -> FileCheckResult:
    """Check README.md: has metadata, file list, risk warnings."""
    score = 100
    issues = []

    has_project = "项目" in content or "project" in content.lower()
    has_files = "文件" in content or "files" in content.lower()
    has_risk = "风险" in content or "risk" in content.lower()

    if not has_project:
        issues.append("README 缺少项目信息")
        score -= 20
    if not has_files:
        issues.append("README 缺少文件清单")
        score -= 15
    if not has_risk:
        issues.append("README 缺少风险提示")
        score -= 15

    return FileCheckResult(
        status="pass" if score >= 70 else "needs_revision",
        score=max(0, score),
        custom_issues=issues,
        custom_suggestions=[],
    )


# ═════════════════════════════════════════════════════════════════════════════
# Cross-cutting checkers
# ═════════════════════════════════════════════════════════════════════════════


def _check_risk_boundary(content: str) -> list[str]:
    """Check for risk phrases and banned keywords. Returns list of issue descriptions."""
    issues = []

    for phrase, explanation in PHASE18_RISK_PHRASES:
        if phrase in content:
            # Check if in safe context (warning/negation)
            if not _is_risk_safe_context(content, phrase):
                issues.append(f"风险短语: '{phrase}' — {explanation}")

    for keyword in PHASE18_BANNED_KEYWORDS:
        if keyword in content:
            if not _is_risk_safe_context(content, keyword):
                issues.append(f"禁止关键词: '{keyword}'")

    return issues


def _is_risk_safe_context(content: str, phrase: str) -> bool:
    """Check if a risk phrase appears in a warning/negation/disclaimer context."""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if phrase not in line:
            continue
        # Check for safe-context markers on the same line
        safe_markers = [
            "不能", "不得", "禁止", "不要", "风险", "必须遵守",
            "不是万能", "不能保证", "不能承诺", "不保证", "并非",
            "不存在", "严禁", "不应", "避免使用", "避免了", "避免",
            "可能触及", "触犯", "违反", "违法", "非法", "法律",
            "❌", "⚠️",
        ]
        if any(marker in line for marker in safe_markers):
            return True
    return False


def _check_cta(content: str, platform: str) -> tuple[bool, str]:
    """Check if content has appropriate CTA for the platform.

    Returns (ok, detail_message).
    """
    cta_keywords = {
        "wechat": ["关注", "点赞", "在看", "分享", "订阅", "下期", "明天"],
        "xiaohongshu": ["评论区", "点赞收藏", "关注", "评论告诉", "👇", "留言"],
        "video": ["关注", "搜索", "GitHub", "点赞", "收藏", "下期", "每天"],
    }
    keywords = cta_keywords.get(platform, ["关注"])

    # Check last 15 lines for CTA
    lines = content.strip().split("\n")
    tail = " ".join(lines[-15:]) if len(lines) > 15 else " ".join(lines)

    has_cta = any(kw in tail for kw in keywords)
    if has_cta:
        return True, ""
    else:
        return False, f"缺少 {platform} CTA 引导语"


def _is_blocking_risk(issue: str) -> bool:
    """Determine if a risk issue is blocking (rejected) vs advisory (needs_revision)."""
    blocking_indicators = [
        "保证排名", "保证询盘", "保证 AI 引用", "保证收益",
        "万能爬虫", "绕过风控", "绕过反爬", "绕过登录",
        "全自动发布", "零风险", "批量注册",
    ]
    return any(indicator in issue for indicator in blocking_indicators)


# ═════════════════════════════════════════════════════════════════════════════
# Renderers
# ═════════════════════════════════════════════════════════════════════════════


def _render_review_report(report: ReviewReport, manifest: dict) -> str:
    """Render the comprehensive review report as Markdown."""
    verdict_icons = {"ready": "✅ 可发布", "needs_revision": "⚠️ 需修改后发布",
                     "rejected": "🔴 不建议发布"}
    verdict_label = verdict_icons.get(report.verdict, report.verdict)

    lines = [
        f"# 发布审核报告",
        "",
        f"**项目**: {manifest.get('repo', 'unknown')}",
        f"**审核时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## 总体判决",
        "",
        f"- **判决**: {verdict_label}",
        f"- **综合评分**: {report.overall_score}/100",
        f"- **阻断问题**: {len(report.blocking_issues)} 个",
        f"- **风险问题**: {report.risk_blocking_count} 个",
        "",
    ]

    if report.blocking_issues:
        lines.append("### 阻断问题")
        lines.append("")
        for bi in report.blocking_issues:
            lines.append(f"- 🔴 {bi}")
        lines.append("")

    if report.risk_issues:
        lines.append("### 风险提示")
        lines.append("")
        for ri in report.risk_issues:
            lines.append(f"- ⚠️ {ri}")
        lines.append("")

    if report.cta_issues:
        lines.append("### CTA 缺失")
        lines.append("")
        for ci in report.cta_issues:
            lines.append(f"- 📢 {ci}")
        lines.append("")

    # Per-file scores
    lines.append("---")
    lines.append("")
    lines.append("## 文件级评分")
    lines.append("")
    lines.append("| 文件 | 状态 | 评分 | 问题数 |")
    lines.append("|------|------|------|--------|")
    for fname, check in report.file_checks.items():
        status_icon = {"pass": "✅", "needs_revision": "⚠️", "fail": "🔴"}.get(check.status, "?")
        lines.append(f"| {fname} | {status_icon} {check.status} | {check.score} | {len(check.custom_issues)} |")
    lines.append("")

    # Per-file details
    for fname, check in report.file_checks.items():
        if check.custom_issues:
            lines.append(f"### {fname}")
            lines.append("")
            for issue in check.custom_issues:
                lines.append(f"- {issue}")
            if check.custom_suggestions:
                lines.append("")
                lines.append("**建议修改**:")
                for s in check.custom_suggestions:
                    lines.append(f"  - {s}")
            lines.append("")

    if report.revision_suggestions:
        lines.append("## 修改建议汇总")
        lines.append("")
        for s in report.revision_suggestions:
            lines.append(f"- {s}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间: {datetime.now(timezone.utc).isoformat()[:19]}*")

    return "\n".join(lines)


def _render_handoff_summary(manifest: dict, approved_at: str) -> str:
    """Render 07_handoff_summary.md."""
    repo = manifest.get("repo", "unknown")
    platforms = manifest.get("suitable_platforms", [])
    source_mode = manifest.get("source_mode", "unknown")
    quality_score = manifest.get("quality_score", "N/A")

    lines = [
        f"# 发布交接摘要 — {repo}",
        "",
        f"**批准时间**: {approved_at}",
        f"**内容模式**: {source_mode}",
        f"**质量评分**: {quality_score}/100",
        f"**状态**: ✅ 已批准发布",
        "",
        "---",
        "",
        "## 发布清单",
        "",
    ]

    if "公众号" in platforms:
        lines.append("### 公众号")
        lines.append("- [ ] 复制 01_wechat_ready.md 到公众号编辑器")
        lines.append("- [ ] 调整排版（字体/行距/段落间距）")
        lines.append("- [ ] 添加封面图")
        lines.append("- [ ] 预览 → 发布")
        lines.append("")

    if "小红书" in platforms:
        lines.append("### 小红书")
        lines.append("- [ ] 复制 02_xiaohongshu_ready.md 到小红书")
        lines.append("- [ ] 添加/调整图片（建议6-9张）")
        lines.append("- [ ] 确认标签准确")
        lines.append("- [ ] 发布 + 置顶评论引导")
        lines.append("")

    if "抖音" in platforms or "视频号" in platforms:
        lines.append("### 短视频")
        lines.append("- [ ] 使用 03_video_script_ready.md 录制口播")
        lines.append("- [ ] 添加字幕 + BGM")
        lines.append("- [ ] 发布到抖音/视频号")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 发布后",
        "",
        "- [ ] 记录各平台发布链接",
        "- [ ] 24h 后记录阅读量/播放量/互动数据",
        "- [ ] 评论区互动",
        "- [ ] 复盘：哪个平台表现最好？",
        "",
        "---",
        "",
        f"*此摘要由 approve-pack 自动生成于 {approved_at}*",
    ])

    return "\n".join(lines)


def _render_rejection_record(manifest: dict, reason: str, rejected_at: str) -> str:
    """Render 07_rejection_record.md."""
    repo = manifest.get("repo", "unknown")

    lines = [
        f"# 发布拒绝记录 — {repo}",
        "",
        f"**拒绝时间**: {rejected_at}",
        f"**状态**: 🔴 已拒绝",
        "",
        "---",
        "",
        "## 拒绝原因",
        "",
        reason,
        "",
        "---",
        "",
        "## 后续建议",
        "",
        "1. 根据拒绝原因修改内容",
        "2. 重新运行 `python run.py publish-pack` 生成新发布包",
        "3. 再次运行 `python run.py review-pack` 检查",
        "",
        "---",
        "",
        f"*此记录由 reject-pack 自动生成于 {rejected_at}*",
    ]

    return "\n".join(lines)


def _render_revision_notes(manifest: dict, all_issues: dict[str, list[str]],
                           report: ReviewReport, generated_at: str) -> str:
    """Render 07_revision_notes.md — suggestions only, no auto-modification."""
    repo = manifest.get("repo", "unknown")

    lines = [
        f"# 改稿建议 — {repo}",
        "",
        f"**生成时间**: {generated_at}",
        f"**审核判决**: {report.verdict}",
        f"**综合评分**: {report.overall_score}/100",
        "",
        "> ⚠️ 此文件仅供人工参考，未对任何正文文件做自动修改。",
        "> 请逐条审阅以下建议，手动修改对应文件后重新发布。",
        "",
        "---",
        "",
    ]

    for fname, issues in all_issues.items():
        if issues:
            lines.append(f"## {fname}")
            lines.append("")
            for i, issue in enumerate(issues, 1):
                lines.append(f"{i}. {issue}")
            lines.append("")

    if not all_issues:
        lines.append("当前未发现需要修改的问题。")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 改稿流程",
        "",
        "1. 逐条审阅上方建议",
        "2. 手动修改对应文件",
        "3. 修改完成后运行 `python run.py review-pack <pack_dir>` 重新检查",
        "4. 确认 verdict=ready 后运行 `python run.py approve-pack <pack_dir>` 批准",
        "",
        "---",
        "",
        f"*此改稿建议由 revise-pack 自动生成于 {generated_at}*",
    ])

    return "\n".join(lines)
