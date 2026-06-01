# STATUS — Posnet

**Cari faza:** AI-0 (BOOTSTRAP)
**Cari task:** AI-0.3 (Docker stack: backend — postgres, redis, vault, keycloak)
**Son commit:** `67bc8e1` — chore: Python tooling — pyproject + Makefile + pre-commit (AI-0.2)
**Son uğurlu verify:** 2026-06-01 (ruff ✅, mypy ✅, bandit ✅, uv sync ✅)
**Vəziyyət:** IN_PROGRESS

---

## Tamamlanmış task-lar
- [x] **AI-0.1** — Monorepo skeleton + Git init (commit: `0a290ad`) — 2026-06-01
  - 58 fayl: services/ libs/ apps/ mocks/ infra/ tests/ docs/ scripts/ .github/
  - .gitignore, README.md, git init -b main, first commit
- [x] **AI-0.2** — Python tooling (commit: `67bc8e1`) — 2026-06-01
  - pyproject.toml (50+ runtime + dev deps, ruff/mypy/pytest/bandit configs)
  - Makefile (20+ target: bootstrap, verify, lint, type, test, format, security, up/down, migrate, seed, backup, smoke, load, clean)
  - .pre-commit-config.yaml (ruff, mypy, bandit, detect-secrets, yamllint, conventional-commits)
  - .yamllint.yml, .env.example, .secrets.baseline (detect-secrets ilkin scan)
  - .python-version = 3.12 (uv project python pin)
  - uv.lock (2828 sətir deterministic)
  - libs/canonical_model + libs/feature_flags (snake_case Python paket)
  - services/-də Docker-svc qovluqlarından `__init__.py` silindi

## İcrada
- [ ] **AI-0.3** — Docker stack: backend (postgres 16-alpine, redis 7-alpine, vault dev mode, keycloak 25.x)
  - Planlandı, başlanmayıb
  - **Preflight tələbi:** Docker Desktop quraşdırılmış və `docker info` işləyir

## Növbəti (FAZA AI-0 qalan — AI-ROADMAP.md §19)
- [ ] AI-0.4 — Docker stack: observability (jaeger, prometheus, grafana, loki, otel-collector)
- [ ] AI-0.5 — Docker stack: dev infra (mailpit, minio, caddy + mkcert TLS)
- [ ] AI-0.6 — Frontend tooling (Node + pnpm workspace + shared eslint/prettier)
- [ ] AI-0.7 — Flutter tooling skeleton (preflight: Flutter 3.24+ quraşdırılmalı — gec mərhələdə də OK)
- [ ] AI-0.8 — GitHub Actions CI (lint + test + security + build)
- [ ] AI-0.9 — ADR + Runbook templates + ilk 3 ADR (stack, monorepo, secrets)
- [ ] AI-0.10 — CLAUDE.md tamamla (v1.1 mövcuddur — qiymətləndir)
- [ ] AI-0.11 — Smoke test: `make bootstrap`

## Açıq Suallar (İnsan üçün)
(yox)

## Bloklar
- ✅ Həll olundu: Git identity (`huseyn.ceferov93@gmail.com` / `Huseyn` lokal repo, 2026-06-01)
- ✅ Həll olundu: Python 3.12 sistemdə yox idi → `uv python install 3.12` ilə 3.12.12 quraşdırıldı (2026-06-01)
- ✅ Həll olundu: Python paket adları tire qadağası → libs snake_case, services hyphen saxlanılır (Docker service)

## Gate vəziyyəti
- G0 (Bootstrap): ⏳ Faza AI-0 sonu (2/11 task tamamlanıb)
- G1 (Foundation): planlandı
- G2-G8: planlandı

---

## Preflight Checklist (İnsan)
- [ ] Docker Desktop quraşdırıldı və `docker info` işləyir **(AI-0.3 üçün KRİTİK — növbəti task)**
- [x] Python 3.12.12 quraşdırıldı (uv vasitəsi ilə — 2026-06-01)
- [x] uv quraşdırıldı (sistem)
- [ ] Node.js 20 LTS (AI-0.6 öncəsi)
- [ ] Flutter 3.24+ + fvm (AI-0.7 öncəsi — gec OK)
- [ ] mkcert + `mkcert -install` (AI-0.5 öncəsi)
- [ ] GitHub hesabı + private organization (AI-0.8 öncəsi)
- [ ] SSH key GitHub-a əlavə (AI-0.8 üçün)
- [ ] VS Code + Claude Code extension hazır
