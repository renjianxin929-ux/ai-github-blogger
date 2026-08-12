# AI GitHub Blogger

> An open-source AI workflow for discovering, evaluating, and transforming GitHub projects into structured research and multi-platform content.

AI GitHub Blogger helps creators and research teams turn the daily stream of AI, LLM, and agent projects on GitHub into a repeatable, reviewable content workflow.

## Why this project

Finding worthwhile projects is only the first step. This project combines repository discovery, transparent scoring, LLM-assisted analysis, quality gates, and human review so content decisions can be reproduced and checked before publication.

## Features

- GitHub repository discovery through Trending RSS and the REST API
- Multi-dimensional repository scoring for stars, activity, relevance, README quality, community health, and licensing
- LLM-powered FDE analysis of functionality, differentiation, and ecosystem value
- Human-in-the-loop review queues and safety checks
- Quality gates, risk review, deduplication, and reproducible reports
- Multi-platform content-package generation
- GitHub Actions automation for tests and daily runs

## Quick start

### 1. Clone the repository

    git clone https://github.com/renjianxin929-ux/ai-github-blogger.git
    cd ai-github-blogger

### 2. Install dependencies

    pip install -r requirements.txt

### 3. Configure environment variables

    cp .env.example .env

Edit .env and add a GitHub token plus an LLM API key. See .env.example for the supported configuration.

### 4. Run a workflow

    # Daily workflow: environment checks, topic discovery, and quality checks
    python run.py daily-workflow

    # End-to-end validation without LLM tokens or content packages
    python run.py dry-run

    # View the human review queue
    python run.py review-queue

## Common commands

    # Full daily pipeline
    python run.py daily

    # Score and report without LLM analysis
    python run.py daily --no-llm

    # Create an 11-file content package for a repository
    python run.py content owner/repo

    # Environment health check, quality gate, and scoring benchmark
    python run.py doctor
    python run.py quality-gate
    python run.py benchmark

## Project structure

    ai-github-blogger/
    ├── .github/workflows/daily.yml  # Tests and scheduled workflow
    ├── src/                         # CLI, discovery, scoring, analysis, and review
    ├── templates/                   # LLM prompt templates
    ├── tests/                       # Unit tests
    ├── docs/                        # Workflow and operational documentation
    ├── data/                        # State and generated outputs
    ├── requirements.txt
    ├── .env.example
    └── run.py

## Testing

    pytest tests/ -v

## GitHub Actions

The workflow runs daily at 08:00 China Standard Time and can also be triggered manually. Configure GH_TOKEN, LLM_API_KEY, LLM_API_BASE, and LLM_MODEL as GitHub Actions Secrets before a scheduled run.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and pull-request guidance.

## Security

See [SECURITY.md](SECURITY.md) for responsible vulnerability reporting and credential-handling guidance.

## License

This project is released under the [MIT License](LICENSE).
