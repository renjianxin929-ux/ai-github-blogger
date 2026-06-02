"""Local operator UI — FastAPI app factory + time-aware state derivation.

Phase 26: Browser-based operator workspace. Wraps existing CLI functions
into a visual UI with 8 sections. Zero JS, pure server-rendered HTML.

Safety boundaries:
  - All POST actions use hardcoded allowlist (no dynamic command passthrough)
  - All inputs validated and sanitized before calling backend functions
  - State-changing actions require confirmation (checked via "confirmed" form field)
  - No external platform API integrations
  - No .env / full API key exposure
  - Paths restricted to project directory
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

PLATFORM_ALLOWLIST = frozenset({"wechat", "xiaohongshu", "douyin", "videohao", "geo"})

PLATFORM_LABELS = {
    "wechat": "公众号",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "videohao": "视频号",
    "geo": "GEO",
}

TIME_LABELS = {
    "night": "\U0001f319 晚间准备",
    "morning": "\U0001f305 早间终审",
    "late_morning": "⚠️ 偏晚警告",
    "post_publish": "\U0001f4ca 发布后",
}

PUBLISH_DEADLINE_HOUR = 9.0
PUBLISH_LATE_HOUR = 9.5

# ═══════════════════════════════════════════════════════════════════════════════
# Path resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root)
    return Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
# Safety Validators
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_pack_dir(path: str, project_root: Path | None = None) -> Path:
    """Validate that pack_dir is within the project directory. No traversal."""
    root = _resolve_root(project_root)
    try:
        resolved = (root / path).resolve()
    except (ValueError, OSError):
        raise ValueError(f"无效路径: {path}")
    root_resolved = root.resolve()
    if not str(resolved).startswith(str(root_resolved) + os.sep) and resolved != root_resolved:
        raise ValueError(f"路径超出项目目录: {path}")
    if ".." in Path(path).parts:
        raise ValueError(f"路径包含非法字符: {path}")
    return resolved


def _validate_repo_name(name: str) -> tuple[str, str]:
    """Validate and split owner/repo format. Only allow safe chars."""
    name = name.strip()
    if not name or "/" not in name:
        raise ValueError(f"无效的 repo 格式 (需要 owner/repo): {name}")
    parts = name.split("/")
    if len(parts) != 2:
        raise ValueError(f"无效的 repo 格式 (需要 owner/repo): {name}")
    owner, repo = parts
    for part in [owner, repo]:
        if not part or not all(c.isalnum() or c in "._-" for c in part):
            raise ValueError(f"repo 名包含非法字符: {name}")
    return owner, repo


def _validate_platform(platform: str) -> str:
    """Validate platform is in allowlist."""
    platform = platform.strip().lower()
    if platform not in PLATFORM_ALLOWLIST:
        raise ValueError(f"不支持的平台: {platform}，允许: {', '.join(sorted(PLATFORM_ALLOWLIST))}")
    return platform


def _validate_nonneg_int(value: str) -> int:
    """Parse and validate non-negative integer."""
    try:
        v = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"不是有效整数: {value}")
    if v < 0:
        raise ValueError(f"不能为负数: {v}")
    return v


def _sanitize_url(url: str) -> str:
    """Only allow http/https URLs."""
    url = url.strip()
    if url and not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError(f"URL 必须以 http:// 或 https:// 开头: {url[:50]}")
    return url[:2000]


def _sanitize_note(note: str) -> str:
    """Strip control characters, limit length."""
    if not note:
        return ""
    cleaned = "".join(c for c in note.strip() if c.isprintable() or c in "\n\r\t")
    return cleaned[:500]


def _mask_key(key: str) -> str:
    """Show only first 4 characters of an API key."""
    if not key:
        return "(未设置)"
    if len(key) <= 6:
        return key[:2] + "****"
    return key[:4] + "****"


# ═══════════════════════════════════════════════════════════════════════════════
# Time Period Detection
# ═══════════════════════════════════════════════════════════════════════════════

def _get_time_period(now: datetime | None = None) -> str:
    """Return current time period for publishing workflow.

    Returns one of: night / morning / late_morning / post_publish
    """
    now = now or datetime.now()
    hour = now.hour + now.minute / 60.0

    if hour >= 21.0:
        return "night"
    if hour < PUBLISH_DEADLINE_HOUR:
        return "morning"
    if hour < PUBLISH_LATE_HOUR:
        return "late_morning"
    return "post_publish"


# ═══════════════════════════════════════════════════════════════════════════════
# State Derivation
# ═══════════════════════════════════════════════════════════════════════════════

def _scan_filesystem(project_root: Path) -> dict:
    """Scan project state from filesystem. Returns raw fs_state dict."""
    fs = {
        "candidates": [],
        "content_packs": [],
        "publish_packs": [],
        "published_entries": [],
        "metrics_entries": [],
        "active_pack": None,
    }
    root = _resolve_root(project_root)

    # Scan reports for candidates
    reports_dir = root / "data" / "reports"
    if reports_dir.exists():
        top5_files = sorted(reports_dir.glob("top5_*.json"), reverse=True)
        if top5_files:
            try:
                top5 = json.loads(top5_files[0].read_text(encoding="utf-8"))
                for item in top5[:10]:
                    score = item.get("publishability_score", item.get("score", 0))
                    grade = "A" if score >= 75 else "B" if score >= 60 else "C" if score >= 40 else "D"
                    fs["candidates"].append({
                        "repo": item.get("repo", item.get("full_name", "?")),
                        "score": score,
                        "grade": grade,
                        "desc": item.get("description", "")[:80],
                    })
            except (json.JSONDecodeError, OSError, KeyError):
                pass
        else:
            brief_files = sorted(reports_dir.glob("daily_brief_*.md"))
            if brief_files:
                content = brief_files[-1].read_text(encoding="utf-8")
                for line in content.splitlines():
                    if "top5" in line.lower() or "A级" in line:
                        fs["candidates"].append({
                            "repo": line.strip()[:60],
                            "score": 0,
                            "grade": "?",
                            "desc": line.strip()[:80],
                        })

    # Scan content packs
    content_dir = root / "data" / "content_packs"
    if content_dir.exists():
        for d in sorted(content_dir.iterdir(), reverse=True):
            if d.is_dir():
                files = list(d.glob("*.md"))
                fs["content_packs"].append({
                    "dir_name": d.name,
                    "path": str(d),
                    "file_count": len(files),
                })

    # Scan publish packs + status
    publish_dir = root / "data" / "publish_packs"
    active_pack = None
    if publish_dir.exists():
        for d in sorted(publish_dir.iterdir(), reverse=True):
            if d.is_dir():
                manifest_path = d / "00_publish_manifest.json"
                status = "draft"
                repo = d.name.replace("__", "/")
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        status = manifest.get("human_review_status", "draft")
                        repo = manifest.get("repo", repo)
                    except (json.JSONDecodeError, OSError):
                        pass
                pack_info = {
                    "dir_name": d.name,
                    "pack_dir": str(d),
                    "repo": repo,
                    "status": status,
                    "file_count": len(list(d.glob("*.md"))),
                }
                fs["publish_packs"].append(pack_info)
                if active_pack is None and status != "rejected":
                    active_pack = pack_info

    fs["active_pack"] = active_pack

    # Scan publish history
    state_dir = root / "data" / "state"
    pub_hist_file = state_dir / "publish_history.json"
    if pub_hist_file.exists():
        try:
            pub_hist = json.loads(pub_hist_file.read_text(encoding="utf-8"))
            for repo, entries in pub_hist.items():
                for entry in entries:
                    fs["published_entries"].append({
                        "repo": repo,
                        "platform": entry.get("platform", "?"),
                        "url": entry.get("url", ""),
                        "published_at": entry.get("published_at", ""),
                    })
        except (json.JSONDecodeError, OSError):
            pass

    # Scan metrics history
    metrics_file = state_dir / "metrics_history.json"
    if metrics_file.exists():
        try:
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            if isinstance(metrics, dict):
                for repo, entries in metrics.items():
                    for entry in entries:
                        fs["metrics_entries"].append({
                            "repo": repo,
                            "platform": entry.get("platform", "?"),
                            "views": entry.get("views", 0),
                        })
            elif isinstance(metrics, list):
                fs["metrics_entries"] = metrics
        except (json.JSONDecodeError, OSError):
            pass

    return fs


def _derive_next_step(fs_state: dict, time_period: str) -> dict:
    """Compute next_step message from filesystem state and time period.

    Returns dict with: message, detail, urgency, time_period, time_label, deadline_countdown
    """
    has_candidates = len(fs_state.get("candidates", [])) > 0
    has_content = len(fs_state.get("content_packs", [])) > 0
    has_publish_pack = fs_state.get("active_pack") is not None
    active_status = fs_state.get("active_pack", {}).get("status", "") if has_publish_pack else ""

    is_built = has_content or has_publish_pack
    is_reviewed = active_status in ("reviewed", "needs_revision", "ready", "approved", "published")
    is_approved = active_status == "approved"
    is_published = active_status == "published"
    has_published_entries = len(fs_state.get("published_entries", [])) > 0

    time_label = TIME_LABELS.get(time_period, "")

    # Night mode: tomorrow prep focus
    if time_period == "night":
        if not has_candidates and not is_built:
            return {
                "message": "选题准备：运行 daily-workflow 发现明日候选项目",
                "detail": "现在时间充裕，从容为明天准备。打开终端运行 python run.py daily-workflow",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if has_candidates and not is_built:
            return {
                "message": "选项目并 Build，提前为明天准备内容包",
                "detail": f"当前有 {len(fs_state['candidates'])} 个候选项目，选择最合适的 Build 内容包",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if is_built and not is_approved:
            return {
                "message": "完成初步 Review，明天早上直接终审",
                "detail": "现在 Review 完明天早上打开就能发，节省早上宝贵时间",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if is_approved:
            return {
                "message": "内容已就绪，明天早上 09:00 前直接复制发布",
                "detail": "晚上准备已完成，安心休息。明天早上打开 UI 直接复制到公众号后台发布。",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if is_published or has_published_entries:
            return {
                "message": "查看 §7 复盘建议，规划明天选题方向",
                "detail": "晚间复盘时间 — 了解什么内容表现好，指导今晚选题决策",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }

    # Morning mode: finalize and publish
    if time_period == "morning":
        if not has_candidates and not is_built:
            return {
                "message": "⚠️ 风险：现在才选题赶不上 9 点发布，优先选最成熟候选",
                "detail": "建议先跑 python run.py daily-workflow，或手动指定已知好项目",
                "urgency": "warning",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if has_candidates and not is_built:
            return {
                "message": "⚠️ 时间紧迫，Build 后直接 Review + Approve",
                "detail": "不要再纠结选哪个 — 选评分最高的 A 级项目直接 Build",
                "urgency": "warning",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if is_built and not is_approved:
            return {
                "message": "终审 Review，确认无误后 Approve",
                "detail": "快速通读一遍内容，确认无敏感信息后 Approve，然后复制发布",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if is_approved:
            now = datetime.now()
            remaining_min = max(0, int((9.0 - (now.hour + now.minute / 60.0)) * 60))
            return {
                "message": "09:00 前复制到公众号后台发布，然后 Mark Published",
                "detail": f"目标发布时间: 09:00（剩余约 {remaining_min} 分钟），发布后回到这里点击 Mark Published",
                "urgency": "normal" if remaining_min > 30 else "warning",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": f"⏰ 距离 09:00 还有约 {remaining_min} 分钟" if remaining_min > 0 else "",
            }
        if is_published or has_published_entries:
            return {
                "message": "今天已发布，下午回来录入表现数据",
                "detail": "发布后 24-48h 再回来录入 views/likes 等数据",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }

    # Late morning: hurry mode
    if time_period == "late_morning":
        if not has_candidates and not is_built:
            return {
                "message": "⚠️ 今天已偏晚，建议不要再选题，应为明天准备",
                "detail": "超过 09:00 再选题几乎不可能在 09:30 前发布。建议运行 daily-workflow 为明天准备。",
                "urgency": "urgent",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if has_candidates and not is_built:
            return {
                "message": "⚠️ 今天已偏晚，不建议临时选题，应发布已准备好的内容或顺延",
                "detail": "现在 Build + Review + 发布至少需要 15 分钟，已超过 09:00 最佳发布时间",
                "urgency": "urgent",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }
        if is_built and not is_approved:
            return {
                "message": "⚠️ 偏晚但仍可赶在 09:30 前 Approve 并发布",
                "detail": "快速 Review + Approve，然后马上复制发布。时间不多了。",
                "urgency": "urgent",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "⏰ 最晚 09:30 前发布",
            }
        if is_approved:
            return {
                "message": "⚠️ 尽快复制发布，最晚 09:30",
                "detail": "内容已 Approve，现在立刻去公众号后台粘贴发布",
                "urgency": "urgent",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "⏰ 最晚 09:30，抓紧时间",
            }
        if is_published or has_published_entries:
            return {
                "message": "已发布，下午回来录入表现数据",
                "detail": "发布后 24-48h 录入数据，现在可以先忙别的",
                "urgency": "normal",
                "time_period": time_period,
                "time_label": time_label,
                "deadline_countdown": "",
            }

    # Post-publish: data & reflection
    if not has_published_entries:
        return {
            "message": "今天已过发布时间。运行 daily-workflow 为明天选题",
            "detail": "晚上 21:00-23:00 是最佳选题准备时间。也可以现在提前 Build。",
            "urgency": "normal",
            "time_period": time_period,
            "time_label": time_label,
            "deadline_countdown": "",
        }
    return {
        "message": "录入表现数据 Record Metrics，查看 §7 复盘建议",
        "detail": "收集各平台 views/likes/favorites 数据录入系统，驱动下次选题优化",
        "urgency": "normal",
        "time_period": time_period,
        "time_label": time_label,
        "deadline_countdown": "",
    }


def derive_page_state(now: datetime | None = None,
                      project_root: Path | None = None) -> dict:
    """Scan filesystem + current time -> complete page_state dict."""
    root = _resolve_root(project_root)
    time_period = _get_time_period(now)
    fs_state = _scan_filesystem(root)
    next_step = _derive_next_step(fs_state, time_period)

    # Doctor summary
    doctor = _get_doctor_summary()

    # Insights
    insights_html = _get_insights_summary(root)

    return {
        "now": (now or datetime.now()).strftime("%H:%M"),
        "time_period": time_period,
        "next_step": next_step,
        "doctor": doctor,
        "candidates": fs_state["candidates"],
        "active_pack": fs_state["active_pack"],
        "published_entries": fs_state["published_entries"],
        "insights": insights_html,
    }


def _get_doctor_summary() -> dict:
    """Lightweight doctor check — just reads env vars, no network."""
    result = {
        "api_key_masked": "(未设置)",
        "github_ok": False,
        "llm_ok": False,
        "pass_count": 0,
    }
    from .config import GITHUB_TOKEN
    token = GITHUB_TOKEN or os.getenv("GITHUB_TOKEN", "")
    result["api_key_masked"] = _mask_key(token)
    result["github_ok"] = bool(token)
    if result["github_ok"]:
        result["pass_count"] += 1

    llm_key = os.getenv("LLM_API_KEY", "")
    result["llm_ok"] = bool(llm_key)
    if result["llm_ok"]:
        result["pass_count"] += 1

    return result


def _get_insights_summary(project_root: Path) -> str:
    """Get insights summary for display in section 7."""
    try:
        from .insights import insights_summary_for_workbench
        lines = insights_summary_for_workbench()
        return "<br>".join(lines)
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI App Factory
# ═══════════════════════════════════════════════════════════════════════════════

def create_app(
    project_root: Path | None = None,
    state_dir: Path | None = None,
    content_packs_dir: Path | None = None,
    publish_packs_dir: Path | None = None,
    reports_dir: Path | None = None,
    templates_dir: Path | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    """Create FastAPI app with optional path overrides (for testing)."""
    root = _resolve_root(project_root)
    _static_dir = static_dir or (root / "static")
    _templates_dir = templates_dir or (root / "templates")

    app = FastAPI(title="AI GitHub Blogger Operator", version="0.1")

    # Static files
    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    # ═════════════════════════════════════════════════════════════════════════
    # GET /
    # ═════════════════════════════════════════════════════════════════════════

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        from fastapi.templating import Jinja2Templates
        from urllib.parse import unquote
        templates = Jinja2Templates(directory=str(_templates_dir))
        state = derive_page_state(project_root=root)
        flash = None
        flash_msg = request.query_params.get("flash_msg")
        flash_level = request.query_params.get("flash_level", "info")
        if flash_msg:
            flash = {"message": unquote(flash_msg), "level": flash_level}
        return templates.TemplateResponse(request, "operator.html", {
            "state": state,
            "flash": flash,
        })

    # ═════════════════════════════════════════════════════════════════════════
    # POST /action/build
    # ═════════════════════════════════════════════════════════════════════════

    @app.post("/action/build")
    async def action_build(request: Request, repo: str = Form(...)):
        try:
            _validate_repo_name(repo)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        try:
            from .publish_pack import build_publish_pack
            result = build_publish_pack(repo)
            msg = f"Build 完成: {result.get('repo', repo)} (status={result.get('status', '?')})"
            level = "ok" if result.get("status") == "ok" else "error"
        except Exception as e:
            msg = f"Build 失败: {e}"
            level = "error"
        resp = RedirectResponse(url="/", status_code=303)
        _set_flash(resp, msg, level)
        return resp

    # ═════════════════════════════════════════════════════════════════════════
    # POST /action/review
    # ═════════════════════════════════════════════════════════════════════════

    @app.post("/action/review")
    async def action_review(request: Request, pack_dir: str = Form(...)):
        try:
            resolved = _validate_pack_dir(pack_dir, root)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        try:
            from .publish_review import review_pack
            report = review_pack(str(resolved))
            msg = f"Review 完成: verdict={report.verdict}, score={report.overall_score}/100"
            level = "ok" if report.verdict != "rejected" else "error"
        except Exception as e:
            msg = f"Review 失败: {e}"
            level = "error"
        resp = RedirectResponse(url="/", status_code=303)
        _set_flash(resp, msg, level)
        return resp

    # ═════════════════════════════════════════════════════════════════════════
    # POST /action/approve (requires confirmation + checks not published)
    # ═════════════════════════════════════════════════════════════════════════

    @app.post("/action/approve")
    async def action_approve(request: Request, pack_dir: str = Form(...),
                             confirmed: str = Form("false")):
        if confirmed != "true":
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, "请确认 Approve 操作", "error")
            return resp
        try:
            resolved = _validate_pack_dir(pack_dir, root)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        # Check not published
        manifest_path = resolved / "00_publish_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("human_review_status") == "published":
                    resp = RedirectResponse(url="/", status_code=303)
                    _set_flash(resp, "此 pack 已发布，不可再 Approve", "error")
                    return resp
            except (json.JSONDecodeError, OSError):
                pass
        try:
            from .publish_review import approve_pack
            result = approve_pack(str(resolved))
            msg = f"Approve 完成: {result.get('status', '?')}"
            level = "ok" if result.get("status") == "ok" else "error"
        except Exception as e:
            msg = f"Approve 失败: {e}"
            level = "error"
        resp = RedirectResponse(url="/", status_code=303)
        _set_flash(resp, msg, level)
        return resp

    # ═════════════════════════════════════════════════════════════════════════
    # POST /action/reject (requires confirmation + checks not published)
    # ═════════════════════════════════════════════════════════════════════════

    @app.post("/action/reject")
    async def action_reject(request: Request, pack_dir: str = Form(...),
                            reason: str = Form(""), confirmed: str = Form("false")):
        if confirmed != "true":
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, "请确认 Reject 操作并填写原因", "error")
            return resp
        if not reason.strip():
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, "Reject 必须提供原因", "error")
            return resp
        try:
            resolved = _validate_pack_dir(pack_dir, root)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        manifest_path = resolved / "00_publish_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("human_review_status") == "published":
                    resp = RedirectResponse(url="/", status_code=303)
                    _set_flash(resp, "此 pack 已发布，不可再 Reject", "error")
                    return resp
            except (json.JSONDecodeError, OSError):
                pass
        try:
            from .publish_review import reject_pack
            result = reject_pack(str(resolved), _sanitize_note(reason))
            msg = f"Reject 完成: {result.get('status', '?')}"
            level = "ok"
        except Exception as e:
            msg = f"Reject 失败: {e}"
            level = "error"
        resp = RedirectResponse(url="/", status_code=303)
        _set_flash(resp, msg, level)
        return resp

    # ═════════════════════════════════════════════════════════════════════════
    # POST /action/revise (requires confirmation + checks not published)
    # ═════════════════════════════════════════════════════════════════════════

    @app.post("/action/revise")
    async def action_revise(request: Request, pack_dir: str = Form(...),
                            confirmed: str = Form("false")):
        if confirmed != "true":
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, "请确认 Revise 操作", "error")
            return resp
        try:
            resolved = _validate_pack_dir(pack_dir, root)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        manifest_path = resolved / "00_publish_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("human_review_status") == "published":
                    resp = RedirectResponse(url="/", status_code=303)
                    _set_flash(resp, "此 pack 已发布，不可再 Revise", "error")
                    return resp
            except (json.JSONDecodeError, OSError):
                pass
        try:
            from .publish_review import revise_pack
            result = revise_pack(str(resolved))
            msg = f"Revise 完成: issues_count={result.get('issues_count', 0)}"
            level = "ok" if result.get("status") == "ok" else "error"
        except Exception as e:
            msg = f"Revise 失败: {e}"
            level = "error"
        resp = RedirectResponse(url="/", status_code=303)
        _set_flash(resp, msg, level)
        return resp

    # ═════════════════════════════════════════════════════════════════════════
    # POST /action/mark-published (requires confirmation + only approved)
    # ═════════════════════════════════════════════════════════════════════════

    @app.post("/action/mark-published")
    async def action_mark_published(
        request: Request,
        pack_dir: str = Form(...),
        platform: str = Form(...),
        url: str = Form(""),
        note: str = Form(""),
        confirmed: str = Form("false"),
    ):
        if confirmed != "true":
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, "请确认 Mark Published 操作", "error")
            return resp
        try:
            resolved = _validate_pack_dir(pack_dir, root)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        try:
            _validate_platform(platform)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        try:
            safe_url = _sanitize_url(url) if url else ""
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        try:
            from .publish_history import mark_published
            result = mark_published(
                str(resolved), platform, url=safe_url,
                note=_sanitize_note(note), force=False
            )
            msg = result.get("message", result.get("status", "?"))
            level = "ok" if result.get("status") == "ok" else "error"
        except Exception as e:
            msg = f"Mark Published 失败: {e}"
            level = "error"
        resp = RedirectResponse(url="/", status_code=303)
        _set_flash(resp, msg, level)
        return resp

    # ═════════════════════════════════════════════════════════════════════════
    # POST /action/record-metrics (requires confirmation + nonneg validation)
    # ═════════════════════════════════════════════════════════════════════════

    @app.post("/action/record-metrics")
    async def action_record_metrics(
        request: Request,
        repo: str = Form(...),
        platform: str = Form(...),
        views: str = Form("0"),
        likes: str = Form("0"),
        favorites: str = Form("0"),
        comments: str = Form("0"),
        leads: str = Form("0"),
        note: str = Form(""),
        confirmed: str = Form("false"),
    ):
        if confirmed != "true":
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, "请确认 Record Metrics 操作", "error")
            return resp
        try:
            _validate_repo_name(repo)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        try:
            _validate_platform(platform)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, str(e), "error")
            return resp
        try:
            v_views = _validate_nonneg_int(views)
            v_likes = _validate_nonneg_int(likes)
            v_favorites = _validate_nonneg_int(favorites)
            v_comments = _validate_nonneg_int(comments)
            v_leads = _validate_nonneg_int(leads)
        except ValueError as e:
            resp = RedirectResponse(url="/", status_code=303)
            _set_flash(resp, f"数据校验失败: {e}", "error")
            return resp
        try:
            from .metrics import record_metrics
            result = record_metrics(
                repo, platform,
                views=v_views, likes=v_likes, favorites=v_favorites,
                comments=v_comments, leads=v_leads,
                note=_sanitize_note(note),
            )
            msg = result.get("message", result.get("status", "?"))
            level = "ok" if result.get("status") == "ok" else "error"
        except Exception as e:
            msg = f"Record Metrics 失败: {e}"
            level = "error"
        resp = RedirectResponse(url="/", status_code=303)
        _set_flash(resp, msg, level)
        return resp

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# Flash message helper
# ═══════════════════════════════════════════════════════════════════════════════

def _set_flash(response: RedirectResponse, message: str, level: str = "info"):
    """Attach flash message via URL query param (avoids cookie encoding issues)."""
    from urllib.parse import quote
    safe_msg = quote(message.replace("\n", " ")[:500], safe="")
    # Append flash params to redirect URL
    url = response.headers.get("location", "/")
    sep = "&" if "?" in url else "?"
    response.headers["location"] = f"{url}{sep}flash_msg={safe_msg}&flash_level={level}"
