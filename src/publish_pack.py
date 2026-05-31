"""Publish pack builder — generates local handoff directories for manual publishing.

No platform API calls, no auto-publishing, no credential storage.
Produces human-ready copy files that the user reviews, edits, and posts manually.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import CONTENT_PACKS_DIR, PUBLISH_PACKS_DIR

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "00_publish_manifest.json"
PACK_FILES = {
    "readme": "README.md",
    "manifest": MANIFEST_FILENAME,
    "wechat": "01_wechat_ready.md",
    "xiaohongshu": "02_xiaohongshu_ready.md",
    "video_script": "03_video_script_ready.md",
    "review_checklist": "04_review_checklist.md",
    "next_actions": "05_next_actions.md",
}

QUALIFIED_THRESHOLD = 75


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def build_publish_pack(repo_full_name: str | None = None) -> dict:
    """Generate a publish handoff pack.

    Args:
        repo_full_name: owner/repo to build pack for. If None, auto-detects
                        the best candidate from the latest daily run.

    Returns:
        dict with keys: status, pack_dir, repo, files, manifest, warnings
    """
    if repo_full_name is None:
        repo_full_name = _find_best_from_review_queue()
        if repo_full_name is None:
            return {
                "status": "no_candidate",
                "pack_dir": None,
                "repo": None,
                "files": [],
                "manifest": None,
                "warnings": ["今日无合格发布候选，不建议生成发布包。最高分低于阈值或风险过高。"],
            }

    # Determine content pack path
    slug = repo_full_name.replace("/", "__")
    content_pack_dir = CONTENT_PACKS_DIR / slug

    # Build publish pack directory
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pack_dir = PUBLISH_PACKS_DIR / f"{today}_{slug}"
    pack_dir.mkdir(parents=True, exist_ok=True)

    # Load content pack files if available
    cp_files = _read_content_pack_files(content_pack_dir)

    # Detect source mode
    source_mode = "full_llm"
    manifest_path = content_pack_dir / "_manifest.json"
    quality_score = None
    recommendation = None
    blocking = 0
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_mode = data.get("mode") or data.get("content_mode") or ""
            # Normalize: "LLM" / "full_llm" → "full_llm"; everything else → "structured_fallback"
            if raw_mode in ("full_llm", "LLM"):
                source_mode = "full_llm"
            else:
                source_mode = "structured_fallback"
            quality_score = data.get("quality_review_score")
            recommendation = data.get("quality_review_recommendation")
            blocking = data.get("blocking", 0)
        except Exception:
            pass

    # Determine publishability
    publishable = source_mode == "full_llm" and recommendation == "yes" and blocking == 0
    manual_review_required = not publishable

    # Determine suitable platforms from content pack presence
    suitable_platforms = []
    if cp_files.get("05_wechat_article"):
        suitable_platforms.append("公众号")
    if cp_files.get("02_xiaohongshu"):
        suitable_platforms.append("小红书")
    if cp_files.get("03_douyin_video") or cp_files.get("04_videohao_script"):
        suitable_platforms.append("抖音")
        suitable_platforms.append("视频号")
    if cp_files.get("07_geo_angle"):
        suitable_platforms.append("外贸/GEO")

    # Risks
    risks = []
    if source_mode == "structured_fallback":
        risks.append("内容由模板生成（structured_fallback），未经 LLM 润色，信息可能不完整")
    if blocking > 0:
        risks.append(f"reviewer 报告 {blocking} 个阻断问题，需人工解决后重新生成")
    if quality_score and quality_score < 91:
        risks.append(f"质量评分 {quality_score}/100 低于 91，建议通读后发布")

    # Collect file list
    files_generated = []

    # 1. Manifest
    manifest = {
        "repo": repo_full_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": source_mode,
        "quality_score": quality_score,
        "recommendation": recommendation,
        "publishable": publishable,
        "blocking_count": blocking,
        "suitable_platforms": suitable_platforms,
        "files": [],
        "manual_review_required": manual_review_required,
        "risks": risks,
        "suggested_publish_order": suitable_platforms,
    }
    _write_file(pack_dir, MANIFEST_FILENAME, json.dumps(manifest, ensure_ascii=False, indent=2))
    files_generated.append(MANIFEST_FILENAME)

    # 2. README
    _write_file(pack_dir, PACK_FILES["readme"],
                _render_readme(repo_full_name, source_mode, quality_score, suitable_platforms,
                               publishable, manual_review_required, risks))
    files_generated.append(PACK_FILES["readme"])

    # 3. WeChat
    _write_file(pack_dir, PACK_FILES["wechat"],
                _render_wechat(repo_full_name, cp_files, source_mode))
    files_generated.append(PACK_FILES["wechat"])

    # 4. Xiaohongshu
    _write_file(pack_dir, PACK_FILES["xiaohongshu"],
                _render_xiaohongshu(repo_full_name, cp_files, source_mode))
    files_generated.append(PACK_FILES["xiaohongshu"])

    # 5. Video script
    _write_file(pack_dir, PACK_FILES["video_script"],
                _render_video_script(repo_full_name, cp_files, source_mode))
    files_generated.append(PACK_FILES["video_script"])

    # 6. Review checklist
    _write_file(pack_dir, PACK_FILES["review_checklist"],
                _render_review_checklist(repo_full_name, source_mode, publishable, risks))
    files_generated.append(PACK_FILES["review_checklist"])

    # 7. Next actions
    _write_file(pack_dir, PACK_FILES["next_actions"],
                _render_next_actions(repo_full_name, suitable_platforms, publishable))
    files_generated.append(PACK_FILES["next_actions"])

    manifest["files"] = files_generated
    _write_file(pack_dir, MANIFEST_FILENAME, json.dumps(manifest, ensure_ascii=False, indent=2))

    return {
        "status": "ok",
        "pack_dir": str(pack_dir),
        "repo": repo_full_name,
        "files": files_generated,
        "manifest": manifest,
        "warnings": risks,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════


def _find_best_from_review_queue() -> str | None:
    """Find the best publishable repo from the latest daily review queue data.

    Scans REPORTS_DIR for top5_*.json, picks the highest-scored repo
    that reaches QUALIFIED_THRESHOLD and passes basic sanity checks.
    """
    from .config import REPORTS_DIR
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Try today's top5 JSON
    top5_path = REPORTS_DIR / f"top5_{today}.json"
    if not top5_path.exists():
        candidates = sorted(REPORTS_DIR.glob("top5_*.json"), reverse=True)
        if candidates:
            top5_path = candidates[0]
        else:
            return None

    try:
        top5 = json.loads(top5_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    best_name = None
    best_score = 0

    for item in top5:
        score = item.get("score", 0) if isinstance(item, dict) else getattr(item, "score", 0)
        name = item.get("full_name", "") if isinstance(item, dict) else getattr(item, "full_name", "")
        if score >= QUALIFIED_THRESHOLD and score > best_score:
            best_score = score
            best_name = name

    # Fallback: if no score in top5 data, try content pack manifests
    if best_name is None:
        best_name = _find_best_from_content_packs()

    return best_name


def _find_best_from_content_packs() -> str | None:
    """Fallback: find best candidate from content pack manifests."""
    best_name = None
    best_score = 0

    for manifest_path in sorted(CONTENT_PACKS_DIR.glob("*/_manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            score = data.get("quality_review_score", 0)
            rec = data.get("quality_review_recommendation", "")
            blocking = data.get("blocking", 0)
            repo = data.get("repo", "")
            if score >= QUALIFIED_THRESHOLD and rec == "yes" and blocking == 0 and score > best_score:
                best_score = score
                best_name = repo
        except Exception:
            continue

    return best_name


def _read_content_pack_files(cp_dir: Path) -> dict[str, str | None]:
    """Read content pack files into a dict keyed by short filename."""
    files = {}
    mapping = {
        "00_repo_snapshot": "00_repo_snapshot.md",
        "01_ai_fde_deep_analysis": "01_ai_fde_deep_analysis.md",
        "02_xiaohongshu": "02_xiaohongshu.md",
        "03_douyin_video": "03_douyin_video.md",
        "04_videohao_script": "04_videohao_script.md",
        "05_wechat_article": "05_wechat_article.md",
        "06_storyboard": "06_storyboard.md",
        "07_geo_angle": "07_geo_angle.md",
        "08_enterprise_pitch": "08_enterprise_pitch.md",
        "09_risk_review": "09_risk_review.md",
        "10_quality_check": "10_quality_check.md",
    }
    for key, fname in mapping.items():
        fpath = cp_dir / fname
        if fpath.exists():
            files[key] = fpath.read_text(encoding="utf-8")
        else:
            files[key] = None
    return files


def _write_file(pack_dir: Path, filename: str, content: str) -> None:
    (pack_dir / filename).write_text(content, encoding="utf-8")


# ═════════════════════════════════════════════════════════════════════════════
# Renderers — each produces a human-ready markdown file
# ═════════════════════════════════════════════════════════════════════════════


def _render_readme(repo: str, source_mode: str, quality_score: int | None,
                   platforms: list[str], publishable: bool, manual_review: bool,
                   risks: list[str]) -> str:
    lines = [
        f"# 发布包 — {repo}",
        "",
        f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## 项目信息",
        "",
        f"- **项目**: `{repo}`",
        f"- **内容模式**: {source_mode}",
        f"- **质量评分**: {quality_score or 'N/A'}/100",
        f"- **可发布**: {'是' if publishable else '否（需人工审核）'}",
        f"- **需人工审核**: {'是' if manual_review else '否'}",
        f"- **适合平台**: {', '.join(platforms) if platforms else '待确认'}",
        "",
        "## 风险提示",
        "",
    ]
    if risks:
        for r in risks:
            lines.append(f"- ⚠ {r}")
    else:
        lines.append("- 无阻断性风险")
    lines.extend([
        "",
        "## 人工审核步骤",
        "",
        "1. 通读各平台 ready 文件",
        "2. 对照 `04_review_checklist.md` 逐项检查",
        "3. 修改需要调整的段落",
        "4. 确认后手动复制到对应平台发布",
        "",
        "## 文件清单",
        "",
        "| 文件 | 用途 |",
        "|------|------|",
        f"| `{PACK_FILES['manifest']}` | 机器可读元数据 |",
        f"| `{PACK_FILES['wechat']}` | 公众号可复制版本 |",
        f"| `{PACK_FILES['xiaohongshu']}` | 小红书可复制版本 |",
        f"| `{PACK_FILES['video_script']}` | 视频号/抖音口播脚本 |",
        f"| `{PACK_FILES['review_checklist']}` | 人工审稿清单 |",
        f"| `{PACK_FILES['next_actions']}` | 下一步动作 |",
        "",
        "> 此发布包不自动发布到任何平台，不调用平台 API，不保存账号密码。",
        "> 所有文件供人工审核后手动发布。",
    ])
    return "\n".join(lines)


def _render_wechat(repo: str, cp_files: dict, source_mode: str) -> str:
    wechat_content = cp_files.get("05_wechat_article")
    deep_analysis = cp_files.get("01_ai_fde_deep_analysis")
    snapshot = cp_files.get("00_repo_snapshot")

    lines = [
        f"# 公众号发布版本 — {repo}",
        "",
        "> 复制以下内容到公众号编辑器，修改后发布。",
        f"> 内容模式: {source_mode}",
        "",
    ]

    if wechat_content and source_mode == "full_llm":
        lines.append(wechat_content)
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 发布前检查")
        lines.append("- [ ] 标题是否吸引人且不超过 64 字")
        lines.append("- [ ] 正文是否包含引导关注语句")
        lines.append("- [ ] 项目链接是否正确")
        lines.append("- [ ] 风险提示是否保留")
    else:
        lines.append("## ⚠ 需人工补写")
        lines.append("")
        lines.append("当前内容由模板生成，不可直接发布。请使用以下素材手动编写：")
        lines.append("")
        if deep_analysis:
            lines.append("### AI-FDE 深度分析素材")
            lines.append("")
            lines.append(deep_analysis[:3000])
            lines.append("")
            lines.append("> （全文见 `01_ai_fde_deep_analysis.md`）")
        if snapshot:
            lines.append("")
            lines.append("### 项目信息")
            lines.append("")
            lines.append(snapshot[:1500])
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 补写要点")
        lines.append("- 开场：一句话说清楚这个项目做什么")
        lines.append("- 技术拆解：3-5 个核心能力")
        lines.append("- 企业场景：2-3 个真实使用场景")
        lines.append("- 风险边界：robots.txt / 版权 / 许可证")
        lines.append("- 结尾：我今天学到了什么")

    return "\n".join(lines)


def _render_xiaohongshu(repo: str, cp_files: dict, source_mode: str) -> str:
    xhs_content = cp_files.get("02_xiaohongshu")

    lines = [
        f"# 小红书发布版本 — {repo}",
        "",
        "> 复制到小红书 App，注意：不能夸大、不能写万能、不能写保证结果。",
        f"> 内容模式: {source_mode}",
        "",
    ]

    if xhs_content and source_mode == "full_llm":
        lines.append(xhs_content)
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 发布前检查")
        lines.append("- [ ] 标题是否在 20 字以内")
        lines.append("- [ ] 正文是否有 emoji 分段")
        lines.append("- [ ] 标签是否 3-5 个")
        lines.append("- [ ] 是否有评论区引导语")
        lines.append("- [ ] 是否避免了'万能/保证/自动绕过'等危险词")
    else:
        lines.append("## ⚠ 需人工补写")
        lines.append("")
        lines.append("当前无 LLM 生成的小红书内容。请手动编写：")
        lines.append("")
        lines.append("### 小红书写作要点")
        lines.append("- 标题：3 个备选，每个 ≤20 字，带 emoji")
        lines.append("- 正文：分点不写大段，用 emoji 分段")
        lines.append("- 标签：3-5 个相关标签")
        lines.append("- 评论区：准备一条引导评论")
        lines.append("- 首图：建议项目 Logo + 一句话亮点")

    return "\n".join(lines)


def _render_video_script(repo: str, cp_files: dict, source_mode: str) -> str:
    douyin = cp_files.get("03_douyin_video")
    videohao = cp_files.get("04_videohao_script")
    storyboard = cp_files.get("06_storyboard")

    lines = [
        f"# 视频脚本 — {repo}",
        "",
        f"> 内容模式: {source_mode}",
        "",
    ]

    if (douyin or videohao) and source_mode == "full_llm":
        lines.append("## 30 秒版（抖音/视频号通用）")
        lines.append("")
        if douyin:
            lines.append(douyin[:2000])
        lines.append("")
        lines.append("## 60 秒版（视频号深度版）")
        lines.append("")
        if videohao:
            lines.append(videohao[:3000])
        if storyboard:
            lines.append("")
            lines.append("## 分镜提示")
            lines.append("")
            lines.append(storyboard[:2000])
    else:
        lines.append("## ⚠ 需人工编写脚本")
        lines.append("")
        lines.append("### 30 秒版模板")
        lines.append("```")
        lines.append("【0-3s 钩子】这个开源项目有 X 万星，却很少人知道它真正能做什么。")
        lines.append(f"【3-15s 核心】{repo} 解决的是...")
        lines.append("【15-25s 场景】想象一下你每天要做 X，现在一个 API 搞定。")
        lines.append("【25-30s CTA】GitHub 搜项目名，免费开源。关注我看更多 AI 工具拆解。")
        lines.append("```")
        lines.append("")
        lines.append("### 屏幕文字提示")
        lines.append("- 0-3s: 项目名称 + Star 数")
        lines.append("- 3-15s: 核心功能 3 个关键词")
        lines.append("- 15-25s: 使用场景配截图/GIF")
        lines.append("- 25-30s: GitHub 链接 + 关注引导")

    return "\n".join(lines)


def _render_review_checklist(repo: str, source_mode: str, publishable: bool,
                             risks: list[str]) -> str:
    lines = [
        f"# 人工审稿清单 — {repo}",
        "",
        f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "在发布到任何平台前，逐项确认以下检查：",
        "",
        "## 事实准确性",
        "- [ ] 项目 Star 数、许可证、编程语言是否与 GitHub 一致",
        "- [ ] 功能描述是否可在 README 中找到对应依据",
        "- [ ] 不存在推测性功能被写成确定事实",
        "",
        "## 夸大风险",
        "- [ ] 不存在'任何网站都能…''万能''自动绕过反爬'等危险表达",
        "- [ ] 不存在'保证排名''保证询盘''保证 AI 引用'等虚假承诺",
        "- [ ] 不存在'登录/付费墙/绕过验证'等违规暗示",
        "",
        "## 平台合规",
        "- [ ] 公众号版本：标题 ≤64 字，文末有引导关注",
        "- [ ] 小红书版本：标题 ≤20 字，有 emoji 分段，有标签",
        "- [ ] 视频脚本：开头 3 秒有钩子，结尾有 CTA",
        "- [ ] 所有平台版本均已添加风险提示",
        "",
        "## 内容质量",
        "- [ ] 文字通顺，无明显语病或机翻痕迹",
        "- [ ] 段落结构清晰，适合手机阅读",
        f"- [ ] 内容模式: {source_mode} — {'可直接发布' if publishable else '需人工补写后再发布'}",
        "",
        "## 风险确认",
    ]
    if risks:
        for r in risks:
            lines.append(f"- [ ] ⚠ {r}")
    else:
        lines.append("- [ ] 无风险项")

    lines.extend([
        "",
        "## 最终结论",
        "",
        "请在以下选项中选择一项：",
        "",
        "- [ ] **可发布** — 所有检查项通过，可以复制到平台发布",
        "- [ ] **修改后发布** — 有少量需要修改的地方（请在文件内标注）",
        "- [ ] **不发布** — 存在阻断性问题，不建议今天发布",
        "",
        "---",
        "",
        "> 签字/日期：_______________",
    ])
    return "\n".join(lines)


def _render_next_actions(repo: str, platforms: list[str], publishable: bool) -> str:
    lines = [
        f"# 下一步动作 — {repo}",
        "",
        "## 今天怎么发",
        "",
    ]
    if publishable and platforms:
        lines.append("建议发布顺序：")
        lines.append("")
        for i, p in enumerate(platforms, 1):
            lines.append(f"{i}. **{p}** — 打开对应文件，复制内容，微调后发布")
        lines.append("")
        lines.append("> 先发公众号/深度平台 → 提取核心观点 → 改写成短视频/图文 → 分发到其他平台。")
    else:
        lines.append("- 今天不建议直接发布")
        lines.append("- 先人工补写或修改内容")
        lines.append("- 完成 `04_review_checklist.md` 的检查")
        lines.append("- 确认后可手动复制发布")

    lines.extend([
        "",
        "## 发完记录什么",
        "",
        "- 各平台阅读量 / 播放量 / 点赞数",
        "- 评论区有价值的问题（可作为下期选题）",
        "- 哪个平台表现最好（决定下次主发哪个平台）",
        "",
        "## 明天怎么复盘",
        "",
        "- 对比今天和昨天的数据",
        "- 找出表现最好的内容类型（深度拆解 vs 工具推荐 vs 行业视角）",
        "- 根据反馈决定是否做二次内容（如：微信文章反响好 → 做成视频深度版）",
        "",
        "## 是否值得做二次内容",
        "",
        "- 如果 24h 内阅读/播放 > 日常平均 2x → 值得做二次内容",
        "- 二次内容形式：视频深度版 / 小红书图文版 / 行业视角版",
        "- 不要为低数据内容投入二次时间",
    ])
    return "\n".join(lines)
