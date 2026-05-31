"""Configuration management for ai-github-blogger.

All secrets loaded from .env via python-dotenv.
API keys must never be hardcoded in this file or in any workflow YAML.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from src/)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# ── Integer config (env-overridable, with documented defaults) ────────────
MAX_README_CHARS = int(os.getenv("MAX_README_CHARS", "8000"))
MAX_REPOS_TO_ENRICH = int(os.getenv("MAX_REPOS_TO_ENRICH", "30"))
MAX_REPOS_TO_ANALYZE = int(os.getenv("MAX_REPOS_TO_ANALYZE", "10"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
DAYS_TO_DEDUP = int(os.getenv("DAYS_TO_DEDUP", "14"))
EVERGREEN_STAR_THRESHOLD = int(os.getenv("EVERGREEN_STAR_THRESHOLD", "30000"))

# ── GitHub API ────────────────────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ── Search keywords ───────────────────────────────────────────────────────
SEARCH_KEYWORDS = [
    "AI",
    "LLM",
    "Agent",
    "RAG",
    "MCP",
    "Dify",
    "n8n",
    "automation",
    "GEO",
    "SEO",
    "prompt-engineering",
    "vector-database",
    "langchain",
    "llamaindex",
    "function-calling",
]

# ── AI-FDE dimensions ─────────────────────────────────────────────────────
FDE_DIMENSIONS = {
    "F": "功能创新 — 该项目解决了什么具体问题？技术方案有何新意？",
    "D": "差异化 — 与同类项目相比，它有什么不可替代的地方？",
    "E": "生态价值 — 对中文开发者和 AI 生态的实际价值有多大？",
}

# ── Scorer weights (must sum to ~100) ─────────────────────────────────────
SCORER_WEIGHTS = {
    "stars": 12,
    "activity": 30,
    "topic_match": 30,
    "readme_quality": 10,
    "content_tellability": 10,
    "community_health": 3,
    "license": 5,
}

# ── Weighted topic keywords for scoring (higher = more选题价值) ──────────
WEIGHTED_TOPICS = {
    "rag": 5,
    "agent": 5,
    "mcp": 5,
    "dify": 4,
    "n8n": 4,
    "geo": 4,
    "seo": 4,
    "automation": 4,
    "workflow": 4,
    "browser-use": 4,
    "eval": 3,
    "prompt": 3,
    "multimodal": 3,
    "function-calling": 3,
    "prompt-engineering": 2,
    "vector-database": 2,
    "langchain": 2,
    "llamaindex": 2,
    "llm": 2,
    "ai": 1,
}

# ── High-risk keywords — repos matching these are blocked from all recommendations
HIGH_RISK_KEYWORDS = [
    "deepfake", "face swap", "faceswap", "fake webcam", "ai-face",
    "realtime-face-changer", "voice clone", "impersonation", "phishing",
    "spam", "credential", "malware", "bypass", "scraping login",
    "account automation", "exploit", "keylogger", "spyware",
    "social engineering", "cracking",
    # v7: expanded from adversarial analysis
    "password crack", "wifi crack", "brute force",
    "instagram auto", "auto-like", "auto-follow", "auto-comment",
    "social media bot", "twitter bot", "linkedin automation",
    "pentest", "penetration test",
    "hack tool", "hacking tool",
    # v7: NSFW/adult content risks
    "nsfw", "uncensored", "adult-content", "porn", "xxx-adult",
    "nude", "naked", "explicit-content", "not-suitable-for-work",
]

# ── AI eligibility — repos must match at least one to enter Top 20
# v7: Split into STRONG (real AI substance) and WEAK (ambiguous, needs more scrutiny)
AI_ELIGIBILITY_KEYWORDS = [
    "ai", "llm", "agent", "rag", "mcp", "automation", "workflow",
    "prompt", "eval", "embedding", "vector", "chatbot", "browser-use",
    "geo", "ai-search", "gpt", "claude", "openai", "deepseek",
    "function-calling", "langchain", "llamaindex", "langgraph",
    "tool-use", "tool-calling", "orchestration", "ai-agent",
    "machine-learning", "deep-learning", "nlp", "natural-language",
    "generative-ai", "genai", "transformer", "diffusion", "stable-diffusion",
]

# Strong AI signals — repo has real AI substance beyond just mentioning "ai"
STRONG_AI_SIGNALS = [
    "llm", "agent", "rag", "mcp", "langchain", "llamaindex", "langgraph",
    "openai", "deepseek", "claude", "gpt", "function-calling", "tool-use",
    "tool-calling", "orchestration", "ai-agent", "chatbot", "browser-use",
    "machine-learning", "deep-learning", "nlp", "transformer",
    "generative-ai", "genai", "diffusion", "stable-diffusion",
    "embedding", "vector", "prompt-engineering", "prompt",
    # v7: Practical AI tool terms from adversarial analysis
    "n8n", "dify", "comfyui", "firecrawl", "crawl",
    "knowledge-graph", "graph-rag", "text-to-sql",
    "model-serving", "inference", "fine-tuning",
    "copilot", "code-assistant", "ai-code",
]

# Hype indicators — repos matching these AND having short/empty READMEs are flagged
HYPE_INDICATORS = [
    "whitepaper coming soon", "token sale", "tokenomics",
    "revolutionary", "game-changer", "disruptive",
    "no working code", "early stage", "coming soon",
    "join our discord", "join our telegram",
    "blockchain", "web3", "crypto token", "nft",
    "decentralized", "meme coin",
]

# ── Non-AI disqualifiers — repos matching these are NOT AI content
NON_AI_DISQUALIFIERS = [
    "java面试", "java 面试", "leetcode", "算法题", "后端面试",
    "前端面试", "roadmap", "计算机基础", "数据结构与算法",
    "设计模式", "操作系统", "计算机网络",
]

# ── Content type classification indicators
AWESOME_LIST_INDICATORS = [
    "awesome-", "awesome-list", "awesome list",
    "curated list", "项目合集", "资源汇总",
]

TUTORIAL_INDICATORS = [
    "面试", "interview", "从零开始", "roadmap",
    "leetcode", "算法题", "学习路线", "handbook",
    "cheatsheet", "cheat-sheet", "coding-interview",
    "cookbook", "system-design-interview",
    "后端面试", "前端面试", "java面试",
    "tutorial", "course", "beginner", "for-beginners",
    "book", "从零", "lesson", "course",
]

FRAMEWORK_INDICATORS = [
    "low-code", "no-code",
    "orchestration", "workflow-automation", "ipaas",
    "inference engine", "model serving",
    "vector database",
    "machine learning framework", "deep learning framework",
    "infrastructure", "iaas", "devops platform",
    # Category-based: topics often signal framework/infrastructure projects
    "vector-database", "embeddings",
]

# ── Known evergreen projects (full_name) — always treated as framework_tool
KNOWN_EVERGREEN = {
    "langgenius/dify", "n8n-io/n8n", "langchain-ai/langchain",
    "Significant-Gravitas/AutoGPT", "microsoft/autogen",
    "run-llama/llama_index", "langflow-ai/langflow",
    "crewAIInc/crewAI", "meta-llama/llama", "openai/openai-python",
    "ollama/ollama", "supabase/supabase", "AUTOMATIC1111/stable-diffusion-webui",
    "Comfy-Org/ComfyUI", "open-webui/open-webui",
    # Large AI/ML infrastructure projects (30K+ stars, framework-level)
    "ggerganov/llama.cpp", "huggingface/transformers",
    "apache/airflow", "milvus-io/milvus",
    "home-assistant/core", "ansible/ansible",
    "hashicorp/terraform",
    # v7: ML platform frameworks from adversarial analysis
    "mlflow/mlflow", "iterative/dvc",
    "prefecthq/prefect", "dagster-io/dagster",
}

# ── Data directories (relative to project root) ───────────────────────────
DATA_DIR = _project_root / "data"
REPORTS_DIR = DATA_DIR / "reports"
CACHE_DIR = DATA_DIR / "cache"
STATE_DIR = DATA_DIR / "state"
CONTENT_PACKS_DIR = DATA_DIR / "content_packs"
TEMPLATES_DIR = _project_root / "templates"

SEEN_REPOS_FILE = STATE_DIR / "seen_repos.json"
GENERATED_REPOS_FILE = STATE_DIR / "generated_repos.json"

# ── GitHub API base ───────────────────────────────────────────────────────
GITHUB_API_BASE = "https://api.github.com"


def get_llm_config() -> dict:
    """Return LLM API configuration from environment.

    Raises ValueError if LLM_API_KEY is missing.
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        raise ValueError(
            "LLM_API_KEY is not set. Copy .env.example to .env and fill in your key."
        )
    return {
        "base_url": os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1"),
        "api_key": api_key,
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
    }


def get_llm_providers() -> list[dict]:
    """Return LLM providers ordered by priority.

    Each provider is a dict with: name, base_url, api_key, model.
    Primary provider (DeepSeek) uses LLM_API_KEY/LLM_API_BASE/LLM_MODEL.
    Fallback providers use FALLBACK_LLM_* env vars.
    """
    providers = []
    # Primary
    primary_key = os.getenv("LLM_API_KEY", "")
    if primary_key:
        providers.append({
            "name": "deepseek",
            "base_url": os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1"),
            "api_key": primary_key,
            "model": os.getenv("LLM_MODEL", "deepseek-chat"),
        })
    # Fallback 1
    fb_key = os.getenv("FALLBACK_LLM_API_KEY", "")
    if fb_key:
        providers.append({
            "name": os.getenv("FALLBACK_LLM_PROVIDER", "openrouter"),
            "base_url": os.getenv("FALLBACK_LLM_API_BASE", "https://openrouter.ai/api/v1"),
            "api_key": fb_key,
            "model": os.getenv("FALLBACK_LLM_MODEL", "openai/gpt-4o"),
        })
    return providers


def mask_key(key: str) -> str:
    """Return a safe representation of an API key (prefix only)."""
    if not key:
        return "not configured"
    if len(key) <= 8:
        return "*** (too short)"
    return f"{key[:4]}***{key[-4:]}"
