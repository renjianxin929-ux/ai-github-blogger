"""Phase 8: Unified error handling with retry, backoff, error classification.

Provides a unified request wrapper for all GitHub API calls with:
- 3-retry exponential backoff (1s → 2s → 4s)
- 7 error classifications
- Single-repo failure isolation
- Cache-first degraded mode for content generation
- failure_summary tracking across pipeline runs
"""

import enum
import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Error classification
# ═════════════════════════════════════════════════════════════════════════════


class ErrorType(enum.Enum):
    RATE_LIMIT = "rate_limit"        # 403/429 — GitHub API rate limit
    SSL_ERROR = "ssl_error"           # SSL/TLS handshake failure
    TIMEOUT = "timeout"               # Request timed out
    NOT_FOUND = "not_found"           # 404 — repo/endpoint doesn't exist
    README_MISSING = "readme_missing" # 404 on /readme endpoint (expected for some repos)
    LICENSE_MISSING = "license_missing" # No license field in repo data
    AUTH_ERROR = "auth_error"         # 401 — bad or missing token
    UNKNOWN = "unknown"               # Uncategorized error


def classify_error(exception: Exception, status_code: int | None = None) -> ErrorType:
    """Classify an exception into one of 7 error types."""
    if isinstance(exception, requests.exceptions.Timeout):
        return ErrorType.TIMEOUT
    if isinstance(exception, requests.exceptions.SSLError):
        return ErrorType.SSL_ERROR
    if isinstance(exception, requests.exceptions.ConnectionError):
        return ErrorType.TIMEOUT

    if status_code == 429 or status_code == 403:
        # 403 could be rate limit or auth — check response body
        return ErrorType.RATE_LIMIT
    if status_code == 404:
        return ErrorType.NOT_FOUND
    if status_code == 401:
        return ErrorType.AUTH_ERROR

    return ErrorType.UNKNOWN


# ═════════════════════════════════════════════════════════════════════════════
# Failure tracking (pipeline-wide)
# ═════════════════════════════════════════════════════════════════════════════


@dataclass
class FailureRecord:
    repo: str
    operation: str
    error_type: ErrorType
    attempts: int
    message: str


@dataclass
class FailureSummary:
    """Accumulates failures across a pipeline run for end-of-run reporting."""
    records: list[FailureRecord] = field(default_factory=list)
    total_requests: int = 0
    total_failures: int = 0
    degraded_fallbacks: int = 0

    def record(self, repo: str, operation: str, error_type: ErrorType,
               attempts: int, message: str, degraded: bool = False):
        self.total_requests += 1
        self.total_failures += 1
        if degraded:
            self.degraded_fallbacks += 1
        self.records.append(FailureRecord(
            repo=repo, operation=operation, error_type=error_type,
            attempts=attempts, message=message,
        ))

    def has_critical(self) -> bool:
        """True if there are non-isolated failures (rate_limit, auth_error)."""
        critical = {ErrorType.RATE_LIMIT, ErrorType.AUTH_ERROR, ErrorType.SSL_ERROR}
        return any(r.error_type in critical for r in self.records)

    def summary_text(self) -> str:
        """Produce human-readable failure summary."""
        if not self.records:
            return "No failures recorded."

        by_type: dict[ErrorType, list[FailureRecord]] = {}
        for r in self.records:
            by_type.setdefault(r.error_type, []).append(r)

        lines = [
            f"Failure Summary: {self.total_failures}/{self.total_requests} requests failed",
            f"  Degraded fallbacks used: {self.degraded_fallbacks}",
        ]
        for etype, recs in sorted(by_type.items(), key=lambda x: -len(x[1])):
            lines.append(f"  [{etype.value}] ({len(recs)}):")
            for r in recs[:5]:
                lines.append(f"    - {r.repo}: {r.operation} — {r.message}")

        critical = self.has_critical()
        if critical:
            lines.append("  WARNING: Critical failures detected (rate_limit/auth/ssl).")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# Unified request wrapper with retry + backoff
# ═════════════════════════════════════════════════════════════════════════════


def github_request(
    url: str,
    headers: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    base_delay: float = 1.0,
    operation: str = "api_call",
    repo_name: str = "unknown",
    failure_summary: FailureSummary | None = None,
) -> requests.Response | None:
    """Unified GitHub API request with exponential backoff retry.

    Args:
        url: Full API URL.
        headers: Request headers (Authorization etc.).
        timeout: Per-request timeout in seconds.
        max_retries: Max retry attempts (default 3 → 1+3=4 total tries).
        base_delay: Initial backoff delay in seconds (doubles each retry).
        operation: Human-readable operation name for logging.
        repo_name: Repo full_name for failure tracking.
        failure_summary: Optional FailureSummary to record failures into.

    Returns:
        requests.Response on success, None after all retries exhausted.
    """
    last_error: Exception | None = None
    last_status: int | None = None

    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)

            # Rate limit — always retry with backoff
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "5")
                wait = float(retry_after) if retry_after.isdigit() else base_delay * (2 ** attempt)
                logger.warning("Rate limited for %s, waiting %.0fs (attempt %d/%d)",
                               repo_name, wait, attempt + 1, max_retries + 1)
                time.sleep(wait)
                last_status = 429
                continue

            # 403 could be rate limit or actual forbidden
            if resp.status_code == 403:
                if "rate limit" in resp.text.lower():
                    wait = base_delay * (2 ** attempt)
                    logger.warning("Rate limited (403) for %s, waiting %.0fs", repo_name, wait)
                    time.sleep(wait)
                    last_status = 403
                    continue
                # Actual 403 forbidden — don't retry
                last_status = 403
                break

            # Server errors — retry
            if resp.status_code in (500, 502, 503, 504):
                if attempt < max_retries:
                    wait = base_delay * (2 ** attempt)
                    logger.warning("Server error %d for %s, retrying in %.0fs (attempt %d/%d)",
                                   resp.status_code, repo_name, wait, attempt + 1, max_retries + 1)
                    time.sleep(wait)
                    last_status = resp.status_code
                    continue
                last_status = resp.status_code
                break

            resp.raise_for_status()
            return resp

        except requests.exceptions.Timeout as e:
            last_error = e
            last_status = None
            if attempt < max_retries:
                wait = base_delay * (2 ** attempt)
                logger.warning("Timeout for %s, retrying in %.0fs (attempt %d/%d)",
                               repo_name, wait, attempt + 1, max_retries + 1)
                time.sleep(wait)
        except requests.exceptions.SSLError as e:
            last_error = e
            logger.error("SSL error for %s — not retrying", repo_name)
            break
        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt < max_retries:
                wait = base_delay * (2 ** attempt)
                logger.warning("Connection error for %s, retrying in %.0fs", repo_name, wait)
                time.sleep(wait)
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries:
                wait = base_delay * (2 ** attempt)
                logger.warning("Request error for %s: %s, retrying", repo_name, e)
                time.sleep(wait)

    # All retries exhausted — record failure
    etype = classify_error(last_error, last_status)
    msg = str(last_error) if last_error else f"HTTP {last_status}"
    logger.warning("Request FAILED for %s [%s]: %s (after %d attempts)",
                   repo_name, etype.value, msg, max_retries + 1)
    if failure_summary:
        failure_summary.record(repo_name, operation, etype, max_retries + 1, msg)
    return None


# ═════════════════════════════════════════════════════════════════════════════
# Higher-level wrappers for specific operations
# ═════════════════════════════════════════════════════════════════════════════


def github_repo_meta(full_name: str, headers: dict, timeout: int = 30,
                     failure_summary: FailureSummary | None = None) -> dict | None:
    """Fetch /repos/{owner}/{repo} metadata with retry."""
    from .config import GITHUB_API_BASE
    url = f"{GITHUB_API_BASE}/repos/{full_name}"
    resp = github_request(url, headers=headers, timeout=timeout,
                          operation="repo_meta", repo_name=full_name,
                          failure_summary=failure_summary)
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def github_readme(full_name: str, headers: dict, timeout: int = 30,
                  failure_summary: FailureSummary | None = None) -> str | None:
    """Fetch /repos/{owner}/{repo}/readme with retry. Returns None on failure (expected for some repos)."""
    from .config import GITHUB_API_BASE
    url = f"{GITHUB_API_BASE}/repos/{full_name}/readme"
    resp = github_request(url, headers=headers, timeout=timeout,
                          operation="readme", repo_name=full_name,
                          failure_summary=failure_summary)
    if resp is None:
        return None
    try:
        import base64
        data = resp.json()
        if data.get("encoding") == "base64" and data.get("content"):
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def github_contributors(full_name: str, headers: dict, timeout: int = 30,
                        failure_summary: FailureSummary | None = None) -> int:
    """Fetch contributor count with retry. Returns 0 on failure."""
    from .config import GITHUB_API_BASE
    url = f"{GITHUB_API_BASE}/repos/{full_name}/contributors?per_page=5"
    resp = github_request(url, headers=headers, timeout=timeout,
                          operation="contributors", repo_name=full_name,
                          failure_summary=failure_summary)
    if resp is None:
        return 0
    try:
        return len(resp.json())
    except Exception:
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# Cache-first degraded mode helpers
# ═════════════════════════════════════════════════════════════════════════════


def cache_or_fetch(cache_dir: str, cache_key: str,
                   fetch_fn: Callable[[], Any],
                   ttl_seconds: int = 86400) -> tuple[Any, bool]:
    """Cache-first read with TTL. Returns (data, is_degraded).

    If cache exists and is fresh, returns cached data with is_degraded=False.
    If cache is stale or missing, calls fetch_fn().
    If fetch_fn() fails and stale cache exists, returns stale cache with is_degraded=True.
    If fetch_fn() fails and no cache exists, returns (None, True).
    """
    import json
    from pathlib import Path

    cache_path = Path(cache_dir) / f"{cache_key}.json"

    # Check fresh cache
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < ttl_seconds:
            try:
                return json.loads(cache_path.read_text(encoding="utf-8")), False
            except Exception:
                pass
        # Stale cache — keep as fallback
        try:
            stale_data = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            stale_data = None
    else:
        stale_data = None

    # Try fresh fetch
    try:
        data = fetch_fn()
        if data is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
            return data, False
    except Exception:
        logger.warning("Fetch failed for %s, falling back to cache", cache_key)

    # Degraded: use stale cache
    if stale_data is not None:
        logger.warning("Using stale cache for %s (degraded mode)", cache_key)
        return stale_data, True

    return None, True
