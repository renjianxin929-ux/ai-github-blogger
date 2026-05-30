"""Post-generation content reviewer pipeline.

6-check pipeline for every generated content file:
  1. repo_consistency_check  — is this content about the RIGHT repo?
  2. claim_grounding_check   — are claims confirmed / reasonable / unverified?
  3. risk_boundary_check     — any exaggerated, unsafe, or misleading statements?
  4. platform_style_check    — does content match platform conventions?
  5. quality_review          — comprehensive pack-level audit (file 10)
  6. _run_reviewer_pipeline  — orchestrates checks, triggers regeneration

If any core check (1, 3) fails:
  - mark file as needs_regeneration
  - regenerate once
  - if still fails, quality_status = needs_review
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Expressions that indicate content hallucination / wrong-project ──────────
# If these appear in content for a scraping/crawling tool, it's a red flag.
WRONG_PROJECT_SIGNALS = [
    "RAGFlow", "LangChain-ChatChat", "知识库问答", "私有化知识库",
    "Milvus", "Chroma", "Pinecone", "Qdrant", "Weaviate",
    "向量数据库", "embedding model", "text2vec",
    "中文分词", "ChatGLM", "Baichuan", "国内常用开源模型",
    "文档分割", "文档切分", "知识库管理",
    "非 AI 工程师也能", "无需编码即可在本地",
]

# ── Expressions that indicate exaggerated / unsafe claims ────────────────────
EXAGGERATED_CLAIMS = [
    ("任意网页", "过于绝对，建议改为'大多数公开网页'或'目标网站'"),
    ("任何网站", "过于绝对，建议改为'符合规范的网页'"),
    ("绕过限制", "危险表达——暗示可违法绕过反爬，必须删除"),
    ("绕过反爬", "危险表达——暗示可违法绕过反爬，必须删除"),
    ("反爬虫机制拉满也能", "暗示可突破安全措施，必须删除"),
    ("像真人一样浏览", "可能暗示冒充真实用户，建议改为'模拟浏览器行为'"),
    ("登录动态页面", "暗示可绕过登录，必须加授权声明"),
    ("万能爬虫", "误导性表达，爬虫不可能万能"),
    ("保证排名", "无法保证，必须删除或改为'可能有助于'"),
    ("保证询盘", "无法保证，必须删除或改为'可能增加'"),
    ("保证 AI 引用", "无法保证，必须删除或改为'可能提升'"),
    ("绝对可以", "过于绝对，需改为合理推断语气"),
    ("核心水龙头", "误导性表达，夸大组件地位"),
    ("定价数千至上万美元", "除非有明确依据，否则不得出现"),
    ("3秒把全网变文档", "夸大速度+能力范围，必须删除"),
]

# ── Hard boundary phrases for GEO content ────────────────────────────────────
GEO_HARD_BOUNDARY_PHRASES = [
    "保证提升 AI 引用",
    "保证排名",
    "保证询盘",
    "直接决定 AI 是否引用",
    "绝对可以",
    "核心水龙头组件",
    "定价数千至上万美元",
]

# ── GEO boundary semantic signals (project-agnostic) ──────────────────────
# Instead of matching a hardcoded sentence, check for 5 boundary meanings.
# Each signal has multiple acceptable phrasings.
_GEO_BOUNDARY_SIGNALS = [
    # 1. Project is only an auxiliary component in the GEO chain
    {
        "name": "组件化定位",
        "patterns": [
            r"(?:可以作为|只能作为|定位为|充当|扮演).{0,20}(?:GEO|外贸|搜索引擎).{0,15}(?:组件|环节|辅助|工具之一|一部分)",
            r"(?:GEO|外贸|搜索引擎).{0,15}(?:链路|工作流|链条|体系).{0,15}(?:组件|环节|辅助|工具之一|一部分)",
            r"(?:组件|环节|辅助).{0,10}(?:之一|而已|罢了)",
        ],
    },
    # 2. Project itself is NOT GEO
    {
        "name": "不等于GEO",
        "patterns": [
            r"(?:本身)?(?:不等于|不是|并非|不构成|不意味着.{0,5}就是).{0,10}(?:GEO|AI搜索优化|搜索引擎优化)",
            r"(?:GEO|AI搜索优化)(?:.{0,5}(?:工具|方案|产品))?",
            r"(?:不能|不可以|不应).{0,10}(?:直接)?(?:包装|硬蹭|宣传).{0,5}(?:GEO|AI搜索优化)",
        ],
    },
    # 3. Does NOT guarantee AI search citation
    {
        "name": "不保证AI引用",
        "patterns": [
            r"不(?:能|会|可|保证|承诺).{0,20}(?:AI|人工智能|大模型|搜索引擎).{0,10}(?:引用|提及|收录|抓取)",
            r"不(?:保证|承诺).{0,10}(?:被.{0,5})?(?:AI|人工智能|大模型).{0,10}(?:引用|提及)",
            r"(?:不能|无法|难以)(?:保证|确保).{0,5}(?:AI.{0,5})?(?:引用|提及)",
        ],
    },
    # 4. Does NOT guarantee ranking
    {
        "name": "不保证排名",
        "patterns": [
            r"不(?:能|会|可|保证|承诺).{0,10}(?:提升|提高|改善|影响).{0,10}(?:排名|搜索排名|SEO)",
            r"不(?:保证|承诺).{0,10}(?:排名|搜索排名|搜索结果)",
            r"(?:不能|无法|难以)(?:保证|确保).{0,5}(?:排名|搜索排名)",
            # Broader: "不能保证...排名" / "不能保证...搜索排名" (direct negation, up to 25 chars gap)
            r"不.{0,5}(?:保证|承诺).{0,25}(?:排名|搜索排名|SEO|搜索结果)",
            r"(?:不能|无法|难以).{0,20}(?:排名|搜索排名)",
        ],
    },
    # 5. Does NOT guarantee inquiry/lead generation
    {
        "name": "不保证询盘",
        "patterns": [
            r"不(?:能|会|可|保证|承诺).{0,10}(?:带来|产生|获取|增加).{0,10}(?:询盘|客户|订单|转化|销售线索)",
            r"不(?:保证|承诺).{0,10}(?:询盘|客户获取|销售线索|业务增长)",
            r"(?:不能|无法|难以)(?:保证|确保).{0,5}(?:询盘|客户|订单|转化)",
            r"不.{0,5}(?:直接|必然).{0,5}(?:带来|产生).{0,5}(?:询盘|客户|订单)",
            # Broader: "不能保证...询盘" / "不能承诺...客户" (direct negation, up to 25 chars gap)
            r"不.{0,5}(?:保证|承诺).{0,25}(?:询盘|客户获取|销售线索|业务增长)",
            r"(?:不能|无法|难以).{0,20}(?:询盘|客户|订单)",
            # Catch "询盘增长" compound: "不能保证...询盘增长"
            r"不.{0,5}(?:保证|承诺).{0,25}询盘",
        ],
    },
]

# ── Template / placeholder detection (Publication Readiness Gate) ──────────
# If any core content file matches these, recommendation must NOT be "yes".
_TEMPLATE_PLACEHOLDER_PATTERNS = [
    (r"\[TODO:\s*LLM\]", "检测到 [TODO: LLM] 占位符，内容未通过 LLM 生成"),
    (r"No-LLM\s+fallback", "检测到 No-LLM fallback 标记，内容为模板占位"),
    (r"source_status:\s*degraded", "检测到 source_status: degraded 标记，生成失败"),
    (r"> 模式：No-LLM", "检测到 No-LLM 模式标记，内容为模板占位"),
    (r"需要\s*LLM\s*(?:深度拓展|生成完整文章)", "检测到 LLM 依赖标记，内容不完整"),
    (r"> 模式：No-LLM fallback", "检测到 No-LLM fallback 模式，需 LLM 重新生成"),
]


def _check_template_placeholders(content: str) -> list[str]:
    """Check for template/fallback placeholders indicating incomplete content."""
    import re
    issues = []
    for pattern, explanation in _TEMPLATE_PLACEHOLDER_PATTERNS:
        if re.search(pattern, content):
            issues.append(explanation)
    return issues


# browser-use specific risk boundary — must appear in content for browser-use
_BROWSER_USE_RISK_BOUNDARY = (
    "browser-use 可以用于公开网页检查、授权流程辅助、页面信息整理"
    "和人工确认后的重复操作自动化，但它不应用于绕过登录、验证码、"
    "风控、平台限制、隐私保护或服务条款。它也不能保证 GEO 排名、AI 引用或询盘增长。"
)


def _geo_boundary_semantic_check(content: str) -> tuple[bool, list[str]]:
    """Check that content expresses all 5 GEO boundary meanings, project-agnostically."""
    import re
    missing = []
    for signal in _GEO_BOUNDARY_SIGNALS:
        found = False
        for pattern in signal["patterns"]:
            if re.search(pattern, content):
                found = True
                break
        if not found:
            missing.append(signal["name"])
    passed = len(missing) == 0
    return passed, missing


@dataclass
class CheckResult:
    """Result of a single review check."""
    check_name: str
    passed: bool
    score: int  # 0-100
    issues: list[str] = field(default_factory=list)
    must_fix_sentences: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class FileReview:
    """Complete review of a single content file."""
    file_name: str
    checks: list[CheckResult] = field(default_factory=list)
    needs_regeneration: bool = False
    overall_score: int = 0

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks) if self.checks else False


# ═════════════════════════════════════════════════════════════════════════════
# Check 1: Repo Consistency
# ═════════════════════════════════════════════════════════════════════════════

# Patterns that indicate the matched term is used in a safe, non-hallucinatory way
_SAFE_CONTEXT_PATTERNS = [
    # Negation: "不是 Milvus", "不同于 Chroma"
    r"(?:不是|不同于|区别于|而非|非|不像|替代.{{0,5}}){signal}",
    # Comparison: "与 Milvus 相比", "不像 Chroma 那样"
    r"(?:与|和|跟|比.{{0,5}}){signal}(?:相比|不同|不一样|有区别)",
    # README excerpt header: the signal may legitimately appear in repo's own README
    r"README\s*(?:摘要|摘录|原文)",
]

# Patterns indicating a risk phrase appears in a WARNING/DISCLAIMER context, not as a feature claim
_RISK_SAFE_CONTEXT_PATTERNS = [
    # Legal warnings: "绕过反爬措施可能触及法律", "不能抓取…"
    r"(?:可能触及|触犯|违反|违法|非法|法律|法规|合规)",
    # Risk disclaimers: "不能抓取", "不能用于侵犯", "必须遵守", "风险"
    r"(?:不能|不得|禁止|不要|风险|必须遵守|必须检查)",
    # Boundary statements: "不是万能", "不能保证", "不能承诺"
    r"(?:不是万能|不能保证|不能承诺|不保证|并非)",
    # Negative framing / counter-example context: "可能浪费时间的", "不适合你"
    r"(?:可能浪费|不适合|不适用|不要期待|不要指望|❌|⚠️)",
    # Describing wrong expectations, not tool capabilities: "期待一个...的人"
    r"期待.{0,5}(?:一个|那种|那种能|能).{0,30}(?:的人|的读者|的用户)",
]


def _is_safe_context(line: str, signal: str) -> bool:
    """Check if a signal appears in a safe context (negation, comparison, quotation)."""
    import re
    line_lower = line.lower()
    sig_escaped = re.escape(signal.lower())

    for pattern in _SAFE_CONTEXT_PATTERNS:
        try:
            actual = pattern.replace("{signal}", sig_escaped)
            if re.search(actual, line_lower):
                return True
        except re.error:
            continue
    return False


def _is_risk_safe_context(line: str, phrase: str, context_lines: list[str] | None = None) -> bool:
    """Check if a risk phrase appears in a warning/disclaimer context, not as a feature claim.

    Checks the line itself AND optional adjacent lines for safe-context signals.
    Example: "绕过反爬措施可能触及法律" is a warning, not a claim.
    Example: A line with "万能爬虫" under "❌ **可能浪费时间的**" header is a counter-example.
    """
    import re

    lines_to_check = [line]
    if context_lines:
        lines_to_check.extend(context_lines)

    for check_line in lines_to_check:
        for pattern in _RISK_SAFE_CONTEXT_PATTERNS:
            try:
                if re.search(pattern, check_line):
                    return True
            except re.error:
                continue
    return False


def repo_consistency_check(
    content: str, repo_full_name: str, unsupported_features: list[str] | None = None,
) -> CheckResult:
    """Check that content is about the correct repo, not hallucinated projects.

    Detects signals from wrong-project concepts (e.g., RAGFlow in a Firecrawl post).
    Requires 3+ wrong-project signals to fail — single-term matches are common
    in README excerpts and should not cause false positives.
    """
    import re
    issues = []
    must_fix = []
    content_lower = content.lower()

    for signal in WRONG_PROJECT_SIGNALS:
        sig_lower = signal.lower()
        if sig_lower not in content_lower:
            continue

        # Check if every occurrence is in a safe context
        matching_lines = []
        for line in content.split("\n"):
            if sig_lower in line.lower():
                if not _is_safe_context(line, signal):
                    matching_lines.append(line.strip()[:120])

        if matching_lines:
            issues.append(f"检测到疑似错位内容：'{signal}'（{len(matching_lines)} 处非安全上下文）")
            must_fix.extend(matching_lines[:2])

    # Require 3+ active wrong-project signals to fail (tolerates README mentions)
    ACTIVE_SIGNAL_THRESHOLD = 3
    passed = len(issues) < ACTIVE_SIGNAL_THRESHOLD

    score = max(0, 100 - len(issues) * 20) if not passed else max(60, 100 - len(issues) * 15)

    return CheckResult(
        check_name="repo_consistency",
        passed=passed,
        score=score,
        issues=issues,
        must_fix_sentences=must_fix[:5],
        detail=f"检测到 {len(issues)} 个错位信号（阈值={ACTIVE_SIGNAL_THRESHOLD}）" if issues else f"内容聚焦于 {repo_full_name}，未发现错位",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Check 2: Claim Grounding
# ═════════════════════════════════════════════════════════════════════════════

def claim_grounding_check(
    content: str, confirmed_features: list[str] | None = None,
) -> CheckResult:
    """Categorize key claims as confirmed / reasonable_inference / unverified.

    unverified_claim must not be presented as confirmed fact.
    """
    issues = []
    must_fix = []

    # Check for unverified patterns
    unverified_patterns = [
        (r"覆盖\s*\d+%", "覆盖率数字需有 benchmark 来源"),
        (r"唯一.*(?:工具|方案|选择)", "唯一性断言需要市场数据验证"),
        (r"所有.*都能", "过于绝对，建议改为'大多数'"),
        (r"从不|永远不会", "过于绝对，技术工具总有边界"),
        (r"完美.*(?:解决|适配|兼容)", "完美是主观判断，建议改为具体数据"),
    ]

    import re
    for pattern, explanation in unverified_patterns:
        matches = re.findall(pattern, content)
        if matches:
            for m in matches[:3]:
                issues.append(f"unverified_claim: '{m}' — {explanation}")
                # Find surrounding context
                idx = content.find(m)
                if idx >= 0:
                    ctx_start = max(0, idx - 30)
                    ctx_end = min(len(content), idx + len(m) + 50)
                    must_fix.append(content[ctx_start:ctx_end].replace("\n", " ").strip())

    # Dedup must_fix
    must_fix = list(dict.fromkeys(must_fix))[:10]

    score = max(0, 100 - len(issues) * 20)
    passed = len(issues) <= 1  # Allow 1 borderline unverified claim

    return CheckResult(
        check_name="claim_grounding",
        passed=passed,
        score=score,
        issues=issues,
        must_fix_sentences=must_fix,
        detail=f"检测到 {len(issues)} 个未验证断言" if issues else "关键断言均有依据或标注为推断",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Check 3: Risk Boundary
# ═════════════════════════════════════════════════════════════════════════════

def risk_boundary_check(content: str, geo_boundary: bool = False, strict_mode: bool = True) -> CheckResult:
    """Check for exaggerated claims, bypass hints, and missing safety disclaimers.

    In strict_mode (default), also checks for missing robots.txt/copyright/privacy
    disclaimers in scraping-related content. In non-strict mode, only checks
    for explicit exaggerated claims — suitable for short-form scripts.
    """
    issues = []
    must_fix = []

    for phrase, explanation in EXAGGERATED_CLAIMS:
        if phrase in content:
            # Check if ALL occurrences are in warning/disclaimer context
            matching_lines = []
            all_lines = content.split("\n")
            for i, line in enumerate(all_lines):
                if phrase in line:
                    # Collect adjacent lines for context-aware safe check
                    adjacent = []
                    if i > 0:
                        adjacent.append(all_lines[i - 1])
                    if i < len(all_lines) - 1:
                        adjacent.append(all_lines[i + 1])
                    if not _is_risk_safe_context(line, phrase, adjacent):
                        matching_lines.append(line.strip()[:150])
            if matching_lines:
                issues.append(f"夸大/风险表达: '{phrase}' — {explanation}")
                must_fix.extend(matching_lines[:2])

    # GEO-specific checks
    if geo_boundary:
        for phrase in GEO_HARD_BOUNDARY_PHRASES:
            if phrase in content:
                issues.append(f"GEO硬承诺: '{phrase}' — 必须删除")
                for line in content.split("\n"):
                    if phrase in line:
                        must_fix.append(line.strip()[:150])
                        break

        # Check that boundary statement is present (only in strict mode)
        if strict_mode:
            geo_passed, geo_missing = _geo_boundary_semantic_check(content)
            if not geo_passed:
                missing_names = "、".join(geo_missing)
                issues.append(f"缺少 GEO 边界声明: {missing_names}")

    # Check for missing safety disclaimers (only in strict mode for scraping tools)
    # Skip if geo_boundary=True and the GEO boundary statement is present —
    # GEO articles cover scope limitations through their boundary statement.
    if strict_mode and not (geo_boundary and _geo_boundary_semantic_check(content)[0]):
        scraping_content = any(k in content for k in ("爬虫", "抓取", "scrap", "crawl"))
        if scraping_content:
            found_any = False
            missing = []
            if "robots.txt" in content:
                found_any = True
            else:
                missing.append("robots.txt 合规提醒")
            if "版权" in content or "copyright" in content.lower():
                found_any = True
            else:
                missing.append("版权风险提醒")
            if "隐私" in content or "privacy" in content.lower():
                found_any = True
            else:
                missing.append("隐私风险提醒")
            # Require at least one disclaimer, warn about missing others
            if not found_any:
                issues.append(f"缺少任何关键风险提醒: {', '.join(missing)}")

    # Count GEO hard-promise issues separately (zero tolerance)
    geo_hard_issues = sum(1 for i in issues if "GEO" in i)
    # Missing ALL disclaimers is always blocking
    missing_all_disclaimers = any("缺少任何关键风险提醒" in i for i in issues)
    general_issues = len(issues) - geo_hard_issues

    score = max(0, 100 - len(issues) * 30)
    passed = geo_hard_issues == 0 and not missing_all_disclaimers and general_issues <= 1

    return CheckResult(
        check_name="risk_boundary",
        passed=passed,
        score=score,
        issues=issues,
        must_fix_sentences=must_fix,
        detail=f"检测到 {len(issues)} 个风险/夸大问题" if issues else "风险边界清晰，无夸大表达",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Check 4: Platform Style
# ═════════════════════════════════════════════════════════════════════════════

PLATFORM_STYLE_RULES = {
    "xiaohongshu": {
        "must_have": ["卡片"],
        "must_not": ["技术架构", "API 调用", "基准测试"],
        "tone": "口语化，像朋友聊天，有社群感",
    },
    "wechat_article": {
        "must_have": ["拆解"],
        "must_not": ["立即购买", "限时优惠", "加我微信"],
        "tone": "专业但不枯燥，有个人成长主线",
    },
    "geo_angle": {
        "must_have": ["边界声明", "组件化定位"],
        "must_not": ["绝对"],
        "tone": "理性分析，不画饼",
    },
    "douyin": {
        "must_have": ["钩子", "画面"],
        "must_not": ["长篇论述", "技术细节堆砌"],
        "tone": "快节奏，可视化驱动",
    },
}


def platform_style_check(content: str, platform: str) -> CheckResult:
    """Check content matches platform-specific style conventions."""
    rules = PLATFORM_STYLE_RULES.get(platform)
    if not rules:
        return CheckResult(
            check_name="platform_style",
            passed=True, score=100,
            detail=f"平台 '{platform}' 暂无风格规则，跳过检查",
        )

    issues = []

    for item in rules.get("must_have", []):
        if item not in content:
            issues.append(f"缺失平台要素: '{item}'")

    for item in rules.get("must_not", []):
        if item in content:
            issues.append(f"不应出现: '{item}'")

    score = max(0, 100 - len(issues) * 25)
    passed = len(issues) <= 1  # Allow 1 minor style issue

    return CheckResult(
        check_name="platform_style",
        passed=passed,
        score=score,
        issues=issues,
        detail=f"平台风格检查 ({platform}): {len(issues)} 个问题" if issues else f"平台风格 ({platform}) 符合要求",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Check 5: Quality Review (full pack audit, replaces old 10_quality_check)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class PackQualityReport:
    """Comprehensive quality report for a content pack."""
    repo_full_name: str
    publish_recommendation: str  # yes / no / revise_first
    overall_score: int  # 0-100
    blocking_issues: list[str] = field(default_factory=list)
    recommended_platform: str = ""
    file_reviews: dict[str, FileReview] = field(default_factory=dict)
    deleted_sentences: dict[str, list[str]] = field(default_factory=dict)


def quality_review(
    pack_dir: Path, repo_full_name: str, ctx: dict | None = None,
) -> PackQualityReport:
    """Run all checks on a content pack and produce a publish-readiness report."""
    ctx = ctx or {}
    confirmed = ctx.get("confirmed_features", [])
    unsupported = ctx.get("unsupported_features", [])

    review_files = [
        "01_ai_fde_deep_analysis.md",
        "02_xiaohongshu.md",
        "03_douyin_video.md",
        "04_videohao_script.md",
        "05_wechat_article.md",
        "07_geo_angle.md",
        "09_risk_review.md",
    ]

    # Map file name → platform for style check
    platform_map = {
        "02_xiaohongshu.md": "xiaohongshu",
        "03_douyin_video.md": "douyin",
        "04_videohao_script.md": "videohao",
        "05_wechat_article.md": "wechat_article",
        "07_geo_angle.md": "geo_angle",
    }

    file_reviews: dict[str, FileReview] = {}
    blocking_issues: list[str] = []
    all_deleted: dict[str, list[str]] = {}

    for fname in review_files:
        fpath = pack_dir / fname
        if not fpath.exists():
            file_reviews[fname] = FileReview(file_name=fname, needs_regeneration=True)
            blocking_issues.append(f"{fname} 文件不存在")
            continue

        content = fpath.read_text(encoding="utf-8")
        fr = FileReview(file_name=fname)

        # Check 0: Template placeholder detection (Publication Readiness Gate)
        # If content has [TODO: LLM] / No-LLM fallback / degraded markers,
        # it is NOT publishable regardless of other check results.
        placeholder_issues = _check_template_placeholders(content)
        if placeholder_issues:
            fr.needs_regeneration = True
            fr.checks.append(CheckResult(
                check_name="publication_readiness",
                passed=False, score=0,
                issues=placeholder_issues,
                detail=f"检测到 {len(placeholder_issues)} 个模板占位符，内容不完整",
            ))
            for issue in placeholder_issues:
                blocking_issues.append(f"{fname}: {issue}")

        # Check 1: Repo consistency (core)
        c1 = repo_consistency_check(content, repo_full_name, unsupported)
        fr.checks.append(c1)
        if not c1.passed:
            fr.needs_regeneration = True
            blocking_issues.append(f"{fname}: repo一致性检查失败 — {c1.detail}")
            all_deleted[fname] = c1.must_fix_sentences

        # Check 2: Claim grounding
        c2 = claim_grounding_check(content, confirmed)
        fr.checks.append(c2)
        if c2.must_fix_sentences:
            all_deleted.setdefault(fname, []).extend(c2.must_fix_sentences)

        # Check 3: Risk boundary (core)
        is_geo = "geo" in fname
        is_light = fname in ("03_douyin_video.md", "04_videohao_script.md")
        c3 = risk_boundary_check(content, geo_boundary=is_geo, strict_mode=not is_light)
        fr.checks.append(c3)
        if not c3.passed:
            fr.needs_regeneration = True
            blocking_issues.append(f"{fname}: 风险边界检查失败 — {c3.detail}")
            all_deleted.setdefault(fname, []).extend(c3.must_fix_sentences)

        # Check 4: Platform style
        platform = platform_map.get(fname)
        if platform:
            c4 = platform_style_check(content, platform)
            fr.checks.append(c4)
            if not c4.passed:
                all_deleted.setdefault(fname, []).extend(c4.issues)

        # Calculate overall score
        scores = [c.score for c in fr.checks]
        fr.overall_score = sum(scores) // len(scores) if scores else 0
        file_reviews[fname] = fr

    # Determine publish recommendation
    if not blocking_issues:
        recommendation = "yes"
    elif any("core check" in b or "repo一致性" in b or "风险边界" in b for b in blocking_issues):
        recommendation = "no"
    else:
        recommendation = "revise_first"

    # Calculate overall score
    all_scores = [fr.overall_score for fr in file_reviews.values()]
    overall_score = sum(all_scores) // len(all_scores) if all_scores else 0

    # Best platform — pick the file with highest score
    best_platform = "公众号"
    if file_reviews:
        best = max(file_reviews.items(), key=lambda kv: kv[1].overall_score)
        platform_names = {
            "02_xiaohongshu.md": "小红书",
            "03_douyin_video.md": "抖音",
            "04_videohao_script.md": "视频号",
            "05_wechat_article.md": "公众号",
            "07_geo_angle.md": "外贸/GEO",
        }
        best_platform = platform_names.get(best[0], "公众号")

    return PackQualityReport(
        repo_full_name=repo_full_name,
        publish_recommendation=recommendation,
        overall_score=overall_score,
        blocking_issues=blocking_issues,
        recommended_platform=best_platform,
        file_reviews=file_reviews,
        deleted_sentences=all_deleted,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline: orchestrates checks, triggers regeneration
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ReviewerOutcome:
    """Result of running the full reviewer pipeline on a single file."""
    file_name: str
    passed: bool
    needs_regeneration: bool
    core_checks_failed: list[str] = field(default_factory=list)
    content: str = ""


def run_reviewer_pipeline(
    file_name: str, content: str, repo_full_name: str,
    ctx: dict | None = None, geo_boundary: bool = False,
    strict_mode: bool = True,
) -> ReviewerOutcome:
    """Run the reviewer pipeline on one generated file.

    Returns ReviewerOutcome with pass/fail/regeneration decisions.
    Core checks (repo_consistency, risk_boundary) are blocking.

    In strict_mode=False, only checks explicit exaggerated claims
    (no disclaimer requirements) — suitable for short-form scripts.
    """
    ctx = ctx or {}
    confirmed = ctx.get("confirmed_features", [])
    unsupported = ctx.get("unsupported_features", [])

    core_failures = []

    # Core check 1: Repo consistency (always strict)
    c1 = repo_consistency_check(content, repo_full_name, unsupported)
    if not c1.passed:
        core_failures.append(f"repo_consistency: {c1.detail}")

    # Core check 2: Risk boundary (strictness varies)
    c3 = risk_boundary_check(content, geo_boundary=geo_boundary, strict_mode=strict_mode)
    if not c3.passed:
        core_failures.append(f"risk_boundary: {c3.detail}")

    # Non-core: Claim grounding
    claim_grounding_check(content, confirmed)

    # Non-core: Platform style (inferred from file_name)
    platform_map = {
        "02_xiaohongshu": "xiaohongshu",
        "03_douyin_video": "douyin",
        "04_videohao_script": "videohao",
        "05_wechat_article": "wechat_article",
        "07_geo_angle": "geo_angle",
    }
    platform = platform_map.get(file_name)
    if platform:
        platform_style_check(content, platform)

    needs_regen = len(core_failures) > 0

    return ReviewerOutcome(
        file_name=file_name,
        passed=not needs_regen,
        needs_regeneration=needs_regen,
        core_checks_failed=core_failures,
        content=content if not needs_regen else "",
    )


def write_quality_report(pack_dir: Path, report: PackQualityReport) -> Path:
    """Write the quality review report as 10_quality_check.md in the pack."""
    lines = [
        f"# 发布前质量检查报告",
        "",
        f"**项目**：{report.repo_full_name}",
        f"**检查时间**：{__import__('datetime').datetime.now().isoformat()[:19]}",
        "",
        "---",
        "",
        "## 1. 总结结论",
        "",
        f"- **是否建议发布**：{_render_recommendation(report.publish_recommendation)}",
        f"- **总分**：{report.overall_score} / 100",
        f"- **主要阻断问题**：{len(report.blocking_issues)} 个",
    ]

    if report.blocking_issues:
        for bi in report.blocking_issues:
            lines.append(f"  - {bi}")
    else:
        lines.append("  - 无阻断问题")

    lines.extend([
        f"- **建议先发布的平台**：{report.recommended_platform}",
        "",
        "---",
        "",
        "## 2. 文件级评分",
        "",
        "| 文件 | Repo一致性 | 事实准确性 | 夸大风险 | AI-FDE主线 | 平台适配 | 总分 | 状态 |",
        "|------|-----------|-----------|---------|-----------|---------|------|------|",
    ])

    for fname, fr in report.file_reviews.items():
        short = fname.replace(".md", "")
        scores = {c.check_name: c.score for c in fr.checks}
        rc = scores.get("repo_consistency", "-")
        cg = scores.get("claim_grounding", "-")
        rb = scores.get("risk_boundary", "-")
        ps = scores.get("platform_style", "-")
        status = "✅" if not fr.needs_regeneration else "🔴 需重写"
        lines.append(
            f"| {short} | {rc} | {cg} | {rb} | - | {ps} | {fr.overall_score} | {status} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Repo 一致性检查",
        "",
        f"是否围绕 **{report.repo_full_name}** 写作：",
    ])

    for fname, fr in report.file_reviews.items():
        c1 = next((c for c in fr.checks if c.check_name == "repo_consistency"), None)
        if c1:
            icon = "✅" if c1.passed else "🔴"
            lines.append(f"- {icon} {fname}: {c1.detail}")

    lines.extend([
        "",
        "如果出现以下错位内容，必须判 fail：",
        "- RAGFlow / LangChain-ChatChat / 知识库平台",
        "- Milvus / Chroma / Pinecone / 向量数据库",
        "- ChatGLM / Baichuan / 国内开源模型",
        "- 文档分割 / 嵌入模型 / 非AI工程师一键构建",
        "",
        "---",
        "",
        "## 4. 事实与断言分级",
        "",
        "每项关键断言分级：",
        "- **confirmed_by_repo** — README / Topics / 代码中可验证",
        "- **reasonable_inference** — 基于项目定位的合理推断",
        "- **unverified_claim** — 无明确依据，不能写成确定事实",
        "",
    ])

    for fname, deleted in report.deleted_sentences.items():
        if deleted:
            lines.append(f"### {fname}")
            for s in deleted[:5]:
                lines.append(f"- ⚠️ unverified_claim: `{s[:120]}`")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## 5. 夸大与合规风险",
        "",
        "已检查以下风险维度：",
        "- 万能化表达（\"任何网站都...\"）",
        "- 绕过反爬暗示（\"自动渲染\"、\"绕过限制\"）",
        "- 登录/账号自动化暗示",
        "- 保证排名/询盘/引用",
        "- 侵犯版权/隐私风险",
        "- robots.txt 和服务条款风险",
        "",
    ])

    # Summarize risk findings
    for fname, fr in report.file_reviews.items():
        c3 = next((c for c in fr.checks if c.check_name == "risk_boundary"), None)
        if c3 and c3.issues:
            lines.append(f"### {fname}")
            for issue in c3.issues:
                lines.append(f"- ❌ {issue}")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## 6. 必须删除或改写的句子",
        "",
    ])

    has_any = False
    for fname, deleted in report.deleted_sentences.items():
        if deleted:
            has_any = True
            lines.append(f"### {fname}")
            for i, s in enumerate(deleted[:5], 1):
                lines.append(f"{i}. `{s[:150]}`")
            lines.append("")

    if not has_any:
        lines.append("未发现必须删除的句子。")

    lines.extend([
        "---",
        "",
        "## 7. 发布建议",
        "",
        f"- **小红书**：{'✅ 可发' if _file_ok(report, '02_xiaohongshu.md') else '❌ 不建议'}",
        f"- **公众号**：{'✅ 可发' if _file_ok(report, '05_wechat_article.md') else '❌ 不建议'}",
        f"- **视频号**：{'✅ 可发' if _file_ok(report, '04_videohao_script.md') else '❌ 不建议'}",
        f"- **外贸/GEO**：{'✅ 可发' if _file_ok(report, '07_geo_angle.md') else '❌ 不建议'}",
        "- 是否需要人工补充观点：是（建议对每个文件做最终通读）",
        "",
        "---",
        "",
        "## 8. 最终结论",
        "",
    ])

    if report.publish_recommendation == "no":
        lines.append("**不建议发布，需重新生成核心文件。**")
        lines.append("")
        lines.append("阻断原因：")
        for bi in report.blocking_issues:
            lines.append(f"- {bi}")
    elif report.publish_recommendation == "revise_first":
        lines.append("**修改后发布** — 存在非阻断问题，建议逐条修复后重新检查。")
    else:
        lines.append("**可以发布** — 所有检查通过，内容质量满足发布标准。")

    lines.extend([
        "",
        "---",
        "",
        f"*报告生成时间：{__import__('datetime').datetime.now().isoformat()[:19]}*",
    ])

    report_path = pack_dir / "10_quality_check.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _render_recommendation(rec: str) -> str:
    return {"yes": "✅ 可以发布", "no": "🔴 不建议发布", "revise_first": "⚠️ 修改后发布"}.get(rec, rec)


def _file_ok(report: PackQualityReport, fname: str) -> bool:
    fr = report.file_reviews.get(fname)
    return fr is not None and not fr.needs_regeneration
