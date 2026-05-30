"""Benchmark runner for 4-layer scoring calibration.

Loads golden_cases.json, runs all scoring layers against each case,
and reports accuracy per pool, per dimension, and per acceptance criterion.
"""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .business_score import score_business_value
from .enricher import EnrichedRepo
from .platform_score import score_platform_fit
from .risk_score import assess_risk
from .scorer import (
    ScoredRepo,
    apply_classification_and_filters,
    classify_content_type,
    score_repo,
)


@dataclass
class CaseResult:
    full_name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    selection_score: float = 0.0
    selection_subscores: dict = field(default_factory=dict)
    business_score: float = 0.0
    business_subscores: dict = field(default_factory=dict)
    pool: str = ""
    content_type: str = ""
    risk_overall: str = ""
    risk_profile: dict = field(default_factory=dict)
    platform_scores: dict = field(default_factory=dict)
    best_platform: str = ""


def load_golden_cases(path: Path | None = None) -> list[dict]:
    if path is None:
        path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden_cases.json"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["cases"]


def case_to_enriched_repo(case: dict) -> EnrichedRepo:
    return EnrichedRepo(
        full_name=case["full_name"],
        name=case["name"],
        description=case.get("description", ""),
        url=f"https://github.com/{case['full_name']}",
        language=case.get("language", "Python"),
        stars=case.get("stars", 0),
        forks=case.get("forks", 0),
        open_issues=0,
        updated_at="2026-05-29T00:00:00Z",
        created_at="2020-01-01T00:00:00Z",
        topics=case.get("topics", []),
        license=case.get("license", ""),
        readme=case.get("readme", ""),
        contributors_count=case.get("contributors_count", 0),
    )


def run_benchmark(golden_path: Path | None = None) -> dict:
    cases = load_golden_cases(golden_path)
    results: list[CaseResult] = []

    for case in cases:
        repo = case_to_enriched_repo(case)
        expected = case.get("expected", {})
        failures: list[str] = []

        # Layer 1 — selection score
        scored = score_repo(repo)
        selection_score = scored.score

        # Layer 1b — classification
        content_type = classify_content_type(repo)

        # Layer 1c — pool assignment (mutates scored.pool in place)
        apply_classification_and_filters([scored])
        pool = scored.pool

        # Layer 2 — business value
        biz = score_business_value(scored)

        # Layer 3 — platform fit
        plat = score_platform_fit(scored)

        # Layer 4 — risk
        risk = assess_risk(scored)

        # ── Assertions ──────────────────────────────────────────────────
        expected_pool = expected.get("pool")
        if expected_pool and pool != expected_pool:
            failures.append(f"pool: expected={expected_pool} got={pool}")

        expected_ct = expected.get("content_type")
        if expected_ct and content_type != expected_ct:
            failures.append(f"content_type: expected={expected_ct} got={content_type}")

        expected_risk = expected.get("risk_overall")
        if expected_risk and risk.overall != expected_risk:
            failures.append(f"risk_overall: expected={expected_risk} got={risk.overall}")

        sel_range = expected.get("repo_selection_score")
        if sel_range:
            lo, hi = sel_range["min"], sel_range["max"]
            if not (lo <= selection_score <= hi):
                failures.append(f"selection_score: expected [{lo},{hi}] got {selection_score}")

        biz_range = expected.get("business_value_score")
        if biz_range:
            lo, hi = biz_range["min"], biz_range["max"]
            if not (lo <= biz.total <= hi):
                failures.append(f"business_score: expected [{lo},{hi}] got {biz.total}")

        plat_ranges = expected.get("platform_fit_ranges", {})
        platform_scores = {
            "xiaohongshu": plat.xiaohongshu,
            "douyin": plat.douyin,
            "videohao": plat.videohao,
            "wechat": plat.wechat,
            "geo_trade": plat.geo_trade,
        }
        for pname, prange in plat_ranges.items():
            actual = platform_scores.get(pname)
            if actual is not None:
                lo, hi = prange["min"], prange["max"]
                if not (lo <= actual <= hi):
                    failures.append(f"platform_{pname}: expected [{lo},{hi}] got {actual}")

        results.append(CaseResult(
            full_name=case["full_name"],
            passed=len(failures) == 0,
            failures=failures,
            selection_score=selection_score,
            selection_subscores=scored.subscores,
            business_score=biz.total,
            business_subscores=biz.subscores,
            pool=pool,
            content_type=content_type,
            risk_overall=risk.overall,
            risk_profile={
                "license": risk.license_risk,
                "data_privacy": risk.data_privacy_risk,
                "account_automation": risk.account_automation_risk,
                "scraping_platform": risk.scraping_platform_risk,
                "deepfake_impersonation": risk.deepfake_impersonation_risk,
                "spam_phishing": risk.spam_phishing_malware_risk,
                "hype": risk.hype_risk,
                "client_misuse": risk.client_misuse_risk,
            },
            platform_scores=platform_scores,
            best_platform=plat.best_platform,
        ))

    # ── Aggregate metrics ──────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for r in results if r.passed)

    # Per-pool accuracy
    pool_stats: dict[str, dict] = {}
    for r, case in zip(results, cases):
        ep = case["expected"].get("pool", "unknown")
        if ep not in pool_stats:
            pool_stats[ep] = {"total": 0, "correct": 0, "cases": []}
        pool_stats[ep]["total"] += 1
        pool_stats[ep]["cases"].append(r.full_name)
        if r.pool == ep:
            pool_stats[ep]["correct"] += 1

    for ps in pool_stats.values():
        ps["accuracy"] = round(ps["correct"] / ps["total"] * 100, 1) if ps["total"] > 0 else 0.0

    # Per-score-dimension accuracy
    sel_passed = sum(1 for r in results if not any("selection_score" in f for f in r.failures))
    biz_passed = sum(1 for r in results if not any("business_score" in f for f in r.failures))
    plat_passed = sum(1 for r in results if not any("platform_" in f for f in r.failures))

    # ── 10 acceptance criteria ─────────────────────────────────────────
    criteria: dict[str, dict] = {}

    # C1: blocked_pool = 100%
    blocked_cases = [r for r in results if r.pool == "blocked" or any(
        c["expected"].get("pool") == "blocked" for c in cases if c["full_name"] == r.full_name
    )]
    expected_blocked = [c for c in cases if c["expected"].get("pool") == "blocked"]
    blocked_ok = all(
        any(r.full_name == c["full_name"] and r.pool == "blocked" for r in results)
        for c in expected_blocked
    )
    criteria["C1_blocked_100pct"] = {"passed": blocked_ok, "detail": f"{len(expected_blocked)} blocked cases"}

    # C2: evergreen >= 90%
    ev_stats = pool_stats.get("evergreen", {"accuracy": 0})
    criteria["C2_evergreen_90pct"] = {"passed": ev_stats["accuracy"] >= 90, "detail": f"{ev_stats['accuracy']}%"}

    # C3: resource >= 90%
    res_stats = pool_stats.get("resource", {"accuracy": 0})
    criteria["C3_resource_90pct"] = {"passed": res_stats["accuracy"] >= 90, "detail": f"{res_stats['accuracy']}%"}

    # C4: top5 >= 85%
    top5_stats = pool_stats.get("top5", {"accuracy": 0})
    criteria["C4_top5_85pct"] = {"passed": top5_stats["accuracy"] >= 85, "detail": f"{top5_stats['accuracy']}%"}

    # C5: browser-use specific
    bu = next((r for r in results if r.full_name == "browser-use/browser-use"), None)
    if bu:
        bu_ok = (
            bu.selection_score >= 80
            and bu.business_score >= 85
            and bu.platform_scores.get("geo_trade", 0) >= 80
            and bu.risk_overall == "medium"
        )
        criteria["C5_browser_use"] = {
            "passed": bu_ok,
            "detail": f"sel={bu.selection_score} biz={bu.business_score} geo={bu.platform_scores.get('geo_trade', 0)} risk={bu.risk_overall}",
        }
    else:
        criteria["C5_browser_use"] = {"passed": False, "detail": "not found"}

    # C6: ragflow specific
    rf = next((r for r in results if r.full_name == "infiniflow/ragflow"), None)
    if rf:
        rf_ok = (
            rf.selection_score >= 80
            and rf.business_score >= 85
            and rf.platform_scores.get("wechat", 0) >= 80
            and rf.platform_scores.get("videohao", 0) >= 80
        )
        criteria["C6_ragflow"] = {
            "passed": rf_ok,
            "detail": f"sel={rf.selection_score} biz={rf.business_score} wechat={rf.platform_scores.get('wechat', 0)} videohao={rf.platform_scores.get('videohao', 0)}",
        }
    else:
        criteria["C6_ragflow"] = {"passed": False, "detail": "not found"}

    # C7: Dify / n8n / LangChain → evergreen
    c7_names = {"langgenius/dify", "n8n-io/n8n", "langchain-ai/langchain"}
    c7_results = [r for r in results if r.full_name in c7_names]
    c7_ok = all(r.pool == "evergreen" for r in c7_results)
    criteria["C7_three_evergreen"] = {
        "passed": c7_ok,
        "detail": ", ".join(f"{r.full_name}={r.pool}" for r in c7_results),
    }

    # C8: Deep-Live-Cam → blocked
    dlc = next((r for r in results if r.full_name == "hacksider/Deep-Live-Cam"), None)
    if dlc:
        criteria["C8_deep_live_cam_blocked"] = {
            "passed": dlc.pool == "blocked",
            "detail": f"pool={dlc.pool} risk={dlc.risk_overall}",
        }
    else:
        criteria["C8_deep_live_cam_blocked"] = {"passed": False, "detail": "not found"}

    # C9: awesome-llm-apps → resource
    ala = next((r for r in results if r.full_name == "Shubhamsaboo/awesome-llm-apps"), None)
    if ala:
        criteria["C9_awesome_llm_apps_resource"] = {
            "passed": ala.pool == "resource",
            "detail": f"pool={ala.pool}",
        }
    else:
        criteria["C9_awesome_llm_apps_resource"] = {"passed": False, "detail": "not found"}

    # C10: JavaGuide → not top5
    jg = next((r for r in results if r.full_name == "Snailclimb/JavaGuide"), None)
    if jg:
        criteria["C10_java_guide_not_top5"] = {
            "passed": jg.pool != "top5",
            "detail": f"pool={jg.pool}",
        }
    else:
        criteria["C10_java_guide_not_top5"] = {"passed": False, "detail": "not found"}

    criteria_passed = sum(1 for c in criteria.values() if c["passed"])
    criteria_total = len(criteria)

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "overall_accuracy": round(passed / total * 100, 1) if total > 0 else 0,
        "pool_accuracy": pool_stats,
        "dimension_accuracy": {
            "selection_score": round(sel_passed / total * 100, 1) if total > 0 else 0,
            "business_score": round(biz_passed / total * 100, 1) if total > 0 else 0,
            "platform_fit": round(plat_passed / total * 100, 1) if total > 0 else 0,
        },
        "criteria": criteria,
        "criteria_summary": f"{criteria_passed}/{criteria_total}",
        "results": [r.__dict__ for r in results],
        "failed_list": [
            {"full_name": r.full_name, "failures": r.failures,
             "sel": r.selection_score, "biz": r.business_score,
             "pool": r.pool, "risk": r.risk_overall}
            for r in results if not r.passed
        ],
    }


def print_benchmark_report(bm: dict, file=None) -> None:
    """Pretty-print the benchmark report."""
    out = file or sys.stdout

    def p(line: str = "") -> None:
        print(line, file=out)

    p("=" * 72)
    p("  Scoring Benchmark Report — 4-Layer Calibration")
    p("=" * 72)
    p()
    p(f"  Total cases:      {bm['total_cases']}")
    p(f"  Passed:           {bm['passed_cases']}")
    p(f"  Failed:           {bm['failed_cases']}")
    p(f"  Overall accuracy: {bm['overall_accuracy']}%")
    p()
    p("── Pool classification accuracy ──")
    for pool_name in ("top5", "evergreen", "resource", "blocked"):
        ps = bm["pool_accuracy"].get(pool_name)
        if ps:
            p(f"  {pool_name:12s}: {ps['correct']}/{ps['total']} = {ps['accuracy']}%")
    p()
    p("── Dimension accuracy ──")
    for dim, acc in bm["dimension_accuracy"].items():
        p(f"  {dim}: {acc}%")
    p()
    p("── 10 Acceptance Criteria ──")
    for cname, cinfo in bm["criteria"].items():
        status = "PASS" if cinfo["passed"] else "FAIL"
        p(f"  [{status}] {cname}: {cinfo['detail']}")
    p()
    p(f"  Criteria passed: {bm['criteria_summary']}")
    p()

    if bm["failed_list"]:
        p("── Failed cases ──")
        for fc in bm["failed_list"]:
            p(f"  ✗ {fc['full_name']} (pool={fc['pool']} risk={fc['risk']} sel={fc['sel']} biz={fc['biz']})")
            for f in fc["failures"]:
                p(f"      • {f}")
        p()

    # Specific repo snapshots
    p("── Key repo snapshots ──")
    for target in ("browser-use/browser-use", "infiniflow/ragflow",
                   "hacksider/Deep-Live-Cam", "langgenius/dify",
                   "n8n-io/n8n", "langchain-ai/langchain",
                   "Shubhamsaboo/awesome-llm-apps", "Snailclimb/JavaGuide"):
        r = next((rr for rr in bm["results"] if rr["full_name"] == target), None)
        if r:
            p(f"  {target}:")
            p(f"    pool={r['pool']} ct={r['content_type']} risk={r['risk_overall']}")
            p(f"    selection={r['selection_score']} business={r['business_score']}")
            p(f"    platforms={r['platform_scores']}")
            p(f"    sel_subscores={r['selection_subscores']}")
            p(f"    biz_subscores={r['business_subscores']}")
            if r["failures"]:
                p(f"    failures={r['failures']}")
    p()
    p("=" * 72)


def cmd_benchmark() -> int:
    """CLI entry point: run all three benchmark types and print comprehensive report."""
    import sys as _sys

    # 1. Golden cases (with expected values)
    print("=" * 72)
    print("  BENCHMARK — Golden Cases (80 cases with expected values)")
    print("=" * 72)
    bm = run_benchmark()
    print_benchmark_report(bm)

    # 2. Adversarial cases
    print()
    print("=" * 72)
    print("  BENCHMARK — Adversarial Cases (20 edge cases)")
    print("=" * 72)
    adv_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "adversarial_cases.json"
    if adv_path.exists():
        adv = run_adversarial_benchmark(adv_path)
        print_adversarial_report(adv)
    else:
        print("  SKIPPED: adversarial_cases.json not found")

    # 3. Live sample cases
    print()
    print("=" * 72)
    print("  BENCHMARK — Live Sample Cases (20 real daily samples)")
    print("=" * 72)
    live_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "live_sample_cases.json"
    if live_path.exists():
        live = run_live_sample_benchmark(live_path)
        print_live_sample_report(live)
    else:
        print("  SKIPPED: live_sample_cases.json not found")

    # Summary
    print()
    print("=" * 72)
    print("  BENCHMARK SUMMARY")
    print("=" * 72)
    golden_acc = bm["overall_accuracy"]
    adv_pass = adv.get("overall_pass_rate", 0) if adv_path.exists() else "N/A"
    live_high = live.get("high_confidence", 0) if live_path.exists() else "N/A"
    live_review = live.get("needs_review", 0) if live_path.exists() else "N/A"

    print(f"  golden_cases_accuracy:     {golden_acc}%")
    print(f"  adversarial_cases_pass:    {adv_pass}%")
    print(f"  live_sample_high_conf:     {live_high}/20")
    print(f"  live_sample_needs_review:  {live_review}/20")
    print("=" * 72)

    all_pass = all(c["passed"] for c in bm["criteria"].values())
    return 0 if all_pass else 1


# ═════════════════════════════════════════════════════════════════════════════
# Adversarial benchmark
# ═════════════════════════════════════════════════════════════════════════════

def run_adversarial_benchmark(path: Path) -> dict:
    """Run scoring against adversarial edge cases. Reports pass rate per test type."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data["cases"]

    results = []
    for case in cases:
        repo = case_to_enriched_repo(case)
        expected = case.get("expected", {})
        failures = []

        scored = score_repo(repo)
        content_type = classify_content_type(repo)
        apply_classification_and_filters([scored])
        pool = scored.pool
        biz = score_business_value(scored)
        risk = assess_risk(scored)
        plat = score_platform_fit(scored)

        test_desc = expected.get("test", "")

        # Check pool expectation
        expected_pool = expected.get("pool")
        if expected_pool and pool != expected_pool:
            failures.append(f"pool: expected={expected_pool} got={pool}")

        # Check content_type
        expected_ct = expected.get("content_type")
        if expected_ct and content_type != expected_ct:
            failures.append(f"content_type: expected={expected_ct} got={content_type}")

        # Check risk
        expected_risk = expected.get("risk_overall")
        if expected_risk and risk.overall != expected_risk:
            failures.append(f"risk: expected={expected_risk} got={risk.overall}")

        # Check selection_score range
        sel_range = expected.get("repo_selection_score")
        if sel_range:
            lo, hi = sel_range["min"], sel_range["max"]
            if not (lo <= scored.score <= hi):
                failures.append(f"selection_score: expected [{lo},{hi}] got {scored.score}")

        # Check business_score range
        biz_range = expected.get("business_value_score")
        if biz_range:
            lo, hi = biz_range["min"], biz_range["max"]
            if not (lo <= biz.total <= hi):
                failures.append(f"business_score: expected [{lo},{hi}] got {biz.total}")

        results.append({
            "full_name": case["full_name"],
            "passed": len(failures) == 0,
            "failures": failures,
            "pool": pool,
            "content_type": content_type,
            "risk": risk.overall,
            "selection_score": scored.score,
            "business_score": biz.total,
            "test": test_desc,
        })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    # Group by test type
    by_category = {}
    for r in results:
        test = r["test"]
        # Extract category from test description
        cat = test.split(" — ")[0] if " — " in test else "other"
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0}
        by_category[cat]["total"] += 1
        if r["passed"]:
            by_category[cat]["passed"] += 1

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "overall_pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "by_category": by_category,
        "results": results,
        "failed_list": [r for r in results if not r["passed"]],
    }


def print_adversarial_report(adv: dict) -> None:
    """Print adversarial benchmark results."""
    print(f"  Total: {adv['total']}, Passed: {adv['passed']}, Failed: {adv['failed']}")
    print(f"  Overall pass rate: {adv['overall_pass_rate']}%")
    print()
    print("  ── By category ──")
    for cat, stats in sorted(adv["by_category"].items()):
        acc = round(stats["passed"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
        print(f"    {cat}: {stats['passed']}/{stats['total']} = {acc}%")
    if adv["failed_list"]:
        print()
        print("  ── Failed adversarial cases ──")
        for fr in adv["failed_list"]:
            print(f"    ✗ {fr['full_name']} (pool={fr['pool']}, risk={fr['risk']})")
            print(f"      Test: {fr['test']}")
            for f in fr["failures"]:
                print(f"      • {f}")


# ═════════════════════════════════════════════════════════════════════════════
# Live sample benchmark (no expected values — confidence-based)
# ═════════════════════════════════════════════════════════════════════════════

def run_live_sample_benchmark(path: Path) -> dict:
    """Run scoring on live samples WITHOUT expected values.

    Instead of claiming accuracy, reports confidence tiers:
      - high_confidence: system classification looks correct
      - needs_review: ambiguous or suspicious result
      - unclear: insufficient information to judge
      - blocked: correctly or incorrectly blocked
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data["cases"]

    results = []
    high_confidence = []
    needs_review = []
    unclear = []
    blocked = []

    for case in cases:
        repo = case_to_enriched_repo(case)
        scored = score_repo(repo)
        content_type = classify_content_type(repo)
        apply_classification_and_filters([scored])
        pool = scored.pool
        biz = score_business_value(scored)
        risk = assess_risk(scored)
        plat = score_platform_fit(scored)

        # Check AI eligibility
        from .scorer import check_ai_eligibility
        is_ai, ai_evidence = check_ai_eligibility(repo)

        r = {
            "full_name": case["full_name"],
            "pool": pool,
            "content_type": content_type,
            "risk": risk.overall,
            "selection_score": scored.score,
            "business_score": biz.total,
            "best_platform": plat.best_platform,
            "ai_eligible": is_ai,
            "ai_evidence": ai_evidence,
            "note": case.get("expected", {}).get("note", ""),
        }

        # Confidence tier assignment (rule-based, no human labels)
        if pool == "blocked":
            r["confidence"] = "blocked"
            blocked.append(r)
        elif content_type == "unclear":
            r["confidence"] = "unclear"
            unclear.append(r)
        elif pool == "top5" and scored.score >= 75 and biz.total >= 75 and is_ai:
            r["confidence"] = "high_confidence"
            high_confidence.append(r)
        elif pool in ("evergreen", "resource") and scored.score < 50:
            r["confidence"] = "high_confidence"
            high_confidence.append(r)
        else:
            r["confidence"] = "needs_review"
            needs_review.append(r)

        results.append(r)

    return {
        "total": len(results),
        "high_confidence": len(high_confidence),
        "needs_review": len(needs_review),
        "unclear": len(unclear),
        "blocked": len(blocked),
        "results": results,
        "high_confidence_list": high_confidence,
        "needs_review_list": needs_review,
        "unclear_list": unclear,
        "blocked_list": blocked,
    }


def print_live_sample_report(live: dict) -> None:
    """Print live sample benchmark results with confidence tiers."""
    print(f"  Total: {live['total']}")
    print(f"  High confidence: {live['high_confidence']}")
    print(f"  Needs review:    {live['needs_review']}")
    print(f"  Unclear:         {live['unclear']}")
    print(f"  Blocked:         {live['blocked']}")
    print(f"  Human review required rate: {round((live['needs_review'] + live['unclear']) / live['total'] * 100, 1)}%")
    print()
    if live["needs_review_list"]:
        print("  ── Needs review ──")
        for r in live["needs_review_list"]:
            print(f"    ? {r['full_name']} pool={r['pool']} risk={r['risk']} sel={r['selection_score']} biz={r['business_score']}")
            print(f"      note: {r['note']}")
    if live["blocked_list"]:
        print()
        print("  ── Blocked repos (verify no false positives) ──")
        for r in live["blocked_list"]:
            print(f"    ✗ {r['full_name']} risk={r['risk']} sel={r['selection_score']}")
            print(f"      note: {r['note']}")
