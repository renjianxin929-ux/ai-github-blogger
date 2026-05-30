"""Risk scoring — detailed multi-dimensional risk assessment.

Replaces the old "无明显风险" with specific per-category analysis.
High-risk repos (deepfake, phishing, etc.) are BLOCKED from all recommendations.
Browser automation repos get nuanced warnings, not "no risk".
"""
from dataclasses import dataclass, field

# ── Blocked keywords — repos matching any of these are BLOCKED ──────────
# v7: Synced with config.HIGH_RISK_KEYWORDS
BLOCKED_KEYWORDS = [
    "deepfake", "face swap", "faceswap", "fake webcam", "ai-face",
    "realtime-face-changer", "voice clone", "impersonation",
    "phishing", "spam", "malware", "credential", "bypass",
    "scraping login", "account automation",
    "exploit", "keylogger", "spyware",
    "social engineering", "cracking",
    "password crack", "wifi crack", "brute force",
    "instagram auto", "auto-like", "auto-follow", "auto-comment",
    "social media bot", "twitter bot", "linkedin automation",
    "pentest", "penetration test",
    "hack tool", "hacking tool",
]

# ── Risk category indicators ────────────────────────────────────────────

ACCOUNT_AUTOMATION_SIGNALS = [
    "login", "account", "credential", "session", "cookie",
    "automation", "bot", "browser-use", "playwright", "selenium",
    "puppeteer", "browser automation",
    "auto-like", "auto-follow", "auto-comment", "auto engage",
    "instagram", "social media", "linkedin", "twitter",
]

SCRAPING_SIGNALS = [
    "scrap", "crawl", "extract data", "web data", "parse html",
    "web scraping",
]

DATA_PRIVACY_SIGNALS = [
    "telemetry", "analytics", "user behavior",
    "fingerprint", "surveillance", "keylogger",
    "user tracking", "employee monitoring", "behavior tracking",
    "user activity tracking", "keystroke logging", "screen monitoring",
]

HYPE_SIGNALS = [
    "revolutionary", "game-changer", "disruptive", "world-changing",
    "ultimate", "best ever",
]


@dataclass
class RiskProfile:
    """Detailed risk assessment for a repository."""
    full_name: str
    overall: str = "low"  # low / medium / high / blocked
    blocked: bool = False
    blocked_reasons: list[str] = field(default_factory=list)

    license_risk: str = "low"
    data_privacy_risk: str = "low"
    account_automation_risk: str = "low"
    scraping_platform_risk: str = "low"
    deepfake_impersonation_risk: str = "low"
    spam_phishing_malware_risk: str = "low"
    hype_risk: str = "low"
    client_misuse_risk: str = "low"

    license_detail: str = ""
    warnings: list[str] = field(default_factory=list)
    must_include_disclaimers: list[str] = field(default_factory=list)

    def to_selection_penalty(self) -> float:
        """Convert risk level to a selection score penalty (0 = blocked, 1 = no penalty)."""
        if self.overall == "blocked":
            return 0.0
        elif self.overall == "high":
            return 0.3
        elif self.overall == "medium":
            return 0.7
        else:
            return 1.0

    def to_business_penalty(self) -> float:
        """Convert risk level to a business score penalty."""
        if self.overall == "blocked":
            return 0.0
        elif self.overall == "high":
            return 0.4
        elif self.overall == "medium":
            return 0.7
        else:
            return 1.0


def _build_text(repo) -> str:
    """Build searchable text from repo metadata + README."""
    text = f"{repo.name or ''} {repo.description or ''} {' '.join(repo.topics or [])}".lower()
    readme = (getattr(repo, 'readme', '') or '').lower()
    return f"{text} {readme}"


def assess_risk(repo) -> RiskProfile:
    """Perform a detailed risk assessment on a repo.

    Args:
        repo: ScoredRepo or EnrichedRepo with name, description, topics, readme, license.

    Returns:
        RiskProfile with per-category assessments, warnings, and disclaimers.
    """
    text = _build_text(repo)
    full_name = getattr(repo, 'full_name', '')
    license_str = (getattr(repo, 'license', '') or '').lower()
    profile = RiskProfile(full_name=full_name)

    # ── 1. Blocked check ────────────────────────────────────────────────
    for kw in BLOCKED_KEYWORDS:
        if kw in text:
            profile.blocked = True
            profile.blocked_reasons.append(kw)

    if profile.blocked:
        profile.overall = "blocked"
        profile.deepfake_impersonation_risk = "high" if any(
            k in text for k in ["deepfake", "face swap", "faceswap", "fake webcam",
                                 "voice clone", "impersonation"]
        ) else "low"
        profile.spam_phishing_malware_risk = "high" if any(
            k in text for k in ["phishing", "spam", "malware", "credential", "bypass"]
        ) else "low"
        profile.account_automation_risk = "high" if "account automation" in text else "low"
        return profile

    # ── 2. License risk ─────────────────────────────────────────────────
    if not license_str or license_str == "未指定":
        profile.license_risk = "medium"
        profile.license_detail = "未指定许可证，商用前需确认版权归属"
        profile.warnings.append("许可证不明确，商业使用前请确认授权")
    elif any(t in license_str for t in ("gpl", "agpl")):
        profile.license_risk = "medium"
        profile.license_detail = f"{license_str} 有 Copyleft 要求，商用需评估合规性"
        profile.warnings.append(f"使用 {license_str} 许可证，商业集成需注意合规")
    elif license_str in ("mit", "apache-2.0", "bsd-3-clause", "unlicense"):
        profile.license_risk = "low"
        profile.license_detail = f"{license_str} 是宽松开源许可证，商业使用友好"
    else:
        profile.license_risk = "low"
        profile.license_detail = f"{license_str} — 建议阅读完整条款"

    # ── 3. Data privacy risk ────────────────────────────────────────────
    privacy_hits = [s for s in DATA_PRIVACY_SIGNALS if s in text]
    if privacy_hits:
        profile.data_privacy_risk = "medium"
        profile.warnings.append(f"涉及用户数据/隐私相关: {', '.join(privacy_hits)}")
    else:
        profile.data_privacy_risk = "low"

    # ── 4. Account automation risk ──────────────────────────────────────
    auto_hits = [s for s in ACCOUNT_AUTOMATION_SIGNALS if s in text]
    if "browser-use" in full_name.lower() or "browser-use" in text:
        profile.account_automation_risk = "medium"
        profile.scraping_platform_risk = "medium"
        profile.client_misuse_risk = "medium"
        profile.warnings.append(
            "涉及浏览器自动化操作，可作为合规工具使用，"
            "但涉及登录、批量采集、账号操作、平台自动化时风险升高"
        )
        profile.must_include_disclaimers.append(
            "本文仅讨论项目的技术原理和合规应用场景（如内部效率提升、测试自动化），"
            "不鼓励任何违反平台服务条款的操作"
        )
    elif any(k in text for k in ("account automation", "credential")):
        profile.account_automation_risk = "high"
        profile.warnings.append("涉及账号自动化或凭据操作，风险较高")
    elif any(k in text for k in ("automation", "login")):
        profile.account_automation_risk = "medium"
        profile.warnings.append("涉及自动化操作，注意区分合规与违规场景")

    # ── 5. Scraping / platform rules risk ───────────────────────────────
    if "browser-use" not in full_name.lower() and "browser-use" not in text:
        scrape_hits = [s for s in SCRAPING_SIGNALS if s in text]
        if scrape_hits and profile.scraping_platform_risk == "low":
            profile.scraping_platform_risk = "medium"
            profile.warnings.append("涉及网页数据采集，需注意平台服务条款和数据合规")

    # ── 6. Deepfake / impersonation risk ────────────────────────────────
    profile.deepfake_impersonation_risk = "low"  # Already checked in blocked

    # ── 7. Spam / phishing / malware risk ───────────────────────────────
    profile.spam_phishing_malware_risk = "low"  # Already checked in blocked

    # ── 8. Hype risk ────────────────────────────────────────────────────
    desc = (getattr(repo, 'description', '') or '').lower()
    hype_hits = [s for s in HYPE_SIGNALS if s in desc]
    if hype_hits:
        profile.hype_risk = "medium"
        profile.warnings.append(f"项目描述中使用较强词汇（{', '.join(hype_hits)}），建议在内容中保持客观")

    # ── 9. Client misuse risk (if not already set) ──────────────────────
    if profile.client_misuse_risk == "low":
        if any(k in text for k in ("api", "sdk", "library", "toolkit")):
            profile.client_misuse_risk = "low"  # Most tools have some misuse potential
            if profile.account_automation_risk in ("medium", "high"):
                profile.client_misuse_risk = "medium"

    # ── 10. Determine overall ───────────────────────────────────────────
    risk_levels = [
        profile.license_risk,
        profile.data_privacy_risk,
        profile.account_automation_risk,
        profile.scraping_platform_risk,
        profile.deepfake_impersonation_risk,
        profile.spam_phishing_malware_risk,
        profile.hype_risk,
        profile.client_misuse_risk,
    ]
    if any(r == "high" for r in risk_levels):
        profile.overall = "high"
    elif sum(1 for r in risk_levels if r == "medium") >= 4:
        profile.overall = "high"
    elif any(r == "medium" for r in risk_levels):
        profile.overall = "medium"
    else:
        profile.overall = "low"

    return profile
