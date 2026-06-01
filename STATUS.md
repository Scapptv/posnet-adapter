# STATUS — Posnet

**Cari faza:** AI-0 (BOOTSTRAP)
**Cari task:** AI-0.2 (Python tooling — pyproject + Makefile + pre-commit)
**Son commit:** `0a290ad` — chore: ilkin monorepo strukturu (AI-0.1)
**Son uğurlu verify:** 2026-06-01 (AI-0.1 acceptance: git status clean ✅, qovluq strukturu ✅)
**Vəziyyət:** IN_PROGRESS

---

## Tamamlanmış task-lar
- [x] **AI-0.1** — Monorepo skeleton + Git init (commit: `0a290ad`) — 2026-06-01
  - 58 fayl yaradıldı: services/ libs/ apps/ mocks/ infra/ tests/ docs/ scripts/ .github/
  - .gitignore (Python + Node + Flutter + Docker + Terraform + secrets)
  - README.md skeleton
  - git init -b main + first commit

## İcrada
- [ ] **AI-0.2** — Python tooling: pyproject.toml + Makefile + pre-commit + detect-secrets baseline
  - Planlandı, başlanmayıb

## Növbəti (FAZA AI-0 qalan — AI-ROADMAP.md §19)
- [ ] AI-0.3 — Docker stack: backend (postgres, redis, vault, keycloak)
- [ ] AI-0.4 — Docker stack: observability (jaeger, prometheus, grafana, loki, otel-collector)
- [ ] AI-0.5 — Docker stack: dev infra (mailpit, minio, caddy + mkcert TLS)
- [ ] AI-0.6 — Frontend tooling (Node + pnpm workspace)
- [ ] AI-0.7 — Flutter tooling skeleton (preflight Flutter quraşdırılmasa təxir et)
- [ ] AI-0.8 — GitHub Actions CI (lint + test + security + build)
- [ ] AI-0.9 — ADR + Runbook templates + ilk 3 ADR
- [ ] AI-0.10 — CLAUDE.md tamamla (artıq v1.1 mövcuddur — qiymətləndir, lazımdırsa əlavə et)
- [ ] AI-0.11 — Smoke test: `make bootstrap`

## Açıq Suallar (İnsan üçün)
(yox)

## Bloklar
**Mini-bloklar (insan həll etdi):**
- ✅ Git identity qurulması — `huseyn.ceferov93@gmail.com` / `Huseyn` (lokal repo, 2026-06-01)

## Gate vəziyyəti
- G0 (Bootstrap): ⏳ Faza AI-0 sonu (11/1 task tamamlanıb)
- G1 (Foundation): planlandı
- G2-G8: planlandı

---

## Preflight Checklist (İnsan — bu yenidən aktiv olur AI-0.2/0.3 başlayanda)
- [ ] GitHub hesabı + private organization yaradıldı (AI-0.8 öncəsi)
- [ ] Docker Desktop quraşdırıldı və `docker info` işləyir (AI-0.3 öncəsi)
- [ ] Python 3.12 quraşdırıldı (AI-0.2 commit hook üçün)
- [ ] Node.js 20 LTS quraşdırıldı (AI-0.6 öncəsi)
- [ ] Flutter 3.24+ (AI-0.7 öncəsi — gec mərhələdə də OK)
- [ ] uv (`pip install uv`) opsional, AI-0.2-də işlədilir
- [ ] mkcert + `mkcert -install` (AI-0.5 öncəsi)
- [ ] VS Code + Claude Code extension hazır
- [ ] SSH key GitHub-a əlavə (AI-0.8 üçün)
