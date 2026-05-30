"""Tests for analyzer.py — LLM API analysis (OpenAI-compatible)."""
import json
from unittest import mock

import pytest


def _make_scored_repo(full_name="test/repo", stars=5000, readme="# Test\n\nSome content"):
    """Helper to build a ScoredRepo for analyzer tests."""
    from src.scorer import ScoredRepo

    return ScoredRepo(
        full_name=full_name,
        name=full_name.split("/")[-1],
        description="A test AI framework",
        url=f"https://github.com/{full_name}",
        language="Python",
        stars=stars,
        forks=300,
        updated_at="2026-05-28T00:00:00Z",
        topics=["AI", "LLM", "agent"],
        license="MIT",
        readme=readme,
        contributors_count=5,
        score=85.0,
        subscores={"stars": 18, "activity": 25, "topic_match": 20, "readme_quality": 12, "community_health": 5, "license": 5},
    )


LLM_RESPONSE_FDE = {
    "choices": [{
        "message": {
            "content": json.dumps({
                "F": "该项目解决了代码库知识图谱的自动构建问题，创新点在于零token增量更新。",
                "D": "相比同类工具，支持12+语言的Tree-sitter解析，搜索速度更快。",
                "E": "对中文开发者友好，支持中文README和代码注释的语义理解。",
                "overall_score": 8,
            }, ensure_ascii=False),
        },
    }],
}


class TestAIFDEAnalyze:
    """Test ai_fde_analyze function."""

    @mock.patch("src.analyzer.requests.post")
    @mock.patch("src.analyzer.get_llm_config")
    def test_ai_fde_analyze_returns_analysis(self, mock_config, mock_post):
        """Should call LLM API and return parsed FDEAnalysis."""
        from src.analyzer import ai_fde_analyze

        mock_config.return_value = {
            "base_url": "https://api.test.com/v1",
            "api_key": "sk-test",
            "model": "test-model",
        }

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = LLM_RESPONSE_FDE
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        repo = _make_scored_repo()
        result = ai_fde_analyze(repo)

        assert result.F is not None
        assert result.D is not None
        assert result.E is not None
        assert result.overall_score is not None
        # Verify API was called with correct payload
        call_args = mock_post.call_args
        assert "/chat/completions" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["model"] == "test-model"
        assert len(payload["messages"]) == 2

    @mock.patch("src.analyzer.requests.post")
    @mock.patch("src.analyzer.get_llm_config")
    def test_ai_fde_analyze_handles_api_error(self, mock_config, mock_post):
        """Should return fallback analysis on API failure."""
        from src.analyzer import ai_fde_analyze

        mock_config.return_value = {
            "base_url": "https://api.test.com/v1",
            "api_key": "sk-test",
            "model": "test-model",
        }
        mock_post.side_effect = Exception("Connection refused")

        repo = _make_scored_repo()
        result = ai_fde_analyze(repo)

        # Should return fallback, not crash
        assert result.F is not None
        assert "失败" in result.F or "fallback" in result.F.lower() or "无法" in result.F

    @mock.patch("src.analyzer.requests.post")
    @mock.patch("src.analyzer.get_llm_config")
    def test_ai_fde_analyze_handles_malformed_json(self, mock_config, mock_post):
        """Should handle LLM returning invalid JSON gracefully."""
        from src.analyzer import ai_fde_analyze

        mock_config.return_value = {
            "base_url": "https://api.test.com/v1",
            "api_key": "sk-test",
            "model": "test-model",
        }

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "not valid json {{{"}}],
        }
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        repo = _make_scored_repo()
        result = ai_fde_analyze(repo)

        # Should return fallback, not crash
        assert result.F is not None


class TestGenerateContent:
    """Test generate_content function."""

    @mock.patch("src.analyzer.requests.post")
    @mock.patch("src.analyzer.get_llm_config")
    @mock.patch("pathlib.Path.read_text", return_value="Template: $full_name — $description")
    def test_generate_content_loads_template_and_calls_llm(self, mock_read, mock_config, mock_post):
        """Should load template file, format prompt, and call LLM."""
        from src.analyzer import generate_content

        mock_config.return_value = {
            "base_url": "https://api.test.com/v1",
            "api_key": "sk-test",
            "model": "test-model",
        }

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Generated content here."}}],
        }
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        repo = _make_scored_repo()
        result = generate_content(repo, "xiaohongshu")

        assert "Generated content here." == result
        # Verify template was read
        mock_read.assert_called_once()
        # Verify API was called
        mock_post.assert_called_once()

    @mock.patch("pathlib.Path.read_text", side_effect=FileNotFoundError)
    @mock.patch("src.analyzer.get_llm_config")
    def test_generate_content_handles_missing_template(self, mock_config, mock_read):
        """Should raise FileNotFoundError when template doesn't exist."""
        from src.analyzer import generate_content

        mock_config.return_value = {
            "base_url": "https://api.test.com/v1",
            "api_key": "sk-test",
            "model": "test-model",
        }

        repo = _make_scored_repo()
        with pytest.raises(FileNotFoundError):
            generate_content(repo, "nonexistent_template")

    @mock.patch("src.analyzer.requests.post")
    @mock.patch("src.analyzer.get_llm_config")
    @mock.patch("pathlib.Path.read_text", return_value="Deep analysis: $full_name")
    def test_generate_content_handles_api_error(self, mock_read, mock_config, mock_post):
        """Should return empty string on API error."""
        from src.analyzer import generate_content

        mock_config.return_value = {
            "base_url": "https://api.test.com/v1",
            "api_key": "sk-test",
            "model": "test-model",
        }
        mock_post.side_effect = Exception("Timeout")

        repo = _make_scored_repo()
        result = generate_content(repo, "deep_analysis")

        assert result == ""
