"""Tests for CI/CD constraints — .gitignore coverage, GitHub Actions workflow.

Phase 13: Ensure operational safety — no secrets committed, no generated
content in repo, CI runs all quality checks.
"""
from pathlib import Path


def _get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_gitignore() -> set[str]:
    gitignore_path = _get_project_root() / ".gitignore"
    if not gitignore_path.exists():
        return set()
    lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    patterns = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.add(stripped)
    return patterns


# ── .gitignore Coverage ─────────────────────────────────────────────────

class TestGitignoreCoverage:
    """Critical paths must be gitignored to prevent accidental commits."""

    def test_env_is_gitignored(self):
        """.env 在 .gitignore 中."""
        patterns = _read_gitignore()
        assert ".env" in patterns, f".env must be in .gitignore, got: {patterns}"

    def test_content_packs_are_gitignored(self):
        """data/content_packs/ 在 .gitignore 中."""
        patterns = _read_gitignore()
        assert "data/content_packs/" in patterns, \
            f"data/content_packs/ must be in .gitignore"

    def test_reports_are_gitignored(self):
        """data/reports/ 在 .gitignore 中."""
        patterns = _read_gitignore()
        assert "data/reports/" in patterns, \
            f"data/reports/ must be in .gitignore"

    def test_cache_is_gitignored(self):
        """data/cache/ 在 .gitignore 中."""
        patterns = _read_gitignore()
        assert "data/cache/" in patterns, \
            f"data/cache/ must be in .gitignore"

    def test_env_example_is_not_gitignored(self):
        """.env.example 不应被 gitignore."""
        patterns = _read_gitignore()
        assert "!.env.example" in patterns or ".env.example" not in patterns, \
            ".env.example must be committable (template file)"


# ── GitHub Actions Workflow ─────────────────────────────────────────────

class TestGitHubActionsWorkflow:
    """CI workflow must include quality checks."""

    def test_workflow_file_exists(self):
        """.github/workflows/daily.yml 存在."""
        wf_path = _get_project_root() / ".github" / "workflows" / "daily.yml"
        assert wf_path.exists(), f"Workflow file not found: {wf_path}"

    def test_workflow_has_pytest(self):
        """workflow 包含 pytest tests/ -v."""
        wf_path = _get_project_root() / ".github" / "workflows" / "daily.yml"
        content = wf_path.read_text(encoding="utf-8")
        assert "pytest" in content, \
            f"Workflow must include pytest step, got:\n{content[:500]}"

    def test_workflow_has_doctor(self):
        """workflow 包含 python run.py doctor."""
        wf_path = _get_project_root() / ".github" / "workflows" / "daily.yml"
        content = wf_path.read_text(encoding="utf-8")
        assert "doctor" in content, \
            f"Workflow must include doctor step, got:\n{content[:500]}"

    def test_workflow_has_quality_gate(self):
        """workflow 包含 python run.py quality-gate."""
        wf_path = _get_project_root() / ".github" / "workflows" / "daily.yml"
        content = wf_path.read_text(encoding="utf-8")
        assert "quality-gate" in content or "quality_gate" in content, \
            f"Workflow must include quality-gate step, got:\n{content[:500]}"

    def test_workflow_has_benchmark(self):
        """workflow 包含 python run.py benchmark."""
        wf_path = _get_project_root() / ".github" / "workflows" / "daily.yml"
        content = wf_path.read_text(encoding="utf-8")
        assert "benchmark" in content, \
            f"Workflow must include benchmark step, got:\n{content[:500]}"


# ── Data Directory Safety ───────────────────────────────────────────────

class TestDataDirectorySafety:
    """Generated data directories must not be tracked by git."""

    def test_content_packs_not_tracked(self):
        """data/content_packs/ 不应有已跟踪文件."""
        import subprocess
        root = _get_project_root()
        result = subprocess.run(
            ["git", "ls-files", "data/content_packs/"],
            cwd=str(root), capture_output=True, text=True
        )
        tracked = result.stdout.strip()
        assert tracked == "", \
            f"data/content_packs/ must have no tracked files, got: {tracked}"

    def test_reports_not_tracked(self):
        """data/reports/ 不应有已跟踪文件."""
        import subprocess
        root = _get_project_root()
        result = subprocess.run(
            ["git", "ls-files", "data/reports/"],
            cwd=str(root), capture_output=True, text=True
        )
        tracked = result.stdout.strip()
        assert tracked == "", \
            f"data/reports/ must have no tracked files, got: {tracked}"

    def test_cache_not_tracked(self):
        """data/cache/ 不应有已跟踪文件."""
        import subprocess
        root = _get_project_root()
        result = subprocess.run(
            ["git", "ls-files", "data/cache/"],
            cwd=str(root), capture_output=True, text=True
        )
        tracked = result.stdout.strip()
        assert tracked == "", \
            f"data/cache/ must have no tracked files, got: {tracked}"

    def test_env_not_tracked(self):
        """.env 不应被 git 跟踪."""
        import subprocess
        root = _get_project_root()
        result = subprocess.run(
            ["git", "ls-files", ".env"],
            cwd=str(root), capture_output=True, text=True
        )
        tracked = result.stdout.strip()
        assert tracked == "", \
            ".env must not be tracked by git"

    def test_publish_packs_not_tracked(self):
        """data/publish_packs/ 不应有已跟踪文件."""
        import subprocess
        root = _get_project_root()
        result = subprocess.run(
            ["git", "ls-files", "data/publish_packs/"],
            cwd=str(root), capture_output=True, text=True
        )
        tracked = result.stdout.strip()
        assert tracked == "", \
            f"data/publish_packs/ must have no tracked files, got: {tracked}"


# ── Phase 19: CLI Command Registration ─────────────────────────────────

class TestPublishFlowCommand:
    """Verify Phase 19 publish-flow subcommand is registered."""

    def test_publish_flow_command_exists(self):
        """publish-flow should be a registered subcommand."""
        from src.main import build_parser

        parser = build_parser()
        subcommands = []
        for action in parser._actions:
            if getattr(action, 'choices', None) is not None:
                subcommands = list(action.choices.keys())
                break

        assert "publish-flow" in subcommands
