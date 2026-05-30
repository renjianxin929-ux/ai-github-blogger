"""Tests for main.py — CLI argument parsing and pipeline orchestration."""
import sys
from unittest import mock

import pytest


class TestCLIArgs:
    """Test CLI argument parsing."""

    def test_daily_subcommand(self):
        """python -m src.main daily should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["daily"])
        assert args.command == "daily"
        assert args.no_llm is False

    def test_daily_no_llm_flag(self):
        """--no-llm flag should be parsed."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["daily", "--no-llm"])
        assert args.no_llm is True

    def test_fetch_subcommand(self):
        """python -m src.main fetch should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["fetch"])
        assert args.command == "fetch"

    def test_score_subcommand(self):
        """python -m src.main score should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["score"])
        assert args.command == "score"

    def test_report_subcommand(self):
        """python -m src.main report should be recognized."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["report"])
        assert args.command == "report"

    def test_content_subcommand_with_repo(self):
        """python -m src.main content owner/repo should parse repo arg."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["content", "test/awesome-repo"])
        assert args.command == "content"
        assert args.repo == "test/awesome-repo"

    def test_content_subcommand_requires_repo(self):
        """content subcommand without repo should raise."""
        from src.main import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["content"])

    def test_default_command_is_daily(self):
        """No arguments should default to daily."""
        from src.main import build_parser

        parser = build_parser()
        args = parser.parse_args([])
        assert args.command == "daily"
