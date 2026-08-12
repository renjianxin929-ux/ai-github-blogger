# Security Policy

## Reporting a vulnerability

Please do not disclose security vulnerabilities in public issues. Report them privately to the repository maintainer through the GitHub profile associated with this repository, including a clear description, reproduction steps, and potential impact.

We will acknowledge reports as soon as practical and coordinate a fix before public disclosure.

## Protecting credentials

Never commit API keys, GitHub tokens, or .env files. Use .env.example as a configuration reference and store production secrets in GitHub Actions Secrets or another appropriate secret manager.
