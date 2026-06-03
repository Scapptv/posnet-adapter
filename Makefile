SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# ---- Configuration ----
UV ?= uv
PYTHON := $(UV) run python
PYTEST := $(UV) run pytest
RUFF := $(UV) run ruff
MYPY := $(UV) run mypy
BLACK := $(UV) run black
BANDIT := $(UV) run bandit
PIP_AUDIT := $(UV) run pip-audit
DETECT_SECRETS := $(UV) run detect-secrets
PRE_COMMIT := $(UV) run pre-commit

COMPOSE := docker compose
COMPOSE_FILE := docker-compose.yml

# ANSI colors
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
RESET := \033[0m

.PHONY: help
help: ## Bütün hədəfləri göstər
	@printf "$(CYAN)Posnet — Mövcud əmrlər$(RESET)\n\n"
	@printf "$(YELLOW)Setup:$(RESET)\n"
	@printf "  make install         Dev deps + pre-commit hook\n"
	@printf "  make bootstrap       İlk dəfə tam setup (install + up + verify)\n\n"
	@printf "$(YELLOW)Quality:$(RESET)\n"
	@printf "  make verify          lint + type + test + security (CI ekvivalenti)\n"
	@printf "  make lint            ruff + black --check\n"
	@printf "  make type            mypy --strict\n"
	@printf "  make test            pytest + coverage (80% gate)\n"
	@printf "  make security        bandit + pip-audit + detect-secrets\n"
	@printf "  make format          ruff format + isort\n\n"
	@printf "$(YELLOW)Docker:$(RESET)\n"
	@printf "  make up              docker-compose up -d\n"
	@printf "  make down            docker-compose down\n"
	@printf "  make logs            docker-compose logs -f\n"
	@printf "  make ps              docker-compose ps\n\n"
	@printf "$(YELLOW)Database:$(RESET)\n"
	@printf "  make migrate         alembic upgrade head\n"
	@printf "  make migrate-down    alembic downgrade -1\n"
	@printf "  make seed            Test data seed\n"
	@printf "  make backup          pg_dump → MinIO\n\n"
	@printf "$(YELLOW)Test specials:$(RESET)\n"
	@printf "  make smoke           Faza-spesifik smoke test\n"
	@printf "  make load            k6 load test (AI-4+)\n"
	@printf "  make test PATTERN=x  Yalnız 'x' adlı testlər\n\n"
	@printf "$(YELLOW)Utility:$(RESET)\n"
	@printf "  make clean           Cache + build artifacts sil\n"
	@printf "  make pre-commit      pre-commit run --all-files\n"

# ---- Setup ----
.PHONY: install
install: ## Dev dependencies quraşdır
	$(UV) sync --all-extras
	$(PRE_COMMIT) install

.PHONY: bootstrap
bootstrap: install up wait-healthy verify ## İlk dəfə tam setup
	@printf "$(GREEN)✓ Bootstrap done$(RESET)\n"

.PHONY: wait-healthy
wait-healthy:
	@printf "$(YELLOW)Servislər healthy olana qədər gözləyirik (30s)...$(RESET)\n"
	@sleep 30
	@$(COMPOSE) ps

# ---- Quality ----
# `test` AI-2.H3-də verify-ə əlavə olundu (audit A5): coverage-paint əleyhinə —
# verify lokal CI ekvivalentidir, suite (real DB + RLS) hər dəfə icra olunmalıdır.
.PHONY: verify
verify: lint type test security ## CI ekvivalenti (lint + type + test + security)
	@printf "$(GREEN)✓ All checks passed$(RESET)\n"

.PHONY: lint
lint: ## Ruff + black --check
	$(RUFF) check .
	$(RUFF) format --check .

.PHONY: type
type: ## mypy --strict
	$(MYPY) services libs

.PHONY: test
test: ## pytest + coverage
ifdef PATTERN
	$(PYTEST) -k "$(PATTERN)" -v
else
	$(PYTEST)
endif

.PHONY: format
format: ## ruff format + import sort
	$(RUFF) check --fix .
	$(RUFF) format .

.PHONY: security
security: ## bandit + pip-audit + detect-secrets
	$(BANDIT) -r services libs -c pyproject.toml -q
	$(PIP_AUDIT) --skip-editable \
		--ignore-vuln CVE-2025-71176 \
		--ignore-vuln CVE-2025-62727 \
		--ignore-vuln PYSEC-2026-161
	$(DETECT_SECRETS) scan --baseline .secrets.baseline

# Ignored vulnerabilities (CVE rasionalı — detail: docs/adr/0010-cve-exceptions.md):
#   CVE-2025-71176 (pytest):
#     - Fix in pytest 9.0.3; schemathesis 3.x stable pytest<9 tələb edir
#     - Risk: aşağı (test framework, prod-da yox)
#     - Plan: schemathesis 4.x stable çıxdıqda pytest>=9.0.3-ə yenilə
#   CVE-2025-62727, PYSEC-2026-161 (starlette):
#     - Fix in starlette 1.0.1; FastAPI/schemathesis/instrumentator hələ
#       starlette 1.0+ tam dəstəkləmir
#     - Risk: orta (web framework prod-da işləyir)
#     - Plan: Faza AI-7 prod-deploy ÖNCƏSİ məcburi həll (G7 gate kriteriya)

.PHONY: pre-commit
pre-commit: ## pre-commit hook-ları işlət
	$(PRE_COMMIT) run --all-files

# ---- Docker ----
.PHONY: up
up: ## docker-compose up -d
	$(COMPOSE) up -d

.PHONY: down
down: ## docker-compose down
	$(COMPOSE) down

.PHONY: logs
logs: ## docker-compose logs -f
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## docker-compose ps
	$(COMPOSE) ps

# ---- Database ----
.PHONY: migrate
migrate: ## alembic upgrade head
	cd services/core && $(UV) run alembic upgrade head

.PHONY: migrate-down
migrate-down: ## alembic downgrade -1
	cd services/core && $(UV) run alembic downgrade -1

.PHONY: seed
seed: ## Test data seed
	$(PYTHON) scripts/seed_data.py

.PHONY: backup
backup: ## DB backup (pg_dump → local + opsional MinIO/S3)
	$(PYTHON) scripts/db_backup.py

# ---- Smoke / Load ----
.PHONY: smoke
smoke: ## Faza-spesifik smoke test
	$(PYTEST) -m smoke -v --no-cov

.PHONY: load
load: ## Load test (k6/locust)
	@echo "Load test Faza AI-4+ sonra mövcuddur"

# ---- Cleanup ----
.PHONY: clean
clean: ## Cache + artifacts sil
	find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type f -name "coverage.xml" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist
	@printf "$(GREEN)✓ Cleaned$(RESET)\n"
