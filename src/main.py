"""CLI entry point for ai-github-blogger.

Usage:
    python -m src.main daily          # Full daily pipeline
    python -m src.main daily --no-llm # Skip LLM analysis
    python -m src.main fetch          # Only fetch repos
    python -m src.main score          # Only score fetched repos
    python -m src.main report         # Generate report from scored repos
    python -m src.main content <repo>  # Generate content pack for a repo
    python -m src.main doctor         # Environment health check
    python -m src.main dry-run        # End-to-end verification without LLM
    python -m src.main benchmark      # Run scoring benchmark
    python -m src.main quality-gate   # Run quality gate evaluation
"""
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path (portable Python workaround)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .analyzer import FDEAnalysis, ai_fde_analyze
from .benchmark import cmd_benchmark
from .quality_gate import cmd_quality_gate
from .config import (
    MAX_REPOS_TO_ANALYZE,
    MAX_REPOS_TO_ENRICH,
    REPORTS_DIR,
)
from .content_pack import CONTENT_FILES_V2, generate_content_pack
from .dedup import SeenReposState, apply_dedup, load_state, mark_as_recommended
from .enricher import enrich_repo
from .fetcher import search_repos
from .report import SkippedRecord, generate_candidate_report, generate_daily_report
from .scorer import apply_classification_and_filters, rank_repos, score_repo

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="ai-github-blogger",
        description="Daily GitHub AI repo discovery and content generation tool.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # daily
    daily_parser = subparsers.add_parser("daily", help="Run full daily pipeline")
    daily_parser.add_argument("--no-llm", action="store_true", help="Skip LLM analysis")

    # fetch
    subparsers.add_parser("fetch", help="Only fetch repos from GitHub")

    # score
    subparsers.add_parser("score", help="Only score repos")

    # report
    subparsers.add_parser("report", help="Generate report from scored repos")

    # content
    content_parser = subparsers.add_parser("content", help="Generate content pack for a repo")
    content_parser.add_argument("repo", help="Repository full name (owner/repo)")

    # benchmark
    subparsers.add_parser("benchmark", help="Run scoring benchmark against golden cases")

    # quality-gate
    subparsers.add_parser("quality-gate", help="Run Phase 6 quality gate evaluation")

    # doctor
    subparsers.add_parser("doctor", help="Environment health check")

    # dry-run
    subparsers.add_parser("dry-run", help="End-to-end verification without LLM")

    # Default to "daily" if no subcommand specified
    parser.set_defaults(command="daily", no_llm=False)

    return parser


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging and fix Windows console encoding."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Fix Windows GBK console encoding for emoji output
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def cmd_daily(no_llm: bool = False) -> int:
    """Run the full daily pipeline.

    1. Fetch repos (RSS + API search)
    2. Dedup
    3. Enrich (up to MAX_REPOS_TO_ENRICH)
    4. Score
    5. Rank → Top 20
    6. Analyze Top N via LLM
    7. Generate daily report
    8. Save report + update state
    """
    logger.info("=== AI GitHub Blogger — Daily Pipeline (v4 四层评分) ===")

    # 1. Fetch
    logger.info("[1/7] Fetching repos from GitHub...")
    raw_repos = search_repos()
    fetched_count = len(raw_repos)
    logger.info("Fetched %d unique repos", fetched_count)

    if not raw_repos:
        logger.warning("No repos fetched. Check network or GitHub token.")
        return 1

    # 2. Dedup
    logger.info("[2/7] Loading dedup state and applying dedup...")
    state = load_state(config.STATE_DIR)
    # Convert RawRepo → EnrichedRepo stub for dedup
    from .enricher import EnrichedRepo

    enriched_stubs = [
        EnrichedRepo(
            full_name=r.full_name,
            name=r.name,
            description=r.description,
            url=r.url,
            language=r.language,
            stars=r.stars_today,
            forks=0,
            open_issues=0,
            updated_at="",
            created_at="",
        )
        for r in raw_repos
    ]
    before_names = {r.full_name for r in enriched_stubs}
    filtered = apply_dedup(enriched_stubs, state)
    after_names = {r.full_name for r in filtered}
    skipped_names = before_names - after_names
    skipped = [SkippedRecord(full_name=name, reason="已生成过内容包，自动跳过") for name in skipped_names]

    logger.info("After dedup: %d candidates (%d skipped)", len(filtered), len(skipped))

    if not filtered:
        logger.warning("All repos filtered by dedup. Try again later.")
        return 0

    # Limit to MAX_REPOS_TO_ENRICH
    filtered = filtered[:MAX_REPOS_TO_ENRICH]

    # 3. Enrich
    logger.info("[3/7] Enriching %d repos...", len(filtered))
    enriched = []
    for repo in filtered:
        result = enrich_repo(repo.full_name)
        if result:
            # Preserve dedup penalty from stub
            result._dedup_penalty = getattr(repo, "_dedup_penalty", 1.0)
            enriched.append(result)
    logger.info("Enriched %d repos", len(enriched))
    enriched_count = len(enriched)
    failed_count = len(filtered) - enriched_count

    # 4. Score
    logger.info("[4/7] Scoring repos...")
    scored = [score_repo(r) for r in enriched]

    # 5. Classify & Filter (v3)
    logger.info("[5/7] Classifying & applying filters...")
    classified = apply_classification_and_filters(scored)
    top5 = classified["runnable_top5"][:5]
    evergreen = classified["evergreen_candidates"]
    resource = classified["resource_candidates"]
    high_risk_skipped = classified["high_risk_skipped"]

    logger.info("Top 5 runnable projects: %s", [r.full_name for r in top5])
    logger.info("Evergreen candidates: %s", [r.full_name for r in evergreen])
    logger.info("Resource candidates: %s", [r.full_name for r in resource])
    logger.info("High-risk skipped: %s", [r.full_name for r in high_risk_skipped])

    # Build top20 for platform picks (top5 + remaining runnable + top evergreen)
    remaining_runnable = classified["runnable_top5"][5:]
    all_pool = top5 + remaining_runnable + evergreen + resource
    top20 = sorted(all_pool, key=lambda r: r.score, reverse=True)[:20]

    # 6. Analyze (LLM)
    analyses: dict[str, FDEAnalysis] = {}
    if not no_llm:
        logger.info("[6/7] Running LLM analysis on top %d...", min(len(top5), MAX_REPOS_TO_ANALYZE))
        for repo in top5[:MAX_REPOS_TO_ANALYZE]:
            logger.info("  Analyzing %s...", repo.full_name)
            analyses[repo.full_name] = ai_fde_analyze(repo)
    else:
        logger.info("[6/7] Skipping LLM analysis (--no-llm)")

    # 7. Generate reports (v3 + Phase 8 daily_brief + review_queue)
    logger.info("[7/7] Generating reports...")
    obs = {"fetched": fetched_count, "enriched": enriched_count, "failed": failed_count}
    report = generate_daily_report(
        top5=top5,
        analyses=analyses,
        top20=top20,
        skipped=skipped,
        evergreen=evergreen,
        resource=resource,
        high_risk=high_risk_skipped,
        obs_stats=obs,
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Daily report
    report_path = REPORTS_DIR / f"daily_report_{today}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info("Daily report saved to %s", report_path)

    # Phase 8: Daily brief (一屏工作台)
    from .report import generate_daily_brief
    brief = generate_daily_brief(
        top5=top5, all_scored=top20, evergreen=evergreen,
        resource=resource, high_risk=high_risk_skipped,
        obs_stats=obs,
    )
    brief_path = REPORTS_DIR / f"daily_brief_{today}.md"
    brief_path.write_text(brief, encoding="utf-8")
    logger.info("Daily brief saved to %s", brief_path)

    # Phase 8: Review queue
    from .report import generate_review_queue
    review = generate_review_queue(
        top5=top5, evergreen=evergreen, resource=resource,
        high_risk=high_risk_skipped, all_scored=top20,
        analyses=analyses,
    )
    review_path = REPORTS_DIR / f"review_queue_{today}.md"
    review_path.write_text(review, encoding="utf-8")
    logger.info("Review queue saved to %s", review_path)

    # 8. Update state — mark top20 + evergreen + resource
    mark_as_recommended([r.full_name for r in top20], config.STATE_DIR)

    print(report)
    return 0


def cmd_fetch() -> int:
    """Fetch repos and print them."""
    repos = search_repos()
    for repo in repos:
        print(f"{repo.full_name:50s} ⭐{repo.stars_today:>6}  {repo.description[:80]}")
    print(f"\nTotal: {len(repos)} unique repos")
    return 0


def cmd_score() -> int:
    """Fetch, enrich, score, and print rankings."""
    raw = search_repos()
    if not raw:
        print("No repos found.")
        return 1

    from .enricher import EnrichedRepo

    enriched = []
    for r in raw[:MAX_REPOS_TO_ENRICH]:
        result = enrich_repo(r.full_name)
        if result:
            enriched.append(result)

    scored = [score_repo(r) for r in enriched]
    ranked = rank_repos(scored, limit=30)

    print(f"{'#':<3} {'Repo':<40} {'Score':>6} {'Stars':>8}")
    print("-" * 60)
    for i, r in enumerate(ranked, 1):
        print(f"{i:<3} {r.full_name:<40} {r.score:>6.1f} {r.stars:>8}")
    return 0


def cmd_report() -> int:
    """Generate a candidate report from fetched repos."""
    raw = search_repos()
    if not raw:
        print("No repos found.")
        return 1

    from .enricher import EnrichedRepo

    enriched = []
    for r in raw[:MAX_REPOS_TO_ENRICH]:
        result = enrich_repo(r.full_name)
        if result:
            enriched.append(result)

    scored = [score_repo(r) for r in enriched]
    top20 = rank_repos(scored, limit=20)
    report = generate_candidate_report(top20)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"daily_report_{today}.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nSaved to {report_path}")
    return 0


def cmd_doctor() -> int:
    """Check environment health with pass/warn/fail grading.

    Grading:
      - PASS: fully operational
      - WARN: can operate with limitations (e.g. no LLM, SSL env issue)
      - FAIL: cannot operate (e.g. no token, no .env)

    Returns 0 for pass/warn, 1 for fail.
    """
    import os
    import sys as _sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent
    failures: list[str] = []
    warns: list[str] = []
    passes: list[str] = []

    def grade_pass(name: str, detail: str = ""):
        line = f"  [PASS] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
        passes.append(name)

    def grade_warn(name: str, detail: str = ""):
        line = f"  [WARN] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
        warns.append(name)

    def grade_fail(name: str, detail: str = ""):
        line = f"  [FAIL] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
        failures.append(name)

    print("=" * 60)
    print("  AI GitHub Blogger — Environment Doctor")
    print("=" * 60)
    print()
    print(f"  Project root: {project_root}")
    print()

    # 1. Python version
    py_ver = _sys.version_info
    if py_ver >= (3, 10):
        grade_pass("Python version", f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    else:
        grade_fail("Python version", f"{py_ver.major}.{py_ver.minor}.{py_ver.micro} (>= 3.10 required)")

    # 2. .env file
    env_path = project_root / ".env"
    if env_path.exists():
        grade_pass(".env file", str(env_path))
    else:
        grade_fail(".env file", "not found — create from .env.example")

    # 3. GITHUB_TOKEN
    github_token = os.getenv("GITHUB_TOKEN") or ""
    if not github_token and env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GITHUB_TOKEN="):
                    github_token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if github_token:
        grade_pass("GITHUB_TOKEN", "set")
    else:
        grade_fail("GITHUB_TOKEN", "not set — GitHub API will be rate-limited (60 req/h)")

    # 4. LLM_API_KEY — always WARN if missing (optional)
    llm_key = os.getenv("LLM_API_KEY") or ""
    if not llm_key and env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("LLM_API_KEY="):
                    llm_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if llm_key:
        grade_pass("LLM_API_KEY", "set")
    else:
        grade_warn("LLM_API_KEY", "not set (optional — run with --no-llm)")

    # 5. GitHub API connectivity — SSL/env issues = WARN, not FAIL
    github_reachable = False
    try:
        import requests
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ai-github-blogger/1.0"}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
        if resp.status_code == 200:
            rate = resp.json()
            core = rate.get("resources", {}).get("core", {})
            remaining = core.get("remaining", "?")
            limit = core.get("limit", "?")
            grade_pass("GitHub API connectivity", f"rate limit: {remaining}/{limit} remaining")
            github_reachable = True
        elif resp.status_code == 401:
            grade_fail("GitHub API connectivity", "401 Unauthorized — check GITHUB_TOKEN")
        else:
            grade_warn("GitHub API connectivity", f"HTTP {resp.status_code}")
    except Exception as e:
        # SSL/TLS errors in restricted environments = WARN, not FAIL
        # The pipeline can still work with --no-llm + cached data
        grade_warn("GitHub API connectivity", f"network restricted (SSL/proxy): {type(e).__name__}")
        warns.append("GitHub API unreachable — daily pipeline may fail, but cached/doc-only operations still work")

    # 6. data/state writable
    state_dir = project_root / "data" / "state"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        test_file = state_dir / ".doctor_test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        grade_pass("data/state writable", str(state_dir))
    except Exception as e:
        grade_fail("data/state writable", str(e))

    # 7. data/cache writable
    cache_dir = project_root / "data" / "cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        test_file = cache_dir / ".doctor_test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        grade_pass("data/cache writable", str(cache_dir))
    except Exception as e:
        grade_warn("data/cache writable", str(e))

    # 8. templates completeness
    templates_dir = project_root / "templates"
    expected_templates = [
        "ai_fde_analysis.md", "deep_analysis.md", "xiaohongshu.md",
        "video_script.md", "douyin.md", "wechat_article.md",
        "storyboard.md", "risk_review.md", "quality_check.md", "scorer_rules.md",
    ]
    if templates_dir.exists():
        missing = [t for t in expected_templates if not (templates_dir / t).exists()]
        if missing:
            grade_warn("templates/ completeness", f"missing: {', '.join(missing)}")
        else:
            grade_pass("templates/ completeness", f"{len(expected_templates)} files")
    else:
        grade_warn("templates/ completeness", "templates/ directory not found")

    # 9. Latest daily report
    reports_dir = project_root / "data" / "reports"
    if reports_dir.exists():
        reports = sorted(reports_dir.glob("daily_report_*.md"), reverse=True)
        if reports:
            grade_pass("Latest daily report", f"{reports[0].name} ({reports[0].stat().st_size} bytes)")
        else:
            grade_warn("Latest daily report", "no daily reports found — run 'python run.py daily --no-llm'")
    else:
        grade_warn("Latest daily report", "data/reports/ directory not found")

    # 10. error_handler module
    try:
        from . import error_handler
        grade_pass("error_handler module", "importable")
    except Exception as e:
        grade_fail("error_handler module", str(e))

    print()

    # ── Summary ──────────────────────────────────────────────────────
    print(f"  PASS: {len(passes)} | WARN: {len(warns)} | FAIL: {len(failures)}")
    print()

    if failures:
        print("  Fix suggestions for FAIL items:")
        for f in failures[:5]:
            if "GITHUB_TOKEN" in f:
                print("    - Set GITHUB_TOKEN in .env (generate at github.com/settings/tokens)")
            elif ".env" in f:
                print("    - Copy .env.example to .env and fill in GITHUB_TOKEN")
            elif "Python" in f:
                print("    - Upgrade to Python 3.10+")
            elif "writable" in f:
                print("    - Check filesystem permissions for data/ directory")
        print()

    if warns:
        print("  Warnings (non-blocking):")
        for w in warns[:5]:
            print(f"    - {w}")
        print()

    # Overall status
    if failures:
        status = "FAIL"
        print("  Overall: FAIL — fix the FAIL items above before running daily pipeline.")
        return 1
    elif warns:
        status = "WARN"
        print("  Overall: WARN — system operational with limitations.")
        if not llm_key:
            print("  Tip: Use --no-llm flag for all commands.")
        return 0
    else:
        status = "PASS"
        print("  Overall: PASS — system ready for daily use.")
        if llm_key:
            print("  Ready for LLM: yes — LLM_API_KEY configured.")
        else:
            print("  Ready for LLM: conditional — add LLM_API_KEY for AI-powered content.")
        return 0


def cmd_dry_run() -> int:
    """End-to-end verification without LLM — check all 8 steps of the pipeline.

    Dry-run outputs:
      ready_for_llm: yes / no / conditional
      recommended_repo_for_llm: which repo to connect LLM for first
      manual_review_required: list of items needing human review
      estimated_human_time: minutes required for manual steps
      remaining_risks: known issues not yet resolved
    """
    import time
    from datetime import datetime, timezone

    print("=" * 60)
    print("  AI GitHub Blogger — Dry-Run Verification (Phase 9)")
    print("=" * 60)
    print()
    start_time = time.time()

    # ── Step 1: Doctor check ────────────────────────────────────────────
    print("── Step 1/8: Environment Health Check ──")
    doctor_ok = True
    doctor_warns: list[str] = []

    import os
    project_root = Path(__file__).resolve().parent.parent

    # 1a. Python version
    py_ver = sys.version_info
    if py_ver < (3, 10):
        print(f"  [FAIL] Python {py_ver.major}.{py_ver.minor} — need 3.10+")
        doctor_ok = False
    else:
        print(f"  [PASS] Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")

    # 1b. .env + GITHUB_TOKEN
    env_path = project_root / ".env"
    github_token = os.getenv("GITHUB_TOKEN") or ""
    if not github_token and env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GITHUB_TOKEN="):
                    github_token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if not github_token:
        print("  [FAIL] GITHUB_TOKEN not set")
        doctor_ok = False
    else:
        print("  [PASS] GITHUB_TOKEN set")

    # 1c. LLM_API_KEY
    llm_key = os.getenv("LLM_API_KEY") or ""
    if not llm_key and env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("LLM_API_KEY="):
                    llm_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if llm_key:
        print("  [PASS] LLM_API_KEY set")
    else:
        print("  [WARN] LLM_API_KEY not set (--no-llm mode is active)")
        doctor_warns.append("LLM_API_KEY missing — content pack will use rule-based fallbacks")

    # 1d. data dirs writable
    for sub in ["state", "cache"]:
        d = project_root / "data" / sub
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / ".dry_run_test").write_text("", encoding="utf-8")
            (d / ".dry_run_test").unlink()
        except Exception:
            print(f"  [FAIL] data/{sub} not writable")
            doctor_ok = False
    print()

    # ── Step 2: Daily --no-llm ──────────────────────────────────────────
    print("── Step 2/8: Daily Pipeline (--no-llm) ──")
    daily_ok = False
    top5: list = []
    all_scored: list = []
    evergreen: list = []
    resource: list = []
    high_risk: list = []
    obs_stats: dict = {}
    try:
        raw = search_repos()
        fetched_count = len(raw)
        print(f"  Fetched: {fetched_count} repos")

        if raw:
            from .enricher import EnrichedRepo as ER

            stubs = [
                ER(full_name=r.full_name, name=r.name, description=r.description,
                   url=r.url, language=r.language, stars=r.stars_today,
                   forks=0, open_issues=0, updated_at="", created_at="")
                for r in raw
            ]
            enriched = []
            for repo in stubs[:MAX_REPOS_TO_ENRICH]:
                result = enrich_repo(repo.full_name)
                if result:
                    result._dedup_penalty = getattr(repo, "_dedup_penalty", 1.0)
                    enriched.append(result)

            scored = [score_repo(r) for r in enriched]
            classified = apply_classification_and_filters(scored)
            top5 = classified["runnable_top5"][:5]
            evergreen = classified["evergreen_candidates"]
            resource = classified["resource_candidates"]
            high_risk = classified["high_risk_skipped"]
            remaining = classified["runnable_top5"][5:]
            all_scored = sorted(top5 + remaining + evergreen + resource, key=lambda r: r.score, reverse=True)[:20]
            obs_stats = {"fetched": fetched_count, "enriched": len(enriched),
                         "failed": len(stubs[:MAX_REPOS_TO_ENRICH]) - len(enriched)}

            print(f"  Top 5: {[r.full_name for r in top5]}")
            print(f"  Evergreen: {len(evergreen)}, Resource: {len(resource)}, High-risk: {len(high_risk)}")
            daily_ok = len(top5) > 0
        else:
            print("  [WARN] No repos fetched — GitHub API may be unreachable")
    except Exception as e:
        print(f"  [WARN] Daily pipeline error: {e}")

    print()

    # ── Step 3: Daily brief ─────────────────────────────────────────────
    print("── Step 3/8: Daily Brief Generation ──")
    brief_ok = False
    try:
        from .report import generate_daily_brief
        brief = generate_daily_brief(
            top5=top5, all_scored=all_scored, evergreen=evergreen,
            resource=resource, high_risk=high_risk, obs_stats=obs_stats,
        )
        brief_len = len(brief)
        print(f"  Daily brief: {brief_len} chars")
        brief_ok = brief_len > 200
    except Exception as e:
        print(f"  [FAIL] Daily brief generation error: {e}")
    print()

    # ── Step 4: Review queue ────────────────────────────────────────────
    print("── Step 4/8: Review Queue Generation ──")
    review_ok = False
    try:
        from .report import generate_review_queue
        review = generate_review_queue(
            top5=top5, evergreen=evergreen, resource=resource,
            high_risk=high_risk, all_scored=all_scored, analyses={},
        )
        review_len = len(review)
        print(f"  Review queue: {review_len} chars")
        review_ok = review_len > 200
    except Exception as e:
        print(f"  [FAIL] Review queue generation error: {e}")
    print()

    # ── Step 5: Pick recommended repo ───────────────────────────────────
    print("── Step 5/8: Select Recommended Repo ──")
    recommended_repo = None
    if top5:
        recommended_repo = top5[0].full_name
        print(f"  Recommended: {recommended_repo} (score={top5[0].score:.0f})")
    else:
        print("  [WARN] No top5 repos — cannot recommend a repo for LLM content pack")
    print()

    # ── Step 6: Content pack (no-LLM fallback) ──────────────────────────
    print("── Step 6/8: Content Pack Generation (no-LLM) ──")
    content_ok = False
    content_degraded = False
    pack_dir = None
    if recommended_repo:
        try:
            pack_dir, status = generate_content_pack(recommended_repo)
            content_degraded = (status == "degraded")
            content_ok = (status in ("ok", "degraded"))
            file_count = len(list(pack_dir.glob("*.md"))) if pack_dir.exists() else 0
            print(f"  Generated {file_count} files, status={status}")
        except Exception as e:
            print(f"  [WARN] Content pack generation failed: {e}")
    else:
        print("  [SKIP] No recommended repo")
    print()

    # ── Step 7: Manifest check ──────────────────────────────────────────
    print("── Step 7/8: Manifest Verification ──")
    manifest_ok = False
    manifest_info: dict = {}
    if pack_dir and pack_dir.exists():
        manifest_path = pack_dir / "_manifest.json"
        if manifest_path.exists():
            try:
                manifest_info = json.loads(manifest_path.read_text(encoding="utf-8"))
                print(f"  Files generated: {manifest_info.get('files_generated', 0)}")
                print(f"  Files degraded: {manifest_info.get('files_degraded', 0)}")
                print(f"  LLM mode: {manifest_info.get('llm_mode', 'unknown')}")
                print(f"  Quality status: {manifest_info.get('quality_status', 'unknown')}")
                print(f"  Risk level: {manifest_info.get('risk_level', 'unknown')}")
                manifest_ok = manifest_info.get("files_generated", 0) > 0
            except Exception as e:
                print(f"  [WARN] Manifest read error: {e}")
        else:
            print("  [WARN] Manifest not found")
    else:
        print("  [SKIP] No content pack generated")
    print()

    # ── Step 8: Quality gate ────────────────────────────────────────────
    print("── Step 8/8: Quality Gate ──")
    gate: dict = {}
    try:
        from .quality_gate import (
            evaluate_quality_gate_v8,
            generate_system_quality_report_v8,
            detect_overfit,
        )
        bm_result = None
        adv_result = None
        try:
            from .benchmark import run_benchmark, run_adversarial_benchmark
            bm_result = run_benchmark()
            adv_path = project_root / "tests" / "fixtures" / "adversarial_cases.json"
            adv_result = run_adversarial_benchmark(adv_path)
        except Exception:
            pass

        quality = generate_system_quality_report_v8(
            benchmark_result=bm_result,
            adversarial_result=adv_result,
            content_command_ok=content_ok,
            content_degraded=content_degraded,
        )

        dims = quality.get("dimensions", {})
        sr = dims.get("skill_readiness_quality", {})
        sub_dims = sr.get("sub_dimensions", {})
        sr_score = float(sr.get("score", 0))
        er_score = float(sub_dims.get("error_recovery", 55))
        hr_score = float(sub_dims.get("human_review_flow", 60))
        or_score = float(dims.get("operational_readiness", {}).get("score", 0))

        gate = evaluate_quality_gate_v8(
            benchmark_result=bm_result,
            adversarial_result=adv_result,
            system_quality_scores={k: v for k, v in dims.items()},
            skill_readiness_score=sr_score,
            error_recovery_score=er_score,
            human_review_flow_score=hr_score,
            operational_readiness_score=or_score,
            content_command_ok=content_ok,
            content_degraded=content_degraded,
        )
        print(f"  Verdict: {gate['verdict'].upper()}")
        print(f"  Score: {gate['adjusted_score']}/100")
        print(f"  Passed: {gate['passed_count']}/{gate['total_count']}")
        print(f"  Ready for LLM key: {gate.get('whether_ready_for_llm_key', 'unknown')}")
        print(f"  Why not 100: {gate.get('why_not_100', 'N/A')}")
    except Exception as e:
        print(f"  [WARN] Quality gate evaluation error: {e}")
    print()

    # ── Final Summary ───────────────────────────────────────────────────
    elapsed = time.time() - start_time

    ready_for_llm = gate.get("whether_ready_for_llm_key", "no") if gate else "no"
    manual_review_required: list[str] = []
    remaining_risks: list[str] = []

    if not llm_key:
        remaining_risks.append("LLM_API_KEY not configured — content quality limited to rule-based fallbacks")
    if content_degraded:
        remaining_risks.append("Content pack degraded — some files use cached/stub data")
    if not daily_ok:
        remaining_risks.append("GitHub API unreachable — daily pipeline cannot fetch fresh repos")
    if not recommended_repo:
        remaining_risks.append("No high-confidence repo available for content pack generation")
    if not doctor_ok:
        remaining_risks.append("Environment has FAIL items — fix before connecting LLM")

    blocking = gate.get("blocking_issues", []) if gate else []
    for b in blocking:
        manual_review_required.append(f"[BLOCKER] {b}")

    non_blocking = gate.get("non_blocking_issues", []) if gate else []
    for nb in non_blocking:
        manual_review_required.append(f"[WARN] {nb}")

    # Estimate human time
    human_minutes = 0
    if manual_review_required:
        human_minutes += len(manual_review_required) * 3
    if not llm_key:
        human_minutes += 5  # time to get/set API key
    if content_degraded:
        human_minutes += 10  # review degraded content

    print("=" * 60)
    print("  DRY-RUN SUMMARY")
    print("=" * 60)
    print(f"  Elapsed:              {elapsed:.1f}s")
    print(f"  Doctor:               {'PASS' if doctor_ok else 'FAIL'}{' (with warnings)' if doctor_warns else ''}")
    print(f"  Daily pipeline:       {'PASS' if daily_ok else 'FAIL'}")
    print(f"  Daily brief:          {'PASS' if brief_ok else 'FAIL'}")
    print(f"  Review queue:         {'PASS' if review_ok else 'FAIL'}")
    print(f"  Recommended repo:     {recommended_repo or 'NONE'}")
    print(f"  Content pack:         {'PASS' if content_ok else 'FAIL'}{' (degraded)' if content_degraded else ''}")
    print(f"  Manifest:             {'PASS' if manifest_ok else 'FAIL'}")
    print(f"  Quality gate:         {gate.get('verdict', 'N/A').upper() if gate else 'N/A'}")
    print()
    print(f"  ready_for_llm:        {ready_for_llm}")
    print(f"  recommended_repo:     {recommended_repo or 'none — run daily pipeline first'}")
    print(f"  estimated_human_time: ~{human_minutes} min")
    print()

    if manual_review_required:
        print("  Manual review required:")
        for item in manual_review_required:
            print(f"    - {item}")
        print()

    if remaining_risks:
        print("  Remaining risks:")
        for r in remaining_risks:
            print(f"    - {r}")
        print()

    if doctor_warns:
        print("  Doctor warnings:")
        for w in doctor_warns:
            print(f"    - {w}")
        print()

    print("=" * 60)

    if ready_for_llm == "yes":
        return 0
    elif ready_for_llm == "conditional":
        return 2
    else:
        return 1 if not doctor_ok else 0


def cmd_content(repo_full_name: str) -> int:
    """Generate content pack for a specific repo (Phase 7: retry + degraded)."""
    logger.info("Generating V2 content pack for %s...", repo_full_name)
    logger.info("Files: %s", ", ".join(CONTENT_FILES_V2))
    pack_dir, status = generate_content_pack(repo_full_name)
    logger.info("Content pack generated at %s (status=%s)", pack_dir, status)

    # List generated files
    files = sorted(pack_dir.glob("*.md"))
    for f in files:
        print(f"  {f.name} ({f.stat().st_size} bytes)")
    print(f"\nTotal: {len(files)} files in {pack_dir}")
    print(f"Status: {status}")

    # Read manifest
    manifest_path = pack_dir / "_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"  Generated: {manifest.get('files_generated', 0)}")
        print(f"  Degraded:  {manifest.get('files_degraded', 0)}")
        print(f"  Failed:    {manifest.get('files_failed', 0)}")

    # Show which files are TODOs vs complete
    for f in files:
        content = f.read_text(encoding="utf-8")
        degraded = "source_status: degraded" in content
        todo_count = content.count("[TODO")
        if degraded:
            print(f"  ⚠ {f.name}: DEGRADED (retries exhausted)")
        elif todo_count > 0:
            print(f"  ⚠ {f.name}: {todo_count} TODO(s) remaining (needs LLM)")
        else:
            print(f"  ✅ {f.name}: complete")

    if status == "failed":
        return 1
    elif status == "degraded":
        return 2  # conditional pass
    return 0


def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    _setup_logging()

    if args.command == "benchmark":
        return cmd_benchmark()
    elif args.command == "quality-gate":
        return cmd_quality_gate()
    elif args.command == "doctor":
        return cmd_doctor()
    elif args.command == "dry-run":
        return cmd_dry_run()
    elif args.command == "daily":
        return cmd_daily(no_llm=args.no_llm)
    elif args.command == "fetch":
        return cmd_fetch()
    elif args.command == "score":
        return cmd_score()
    elif args.command == "report":
        return cmd_report()
    elif args.command == "content":
        if not args.repo:
            parser.error("content command requires a repo argument (owner/repo)")
        return cmd_content(args.repo)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
