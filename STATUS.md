# STATUS — Posnet

**Cari faza:** AI-0 (BOOTSTRAP)
**Cari task:** AI-0.4 (Docker stack: observability — jaeger, prometheus, grafana, loki, otel)
**Son commit:** `e32670f` — docs: AI-ROADMAP v4.0 + CLAUDE/README hub modelinə uyğunlaşdırıldı
**Son uğurlu verify:** 2026-06-01 (`make verify` exit 0); AI-0.3 stack healthy (4/4 servis)
**Vəziyyət:** IN_PROGRESS

---

## 🎯 STRATEGİYA (ADR-0012 — POS-anchored İnteqrasiya Hub)

**Məhsul:** POS-anchored omnichannel **inteqrasiya hub** (TSoft/Entegra/ChannelEngine modeli).
POS = tək həqiqət mənbəyi; hub məhsul/stok/qiyməti marketplace/delivery/booking-ə çıxarır.

- **Beachhead:** **Azərbaycan · pərakəndə (market/butik) · ilk kanal = Birmarket/Trendyol (marketplace)**
- **İlk MVP dilimi:** POS-da məhsul → Birmarket-ə listing → stok/qiymət sync → sifariş POS-a → stok hər yerdə azalır
- **Crown jewel:** adapter SDK + canonical model + sync engine (idempotency + reconciliation 1-ci gündən)
- **Paralel insan trekləri:** (1) retail satıcı müsahibələri · (2) **Birmarket/Trendyol seller API access** (partner gate, D-002)
- **AI build (blok deyil):** framework + **mock Birmarket adapter** → real credential gələndə swap

> 🔄 ADR-0011 dondurması incələşdirildi: adapter framework + 1 kanal artıq CORE (yeni task **AI-2.5**, MVP-yə daxil).
> Hələ təxirdə: 2-ci kanal, delivery & booking domain, fiskal, multi-country, cloud, TR.
> Detal: `docs/adr/0012-integration-hub-reframe.md`.

---

## Tamamlanmış task-lar
- [x] **AI-0.1** — Monorepo skeleton + Git init (commit: `0a290ad`) — 2026-06-01
  - 58 fayl: services/ libs/ apps/ mocks/ infra/ tests/ docs/ scripts/ .github/
- [x] **AI-0.2** — Python tooling (commit-lər: `67bc8e1`, `a25a339`, `b5a720d`) — 2026-06-01
  - pyproject.toml (50+ deps + tool configs), Makefile (21 target), .pre-commit (17 hook)
  - **CVE remediation:** black 26.x; pytest + starlette CVE müvəqqəti ignore + **ADR-0010**
- [x] **AI-0.3** — Docker stack: backend (postgres+pgmq, redis, vault, keycloak) — 2026-06-01
  - `docker-compose.yml` (name: **adapter**) + `infra/postgres/init.sql` + `infra/keycloak/realm-posnet.json`
  - **pgmq image düzəlişi:** `ghcr.io/pgmq/pg16-pgmq` (standart postgres-də pgmq YOXDUR)
  - Konteynerlər **`adapter_*`** (help-center `posnet_*`-dən AYRI; port 5432/6379/8200/8080/9100)
  - Acceptance ✅: 4/4 healthy · pgmq 1.11.1 + pg_trgm · vault unsealed (v1.15.6) · keycloak /health/ready 200 · redis PONG

## İcrada
- [ ] **AI-0.4** — Docker stack: observability (jaeger, prometheus, grafana, loki, otel-collector)
  - mövcud `docker-compose.yml`-ə əlavə + `infra/{prometheus,loki,otel,grafana}` config

## Növbəti (FAZA AI-0 qalan — AI-ROADMAP.md §14)
- [ ] AI-0.5 — Docker stack: dev infra (mailpit, minio, caddy + mkcert TLS)
- [ ] AI-0.6 — Frontend tooling (Node + pnpm workspace + shared eslint/prettier)
- [ ] AI-0.7 — Flutter tooling skeleton (preflight: Flutter 3.24+ — gec mərhələdə də OK)
- [ ] AI-0.8 — GitHub Actions CI (lint + test + security + build)
- [ ] AI-0.9 — ADR + Runbook templates (ADR-0010/0011/0012 artıq mövcuddur)
- [ ] AI-0.10 — CLAUDE.md tamamla (hub modelinə uyğunlaşdırıldı ✅)
- [ ] AI-0.11 — Smoke test: `make bootstrap`

## Açıq Suallar (İnsan üçün)
(yox)

## Bloklar / Həll olunmuş
- ✅ Git identity (`huseyn.ceferov93@gmail.com` / `Huseyn` lokal repo, 2026-06-01)
- ✅ Python 3.12.12 (uv vasitəsi ilə, 2026-06-01)
- ✅ **make Win11 quraşdırılması** (`winget install GnuWin32.Make`, 2026-06-01)
- ✅ **İki ayrı posnet layihəsi aydınlaşdırıldı:** bu layihə = `adapter_*` konteynerlər; `posnet-help-center` = `posnet_*` (pgvector+meili, toxunma)
- ⏳ **CVE remediation** (ADR-0010): 3 CVE müvəqqəti ignored — Faza AI-7 G7 gate-də məcburi həll

## Gate vəziyyəti
- G0 (Bootstrap): ⏳ Faza AI-0 sonu (**3/11** task tamamlanıb)
- G1 (Foundation): planlandı — eventbus/outbox prioritet (hub onurğası)
- G2 (POS Core): planlandı — canonical model "hub-a hazır"
- **AI-2.5 (Adapter framework + 1 kanal):** 🆕 ADR-0012 — MVP-yə daxil (mock→real Birmarket)
- **G-V (Validasiya):** ADR-0012 — "online çıxış" dilimini retail satıcıya demo (kill/continue)
- G3-G6, G7, G8: ❄️ təxirdə (G-V sonrası); G7-də ADR-0010 starlette CVE məcburi

---

## Preflight Checklist (İnsan)
- [x] Python 3.12.12 quraşdırıldı (uv 2026-06-01)
- [x] uv quraşdırıldı (sistem)
- [x] **make 3.81 quraşdırıldı** (winget GnuWin32, 2026-06-01)
- [x] **Docker Desktop işləyir** (v29.4.3 — AI-0.3 stack qaldırıldı ✅)
- [ ] Node.js 20 LTS (AI-0.6 öncəsi)
- [ ] Flutter 3.24+ + fvm (AI-0.7 öncəsi — gec OK)
- [ ] mkcert + `mkcert -install` (AI-0.5 öncəsi)
- [ ] GitHub hesabı + private organization (AI-0.8 öncəsi)
- [ ] SSH key GitHub-a əlavə (AI-0.8 üçün)
- [ ] VS Code + Claude Code extension hazır

---

## CVE Status (ADR-0010 → docs/adr/0010-cve-exceptions.md)

| CVE | Paket | Status | Plan |
|---|---|---|---|
| CVE-2026-32274 | black | ✅ Düzəldildi (26.3.1+) | — |
| CVE-2025-71176 | pytest | ⏳ Ignored | schemathesis 4.x stable çıxdıqda pytest>=9.0.3 |
| CVE-2025-62727 | starlette | ⏳ Ignored | **G7 gate-də MƏCBURİ** |
| PYSEC-2026-161 | starlette | ⏳ Ignored | **G7 gate-də MƏCBURİ** |
