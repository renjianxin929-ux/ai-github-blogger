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

    # daily-workflow (Phase 13)
    subparsers.add_parser("daily-workflow", help="One-command daily workflow: doctor → daily → quality-gate")

    # review-queue (Phase 13)
    subparsers.add_parser("review-queue", help="Show human review checklist from latest daily run")

    # llm-doctor (Phase 15)
    subparsers.add_parser("llm-doctor", help="Diagnose LLM provider connectivity")

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

    # 8. templates completeness (including content pack template map)
    templates_dir = project_root / "templates"
    expected_templates = [
        "ai_fde_analysis.md", "deep_analysis.md", "xiaohongshu.md",
        "video_script.md", "douyin.md", "wechat_article.md",
        "storyboard.md", "risk_review.md", "quality_check.md", "scorer_rules.md",
        "00_repo_snapshot.md", "07_geo_angle.md", "08_enterprise_pitch.md",
    ]
    if templates_dir.exists():
        # Verify content pack template map coverage
        try:
            from .content_pack import CONTENT_PACK_TEMPLATE_MAP, CONTENT_FILES_V2
            cp_missing = []
            for out_name in CONTENT_FILES_V2:
                tmpl_name = CONTENT_PACK_TEMPLATE_MAP.get(out_name, out_name)
                tmpl_path = templates_dir / f"{tmpl_name}.md"
                if not tmpl_path.exists():
                    cp_missing.append(f"{out_name}→{tmpl_name}.md")
            if cp_missing:
                grade_warn("content pack templates", f"missing: {', '.join(cp_missing)}")
            else:
                grade_pass("content pack templates", f"all {len(CONTENT_FILES_V2)} files mapped")
        except Exception:
            pass
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
    """Phase 13 enhanced dry-run: zero LLM, zero side effects, writes report.

    Simulates: daily → content → quality-gate → review_queue
    Output: pool assignments, API estimates, risk items, ready_for_llm
    Writes: data/reports/dry_run_report_{date}.md (NOT real content_pack)
    """
    import os
    import time
    from datetime import datetime, timezone

    start_time = time.time()
    project_root = Path(__file__).resolve().parent.parent
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("=" * 64)
    print("  AI GitHub Blogger — Dry-Run Report (Phase 13)")
    print("=" * 64)
    print()

    # ── Step 1: Doctor (silent) ───────────────────────────────────────
    print("── Step 1/9: Environment Health ──")
    doctor_ok = True
    doctor_warns: list[str] = []

    py_ver = sys.version_info
    if py_ver < (3, 10):
        print(f"  [FAIL] Python {py_ver.major}.{py_ver.minor} — need 3.10+")
        doctor_ok = False
    else:
        print(f"  [PASS] Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")

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

    llm_key = os.getenv("LLM_API_KEY") or ""
    if not llm_key and env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("LLM_API_KEY="):
                    llm_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    llm_configured = bool(llm_key)
    if llm_configured:
        print("  [PASS] LLM_API_KEY set")
    else:
        print("  [WARN] LLM_API_KEY not set — content generation will be no-LLM only")
        doctor_warns.append("LLM_API_KEY missing")

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

    # ── Step 2: Fetch ──────────────────────────────────────────────────
    print("── Step 2/9: Fetch Repos ──")
    fetched_count = 0
    raw = []
    try:
        raw = search_repos()
        fetched_count = len(raw)
        print(f"  Fetched: {fetched_count} repos from GitHub API")
    except Exception as e:
        print(f"  [WARN] Fetch failed: {e}")
    if not raw:
        print("  [SKIP] No repos to process — pipeline stopped")
        print()
        print("=" * 64)
        print("  DRY-RUN ABORTED: No repos available")
        print("=" * 64)
        return 1
    print()

    # ── Step 3: Enrich + Score + Classify (no LLM) ────────────────────
    print("── Step 3/9: Enrich, Score & Classify ──")
    from .enricher import EnrichedRepo as ER

    stubs = [
        ER(full_name=r.full_name, name=r.name, description=r.description,
           url=r.url, language=r.language, stars=r.stars_today,
           forks=0, open_issues=0, updated_at="", created_at="")
        for r in raw
    ]
    enriched = []
    enrich_api_calls = min(len(stubs), MAX_REPOS_TO_ENRICH)
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

    print(f"  Enriched: {len(enriched)}/{enrich_api_calls} repos")
    print(f"  Scored:   {len(scored)} repos")
    print()

    # ── Step 4: Pool Assignments ──────────────────────────────────────
    print("── Step 4/9: Pool Assignments ──")
    print(f"  ⭐ Top5 (runnable):  {len(top5):>2}  → {', '.join(r.full_name for r in top5) or '(none)'}")
    print(f"  🌲 Evergreen:        {len(evergreen):>2}  → {', '.join(r.full_name for r in evergreen) or '(none)'}")
    print(f"  📚 Resource:         {len(resource):>2}  → {', '.join(r.full_name for r in resource) or '(none)'}")
    if high_risk:
        print(f"  🚫 Blocked (high-risk): {len(high_risk):>2}  → {', '.join(r.full_name for r in high_risk)}")
    else:
        print(f"  🚫 Blocked (high-risk):  0")
    needs_review = [r for r in (remaining or []) if r.pool == "review"]
    if needs_review:
        print(f"  🔍 Needs Review:     {len(needs_review):>2}  → {', '.join(r.full_name for r in needs_review)}")
    else:
        print(f"  🔍 Needs Review:      0")
    print()

    # ── Step 5: Content Pack Simulation ───────────────────────────────
    print("── Step 5/9: Content Pack Simulation (no-LLM, no file writes) ──")
    if top5:
        try:
            pack_dir, sim_status = generate_content_pack(
                top5[0].full_name, dry_run=True,
            )
            llm_mode = "LLM" if llm_configured else "No-LLM"
            print(f"  Top1 candidate: {top5[0].full_name} (score={top5[0].score:.0f})")
            print(f"  Simulated mode: {llm_mode}")
            print(f"  Would generate: {len(CONTENT_FILES_V2)} content files")
            print(f"  Simulated status: {sim_status}")
        except Exception as e:
            print(f"  [WARN] Content pack simulation error: {e}")
    else:
        print("  [SKIP] No runnable repos for content pack simulation")
    print()

    # ── Step 6: Quality Gate ──────────────────────────────────────────
    print("── Step 6/9: Quality Gate ──")
    gate: dict = {}
    try:
        from .quality_gate import evaluate_quality_gate_v8, generate_system_quality_report_v8

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
            content_command_ok=True,
            content_degraded=False,
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
            content_command_ok=True,
            content_degraded=False,
        )
        print(f"  Verdict: {gate.get('verdict', 'N/A').upper()}")
        print(f"  Score: {gate.get('adjusted_score', 'N/A')}/100")
        print(f"  Passed: {gate.get('passed_count', '?')}/{gate.get('total_count', '?')}")
    except Exception as e:
        print(f"  [WARN] Quality gate error: {e}")
    print()

    # ── Step 7: Review Queue Generation ───────────────────────────────
    print("── Step 7/9: Review Queue ──")
    try:
        all_scored = sorted(
            top5 + list(remaining) + list(evergreen) + list(resource),
            key=lambda r: r.score, reverse=True,
        )[:20]
        from .report import generate_review_queue
        review = generate_review_queue(
            top5=top5, evergreen=evergreen, resource=resource,
            high_risk=high_risk, all_scored=all_scored, analyses={},
        )
        review_len = len(review)
        print(f"  Review queue: {review_len} chars generated")
    except Exception as e:
        print(f"  [WARN] Review queue error: {e}")
    print()

    # ── Step 8: API & Time Estimates ──────────────────────────────────
    print("── Step 8/9: Resource Estimates ──")
    api_calls = {
        "fetch (search)": 1,
        "enrich (per repo)": enrich_api_calls,
    }
    total_api = sum(api_calls.values())
    llm_calls = 0
    if llm_configured and top5:
        # estimate: top5[0] content_pack = 11 LLM calls + FDE analysis = 1
        llm_calls = len(CONTENT_FILES_V2) + 1
        api_calls["LLM content generation (estimated)"] = llm_calls
        total_api += llm_calls

    print(f"  GitHub API calls: {sum(v for k, v in api_calls.items() if 'LLM' not in k)}")
    print(f"  LLM calls (estimated): {llm_calls}")
    print(f"  Total API calls: {total_api}")

    est_seconds = 30 + enrich_api_calls * 2 + 5
    if llm_configured:
        est_seconds += llm_calls * 15  # ~15s per LLM call
        print(f"  Estimated time (LLM mode): ~{est_seconds // 60}min {est_seconds % 60}s")
    else:
        print(f"  Estimated time (no-LLM mode): ~{est_seconds}s")
    print()

    # ── Step 9: Risk Items & Recommendations ──────────────────────────
    print("── Step 9/9: Risk Items & Next Actions ──")
    remaining_risks: list[str] = []
    if not llm_configured:
        remaining_risks.append("LLM_API_KEY not configured — content pack limited to rule-based fallbacks")
    if high_risk:
        remaining_risks.append(f"{len(high_risk)} high-risk repos blocked ({', '.join(r.full_name for r in high_risk[:3])})")
    if not doctor_ok:
        remaining_risks.append("Environment has FAIL items — fix before generating content")

    if remaining_risks:
        for r in remaining_risks:
            print(f"  ⚠ {r}")
    else:
        print("  ✅ No risk items detected")
    print()

    # Recommended next action
    print("  Recommended next actions:")
    if llm_configured and top5:
        print(f"    python run.py content {top5[0].full_name}    # Generate content for Top1")
    elif top5:
        print(f"    python run.py content {top5[0].full_name}    # Generate content (no-LLM)")
    print("    python run.py daily-workflow                  # Full daily workflow")
    print("    python run.py review-queue                    # Human review checklist")
    print()

    # ── Determine ready_for_llm ───────────────────────────────────────
    ready = gate.get("whether_ready_for_llm_key", "no") if gate else "no"
    if not llm_configured:
        ready = "no (LLM_API_KEY not configured)"
    elif ready == "yes":
        ready = "yes — system ready, LLM key present"

    elapsed = time.time() - start_time

    # ── Write dry_run_report ──────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_lines = [
        f"# Dry-Run Report — {today}",
        "",
        f"生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## 数据摘要",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 抓取 repos | {fetched_count} |",
        f"| 增强 repos | {len(enriched)} |",
        f"| 评分 repos | {len(scored)} |",
        "",
        "## Pool 分配",
        "",
        f"| Pool | 数量 | 项目 |",
        f"|------|------|------|",
        f"| ⭐ Top5 (runnable) | {len(top5)} | {', '.join(r.full_name for r in top5) or '(none)'} |",
        f"| 🌲 Evergreen | {len(evergreen)} | {', '.join(r.full_name for r in evergreen) or '(none)'} |",
        f"| 📚 Resource | {len(resource)} | {', '.join(r.full_name for r in resource) or '(none)'} |",
        f"| 🚫 Blocked (high-risk) | {len(high_risk)} | {', '.join(r.full_name for r in high_risk) or '(none)'} |",
        "",
        "## 预估资源",
        "",
        f"- GitHub API 调用：{sum(v for k, v in api_calls.items() if 'LLM' not in k)} 次",
        f"- LLM 调用（预估）：{llm_calls} 次",
        f"- 预计耗时：{elapsed:.0f}s (实际 dry-run) / ~{est_seconds}s (实际执行)",
        "",
        "## 系统状态",
        "",
        f"- Doctor: {'PASS' if doctor_ok else 'FAIL'}",
        f"- Quality Gate: {gate.get('verdict', 'N/A').upper() if gate else 'N/A'} ({gate.get('adjusted_score', 'N/A')}/100)" if gate else "",
        f"- ready_for_llm: {ready}",
        "",
    ]
    if remaining_risks:
        report_lines.append("## 风险项")
        report_lines.append("")
        for r in remaining_risks:
            report_lines.append(f"- {r}")
        report_lines.append("")

    report_lines.extend([
        "## 建议下一步",
        "",
    ])
    if llm_configured and top5:
        report_lines.append(f"- `python run.py content {top5[0].full_name}` — 为 Top1 生成内容包")
    elif top5:
        report_lines.append(f"- `python run.py content {top5[0].full_name}` — 为 Top1 生成内容包（no-LLM）")
    report_lines.append("- `python run.py daily-workflow` — 一键执行完整日更流程")
    report_lines.append("- `python run.py review-queue` — 查看人工审核清单")
    report_lines.append("")

    report_path = REPORTS_DIR / f"dry_run_report_{today}.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"  Report saved: {report_path}")
    print()

    # ── Final Summary ─────────────────────────────────────────────────
    print("=" * 64)
    print("  DRY-RUN SUMMARY")
    print("=" * 64)
    print(f"  Elapsed:          {elapsed:.1f}s")
    print(f"  Doctor:           {'PASS' if doctor_ok else 'FAIL'}")
    print(f"  Fetched:          {fetched_count} repos")
    print(f"  Top5 candidates:  {len(top5)}")
    print(f"  Blocked:          {len(high_risk)}")
    print(f"  Quality Gate:     {gate.get('verdict', 'N/A').upper() if gate else 'N/A'}")
    print(f"  ready_for_llm:    {ready}")
    print(f"  Report:           {report_path}")
    print("=" * 64)

    if not doctor_ok:
        return 1
    return 0


def cmd_daily_workflow() -> int:
    """Phase 15: One-command daily workflow — 3-section concise output.

    Sections: 今天能发布吗 / 最推荐的项目及理由 / 下一步命令.
    """
    import os
    from datetime import datetime, timezone

    from .analyzer import _call_llm_with_failover
    from .config import get_llm_providers

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── LLM health check ──
    llm_available = False
    providers = get_llm_providers()
    if providers:
        try:
            result = _call_llm_with_failover(
                system_prompt="Reply with just OK.",
                user_prompt="OK",
                temperature=0.0,
                max_retries_per_provider=0,
            )
            llm_available = result.success
        except Exception:
            llm_available = False

    # ── Run daily pipeline ──
    daily_rc = cmd_daily(no_llm=True)

    # ── Collect top5 info ──
    import json as _json
    top5_path = REPORTS_DIR / f"top5_{today}.json"
    top5 = []
    if top5_path.exists():
        try:
            top5 = _json.loads(top5_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    print()
    print("=" * 64)
    print(f"  Daily Workflow — {today}")
    print("=" * 64)
    print()

    # ── Section 1: 今天能发布吗 ──
    print("── 今天能发布吗？ ──")
    print()
    if llm_available:
        print("  ✅ LLM 可用 — 内容生成模式: full_llm")
        print("     生成的公众号文章、小红书等可直接发布（需人工通读）。")
    else:
        print("  ⚠️  LLM 不可用 — 内容生成模式: structured_fallback")
        print("     今天不能直接发布，只能进入人工改稿。")
        print("     生成的是研究简报（research brief），不是可发布文章。")
        print("     请用简报中的素材在 30 分钟内人工补写。")
    print()

    # ── Section 2: 最推荐的项目及理由 ──
    print("── 最推荐的项目及理由 ──")
    print()
    if top5:
        best = top5[0]
        name = best.get("full_name", best.get("name", "unknown"))
        stars = best.get("stars", 0)
        score = best.get("score", 0)
        pub_score = best.get("publishability_score", 0)
        desc = best.get("description", "")[:120]
        content_type = best.get("content_type", "unclear")
        topics = best.get("topics", [])
        reason_parts = []
        if pub_score >= 60:
            reason_parts.append(f"可发布性高({pub_score:.0f}/100)")
        if stars >= 1000:
            reason_parts.append(f"社区认可({stars} stars)")
        if content_type == "runnable_project":
            reason_parts.append("可运行项目，素材充分")
        if desc:
            reason_parts.append(f"一句话: {desc}")
        if not reason_parts:
            reason_parts.append(f"综合评分最高({score:.0f}/100)")

        print(f"  项目: {name}")
        print(f"  推荐理由: {'; '.join(reason_parts)}")
        if topics:
            print(f"  标签: {', '.join(topics[:5])}")
        if llm_available and pub_score >= 40:
            print(f"  操作: python run.py content {name}")
        elif not llm_available:
            print(f"  操作: python run.py content {name}  # 将进入 structured_fallback 模式")
        else:
            print(f"  注意: 可发布性不足({pub_score:.0f})，建议人工审核后再生成")

        # Show remaining top5 with brief scores
        if len(top5) > 1:
            print()
            print("  其他候选:")
            for r in top5[1:5]:
                rname = r.get("full_name", r.get("name", "unknown"))
                rscore = r.get("publishability_score", r.get("score", 0))
                print(f"    - {rname} (可发布性: {rscore:.0f})")
    else:
        print("  今日无高置信度选题。建议扩大搜索范围或检查 GitHub API 状态。")
    print()

    # ── Section 3: 下一步命令 ──
    print("── 下一步命令 ──")
    print()
    if llm_available and top5:
        best_name = top5[0].get("full_name", top5[0].get("name", ""))
        print(f"  生成内容:  python run.py content {best_name}")
    print("  审核队列:    python run.py review-queue")
    print("  LLM 诊断:    python run.py llm-doctor")
    print("  试运行:      python run.py dry-run")
    print("  全量验证:    python -m pytest tests/ -v")
    print()
    print("=" * 64)

    return daily_rc


def cmd_review_queue() -> int:
    """Phase 13: Display human review checklist from latest daily run.

    Reads the latest review_queue_{date}.md and prints it.
    If no report exists, suggests running daily first.
    """
    from datetime import datetime, timezone

    reports_dir = REPORTS_DIR
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Try today's report first, then fall back to latest
    queue_path = reports_dir / f"review_queue_{today}.md"
    if not queue_path.exists():
        # Find latest
        candidates = sorted(reports_dir.glob("review_queue_*.md"), reverse=True)
        if candidates:
            queue_path = candidates[0]
        else:
            print("=" * 64)
            print("  Review Queue — Not Available")
            print("=" * 64)
            print()
            print("  No review queue report found.")
            print()
            print("  Run the daily pipeline first:")
            print("    python run.py daily --no-llm")
            print("    python run.py daily-workflow")
            print()
            return 1

    print()
    content = queue_path.read_text(encoding="utf-8")
    print(content)
    print()

    if queue_path.name != f"review_queue_{today}.md":
        print(f"  Note: Showing latest available report ({queue_path.name})")
        print(f"  Run 'python run.py daily --no-llm' to generate today's report.")
        print()

    return 0


def cmd_llm_doctor() -> int:
    """Phase 15: Diagnose LLM provider connectivity.

    Tests each configured provider with a minimal request.
    Never prints full API keys.
    """
    import os
    import time
    import requests

    from .config import get_llm_providers, mask_key
    from .analyzer import _classify_llm_error

    print()
    print("=" * 64)
    print("  LLM Doctor")
    print("=" * 64)
    print()

    # ── Config section ──
    llm_key = os.getenv("LLM_API_KEY", "")
    llm_base = os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1")
    llm_model = os.getenv("LLM_MODEL", "deepseek-chat")
    fb_key = os.getenv("FALLBACK_LLM_API_KEY", "")
    fb_base = os.getenv("FALLBACK_LLM_API_BASE", "")
    fb_model = os.getenv("FALLBACK_LLM_MODEL", "")
    fb_provider = os.getenv("FALLBACK_LLM_PROVIDER", "openrouter")

    print("🔧 配置")
    print(f"  LLM_API_KEY:      {mask_key(llm_key)}")
    print(f"  LLM_API_BASE:     {llm_base}")
    print(f"  LLM_MODEL:        {llm_model}")
    print(f"  FALLBACK_LLM_API_KEY: {mask_key(fb_key)}")
    if fb_key:
        print(f"  FALLBACK_LLM_API_BASE: {fb_base}")
        print(f"  FALLBACK_LLM_MODEL:    {fb_model}")
    print()

    # ── Provider status ──
    providers = get_llm_providers()
    if not providers:
        print("📡 Provider 状态")
        print("  No providers configured.")
        print()
        print("📋 结论")
        print("  LLM_API_KEY 未配置。内容生成将进入 structured_fallback 模式。")
        print("  建议：Copy .env.example to .env and set LLM_API_KEY.")
        print()
        return 1

    print("📡 Provider 状态")
    all_failed = True
    short_test_prompt = "Say OK in one word."

    for i, p in enumerate(providers):
        label = "primary" if i == 0 else f"fallback {i}"
        print(f"  {i+1}. {p['name']} ({label})")
        url = p["base_url"].rstrip("/") + "/chat/completions"
        print(f"     URL: {url}")

        try:
            t0 = time.monotonic()
            resp = requests.post(
                url,
                json={
                    "model": p["model"],
                    "messages": [{"role": "user", "content": short_test_prompt}],
                    "max_tokens": 10,
                    "temperature": 0,
                },
                headers={
                    "Authorization": f"Bearer {p['api_key']}",
                    "Content-Type": "application/json",
                },
                timeout=(5, 15),
            )
            latency = (time.monotonic() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            print(f"     Status: ✅ 可用 ({latency:.0f}ms)")
            print(f"     Response: \"{content[:80]}\"")
            all_failed = False
        except Exception as e:
            error_type = _classify_llm_error(e)
            error_code = 0
            if isinstance(e, requests.exceptions.HTTPError):
                error_code = getattr(e.response, "status_code", 0)
            print(f"     Status: ❌ 不可用")
            print(f"     Error: {error_code} {type(e).__name__}")

            if error_type in ("http_401_permanent",):
                print(f"     Diagnosis: API Key 无效或未授权，请检查 LLM_API_KEY")
            elif error_type in ("http_402_permanent",):
                print(f"     Diagnosis: 账户余额不足或欠费，请充值后重试")
            elif error_type in ("http_403_permanent",):
                print(f"     Diagnosis: 权限不足，请检查 API Key 权限范围")
            elif error_type in ("http_429_temporary",):
                print(f"     Diagnosis: 请求频率过高，稍后自动恢复")
            elif error_type in ("timeout",):
                print(f"     Diagnosis: 连接超时，请检查网络或换用低延迟 provider")
            elif error_type in ("network",):
                print(f"     Diagnosis: 网络不可达，请检查 DNS 或防火墙设置")
            else:
                print(f"     Diagnosis: 未知错误类型 ({error_type})")
        print()

    # ── Test generation ──
    print("🧪 测试生成")
    print(f"  Test prompt: \"{short_test_prompt}\"")

    from .analyzer import _call_llm_with_failover
    result = _call_llm_with_failover(
        system_prompt="You are a helpful assistant.",
        user_prompt=short_test_prompt,
        temperature=0,
    )

    if result.success:
        print(f"  Result: ✅ 成功 (provider: {result.provider})")
    else:
        errors = "; ".join(
            f"{a.provider}: {a.error_type}({a.error_code})" for a in result.attempts
        )
        print(f"  Result: ❌ 失败")
        print(f"  Attempts: {errors}")
    print()

    # ── Conclusion ──
    print("📋 结论")
    if all_failed:
        print("  LLM 当前不可用。内容生成将进入 structured_fallback 模式。")
        if fb_key:
            print(f"  Primary 和 fallback 均已测试，均不可用。")
        else:
            print("  建议：配置 FALLBACK_LLM_API_KEY 以增加容错，或修复 primary 连接。")
    else:
        print("  LLM 可用。内容生成将使用 full_llm 模式。")

    n_ok = sum(1 for p in providers if not all_failed) if not all_failed else 0
    print(f"  Provider 可用: {n_ok}/{len(providers)}")
    print()

    return 0 if not all_failed else 1


def cmd_content(repo_full_name: str) -> int:
    """Phase 15: Generate content pack with LLM health awareness.

    Statuses: ok_full_llm / ok_structured_fallback / degraded / failed
    """
    from .content_pack import _check_llm_health

    # Pre-flight LLM health check
    llm_available, llm_mode, _ = _check_llm_health(timeout=10)
    if not llm_available:
        print()
        print("  ⚠️  LLM 不可用 — 内容将生成为 structured_fallback 研究简报")
        print("     这不是可发布文章，需要人工补写后才能发布。")
        print()

    logger.info("Generating V2 content pack for %s...", repo_full_name)
    logger.info("Files: %s", ", ".join(CONTENT_FILES_V2))
    pack_dir, status = generate_content_pack(repo_full_name)
    logger.info("Content pack generated at %s (status=%s)", pack_dir, status)

    # List generated files
    files = sorted(pack_dir.glob("*.md"))
    for f in files:
        print(f"  {f.name} ({f.stat().st_size} bytes)")
    print(f"\nTotal: {len(files)} files in {pack_dir}")

    # Status display with clear labels
    status_labels = {
        "ok_full_llm": "✅ OK (full_llm) — 内容由 LLM 生成，可直接发布",
        "ok_structured_fallback": "⚠️  OK (structured_fallback) — 研究简报模式，需人工补写后才能发布",
        "degraded": "⚠️  DEGRADED — 部分文件生成失败，需人工补全",
        "failed": "❌ FAILED — 内容生成失败",
    }
    label = status_labels.get(status, f"Unknown status: {status}")
    print(f"Status: {label}")

    # Read manifest
    manifest_path = pack_dir / "_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"  Generated: {manifest.get('files_generated', 0)}")
        print(f"  Degraded:  {manifest.get('files_degraded', 0)}")
        print(f"  Failed:    {manifest.get('files_failed', 0)}")
        if "content_mode" in manifest:
            print(f"  Content Mode: {manifest['content_mode']}")
        if "llm_status" in manifest:
            print(f"  LLM Status: {manifest['llm_status']}")

    # Show per-file status
    for f in files:
        content = f.read_text(encoding="utf-8")
        is_brief = "NOT_PUBLISHABLE_RESEARCH_BRIEF" in content
        degraded_mark = "source_status: degraded" in content
        todo_count = content.count("[TODO")

        if is_brief:
            print(f"  📋 {f.name}: 研究简报 (需人工补写)")
        elif degraded_mark:
            print(f"  ⚠️  {f.name}: DEGRADED (retries exhausted)")
        elif todo_count > 0:
            print(f"  ⚠️  {f.name}: {todo_count} TODO(s) remaining")
        else:
            print(f"  ✅ {f.name}: complete")

    if status == "failed":
        return 1
    elif status == "blocked":
        print("\n⛔ BLOCKED: 高风险项目，已拒绝生成内容。")
        return 4
    elif status == "degraded":
        return 2
    elif status == "ok_structured_fallback":
        return 3  # distinct exit code for fallback mode
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
    elif args.command == "daily-workflow":
        return cmd_daily_workflow()
    elif args.command == "review-queue":
        return cmd_review_queue()
    elif args.command == "llm-doctor":
        return cmd_llm_doctor()
    elif args.command == "content":
        if not args.repo:
            parser.error("content command requires a repo argument (owner/repo)")
        return cmd_content(args.repo)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
