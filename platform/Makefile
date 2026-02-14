PYTHON ?= python
DOCKER_COMPOSE ?= $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; elif command -v docker-compose >/dev/null 2>&1; then echo "docker-compose"; else echo "docker compose"; fi)

.PHONY: dev run test test-cov lint format docker-build docker-up docker-up-dev docker-down docker-logs db-shell deploy rollback backup health-check

dev:
	streamlit run app.py --server.port=8501 --server.runOnSave=true

run:
	streamlit run app.py --server.port=8501 --server.headless=true

docker-build:
	$(DOCKER_COMPOSE) build

docker-up:
	$(DOCKER_COMPOSE) up -d

docker-up-dev:
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml up

docker-down:
	$(DOCKER_COMPOSE) down

docker-logs:
	$(DOCKER_COMPOSE) logs -f app

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

test-cov:
	$(PYTHON) -m pytest tests/ -v --cov=services --cov=modules --cov-report=html

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

db-shell:
	$(PYTHON) -c "import os, duckdb; db=os.getenv('UNIFIED_DB_PATH','databases/plant_registry.duckdb'); print(f'Opening {db}'); duckdb.connect(db).execute('SHOW TABLES').fetchall()"

deploy:
	./scripts/deploy.sh

rollback:
	@read -p "Backup dir: " dir; ./scripts/rollback.sh $$dir

backup:
	./scripts/backup_db.sh

health-check:
	./scripts/health_check.sh
