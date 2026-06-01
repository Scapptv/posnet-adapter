# STATUS — Posnet

**Cari faza:** AI-0 (BOOTSTRAP) — başlanmayıb
**Cari task:** AI-0.1 (Qovluq strukturu + Git)
**Son commit:** (yox — git init hələ olunmayıb)
**Son uğurlu verify:** (yox)
**Vəziyyət:** READY_TO_START

---

## Tamamlanmış task-lar
(yox)

## İcrada
(yox — sessiya başladıqda AI-0.1 götürür)

## Növbəti (FAZA AI-0 — 11 task, AI-ROADMAP.md §10)
- [ ] AI-0.1 — Monorepo skeleton + Git init + `*.md` faylları `docs/phases/`-ə köçür
- [ ] AI-0.2 — Python tooling (pyproject + Makefile + pre-commit + detect-secrets baseline)
- [ ] AI-0.3 — Docker stack: backend (postgres, redis, vault, keycloak)
- [ ] AI-0.4 — Docker stack: observability (jaeger, prometheus, grafana, loki, otel-collector)
- [ ] AI-0.5 — Docker stack: dev infra (mailpit, minio, caddy + mkcert TLS)
- [ ] AI-0.6 — Frontend tooling (Node + pnpm workspace + shared eslint/prettier)
- [ ] AI-0.7 — Flutter tooling skeleton (apps/pos-flutter/)
- [ ] AI-0.8 — GitHub Actions CI (lint + test + security + build)
- [ ] AI-0.9 — ADR + Runbook templates + ilk 3 ADR (stack, monorepo, secrets)
- [ ] AI-0.10 — CLAUDE.md tamamla (skeleton mövcuddur)
- [ ] AI-0.11 — Smoke test: `make bootstrap`

## Açıq Suallar (İnsan üçün)
(yox)

## Bloklar
(yox)

## Gate vəziyyəti
- G0 (Bootstrap): ⏳ Faza AI-0 sonu
- G1 (Foundation): planlandı
- G2-G8: planlandı

---

## Preflight Checklist (İnsan — başlamadan əvvəl)
- [ ] GitHub hesabı + private organization yaradıldı
- [ ] Docker Desktop quraşdırıldı və `docker info` işləyir
- [ ] Python 3.12 quraşdırıldı (`python --version` → 3.12.x)
- [ ] Node.js 20 LTS quraşdırıldı (`node --version`)
- [ ] Flutter 3.24+ quraşdırıldı (Faza AI-2-yə qədər gözləyə bilər)
- [ ] uv quraşdırıldı (`uv --version`) — opsional, pip də işləyər
- [ ] VS Code + Claude Code extension hazır
- [ ] SSH key GitHub-a əlavə edildi
- [ ] (Vault root token, Keycloak admin password gələcəkdə Vault qurulduqda offline saxlanılacaq)

**Hamısı işarələnəndə:** AI sessiya başlat və əmr ver:
> "STATUS.md və AI-ROADMAP.md oxu. Faza AI-0 Task AI-0.1-dən başla."
