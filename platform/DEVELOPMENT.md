# Development Setup

## Prerequisites

- Python 3.12+
- Docker Desktop (or Docker Engine + Compose plugin)
- Git

## Quick Start

1. Create and activate a virtual environment:

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-cov ruff mypy pre-commit
   ```

3. Configure environment:

   ```bash
   cp .env.example .env
   # Add required API keys in .env
   ```

4. Run locally:

   ```bash
   make dev
   ```

5. Run with Docker Compose:

   ```bash
   docker compose up -d
   ```

## Common Commands

| Task | Command |
|------|---------|
| Run app (dev) | `make dev` |
| Run app (headless) | `make run` |
| Run tests | `make test` |
| Run tests with coverage | `make test-cov` |
| Lint | `make lint` |
| Format | `make format` |
| Docker build | `make docker-build` |
| Docker up | `make docker-up` |
| Docker up (dev overrides) | `make docker-up-dev` |
| Docker logs | `make docker-logs` |
| Docker down | `make docker-down` |

## Notes

- The default app URL is http://localhost:8501
- Redis is included in Docker Compose for optional caching/background infrastructure.
- Weekly automation workflows are intentionally unchanged.
