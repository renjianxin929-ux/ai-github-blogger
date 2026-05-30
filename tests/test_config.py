"""Tests for config.py — configuration management."""
import os
import tempfile
from pathlib import Path
from unittest import mock


class TestConfigDefaults:
    """Test default configuration values when no .env is present."""

    def test_default_constants(self):
        """All config constants should have their documented defaults."""
        from src.config import (
            MAX_README_CHARS,
            MAX_REPOS_TO_ENRICH,
            MAX_REPOS_TO_ANALYZE,
            HTTP_TIMEOUT,
            LLM_TIMEOUT,
            DAYS_TO_DEDUP,
        )

        assert MAX_README_CHARS == 8000
        assert MAX_REPOS_TO_ENRICH == 30
        assert MAX_REPOS_TO_ANALYZE == 10
        assert HTTP_TIMEOUT == 20
        assert LLM_TIMEOUT == 60
        assert DAYS_TO_DEDUP == 14

    def test_keywords_not_empty(self):
        """SEARCH_KEYWORDS should be a non-empty list."""
        from src.config import SEARCH_KEYWORDS

        assert isinstance(SEARCH_KEYWORDS, list)
        assert len(SEARCH_KEYWORDS) >= 5
        assert "AI" in SEARCH_KEYWORDS or "LLM" in SEARCH_KEYWORDS

    def test_scorer_weights_sum_to_100(self):
        """Scorer weights should sum to approximately 100."""
        from src.config import SCORER_WEIGHTS

        total = sum(SCORER_WEIGHTS.values())
        assert abs(total - 100) < 1, f"Weights sum to {total}, expected ~100"

    def test_fde_dimensions(self):
        """FDE_DIMENSIONS should have F, D, E keys."""
        from src.config import FDE_DIMENSIONS

        assert "F" in FDE_DIMENSIONS
        assert "D" in FDE_DIMENSIONS
        assert "E" in FDE_DIMENSIONS

    def test_weighted_topics_not_empty(self):
        """WEIGHTED_TOPICS should be a non-empty dict with valid weights."""
        from src.config import WEIGHTED_TOPICS

        assert isinstance(WEIGHTED_TOPICS, dict)
        assert len(WEIGHTED_TOPICS) >= 10
        for key, weight in WEIGHTED_TOPICS.items():
            assert isinstance(key, str)
            assert isinstance(weight, int)
            assert 1 <= weight <= 5


class TestConfigEnvLoading:
    """Test that environment variables override defaults."""

    def test_env_overrides_max_readme_chars(self, monkeypatch):
        """Setting MAX_README_CHARS env var should override default."""
        monkeypatch.setenv("MAX_README_CHARS", "5000")
        # Re-import to pick up env var (module-level constants are set at import)
        import importlib
        import src.config

        importlib.reload(src.config)
        assert src.config.MAX_README_CHARS == 5000

    def test_env_overrides_max_repos_to_enrich(self, monkeypatch):
        """MAX_REPOS_TO_ENRICH can be overridden via env."""
        monkeypatch.setenv("MAX_REPOS_TO_ENRICH", "20")
        import importlib
        import src.config

        importlib.reload(src.config)
        assert src.config.MAX_REPOS_TO_ENRICH == 20

    def test_missing_env_vars_fallback_to_defaults(self):
        """When no env vars set, defaults are used."""
        import importlib
        import src.config

        importlib.reload(src.config)
        assert src.config.MAX_REPOS_TO_ENRICH == 30
        assert src.config.DAYS_TO_DEDUP == 14


class TestLLMConfig:
    """Test LLM API configuration loading."""

    def test_get_llm_config_from_env(self, monkeypatch):
        """get_llm_config should return values from environment."""
        monkeypatch.setenv("LLM_API_BASE", "https://api.test.com/v1")
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        monkeypatch.setenv("LLM_MODEL", "test-model")

        import importlib
        import src.config

        importlib.reload(src.config)
        cfg = src.config.get_llm_config()
        assert cfg["base_url"] == "https://api.test.com/v1"
        assert cfg["api_key"] == "sk-test-key"
        assert cfg["model"] == "test-model"

    def test_get_llm_config_raises_when_missing_key(self):
        """get_llm_config should raise when LLM_API_KEY is missing."""
        import importlib
        import src.config

        importlib.reload(src.config)

        import pytest

        with pytest.raises(ValueError, match="LLM_API_KEY"):
            src.config.get_llm_config()
