# STATUS — Posnet

**Cari faza:** AI-0 (BOOTSTRAP)
**Cari task:** AI-0.8 (GitHub Actions CI — workflow faylları; GitHub push-da işləyəcək)
**Son commit:** `cdaf54e` — feat(infra): AI-0.5 dev infra (mailpit, minio, caddy)
**Son uğurlu verify:** 2026-06-01; AI-0.6 frontend tooling işlək (lint + typecheck + Vite build ✅)
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
- [x] **AI-0.1** — Monorepo skeleton + Git init — 2026-06-01
- [x] **AI-0.2** — Python tooling (pyproject + Makefile + pre-commit; ADR-0010 CVE) — 2026-06-01
- [x] **AI-0.3** — Docker backend (postgres+pgmq, redis, vault, keycloak) — `adapter_*` konteynerlər — 2026-06-01
- [x] **AI-0.4** — Observability (otel, jaeger, prometheus, loki, grafana); OTLP→Jaeger E2E ✅ — 2026-06-01
- [x] **AI-0.5** — Dev infra (mailpit, minio + bucket-lar, caddy daxili-TLS) — 2026-06-01
- [x] **AI-0.6** — Frontend tooling — 2026-06-01
  - `pnpm-workspace.yaml` + root `package.json` (eslint 9 flat, prettier, tsconfig.base)
  - **`apps/admin-web`** — Vite + React 18 + TS skeleton (hub merchant paneli; real impl AI-2.7)
  - `apps/storefront` ❄️ frozen (ADR-0012); husky yox (pre-commit var)
  - Acceptance ✅: `pnpm install` · `pnpm -r lint` təmiz · `pnpm -r typecheck` təmiz · **Vite build keçdi**

## İcrada
- [ ] **AI-0.8** — GitHub Actions CI (lint + test + security + build workflow-ları)
  - Faylları yazıram (`.github/workflows/`); **GitHub-da yalnız push-dan sonra işləyəcək** (remote yox)

## Növbəti (FAZA AI-0 qalan — AI-ROADMAP.md §14)
- [ ] AI-0.7 — Flutter tooling skeleton — ⏸️ **TƏXİRƏ SALINDI** (gec OK; hub marketplace-first MVP-də kassir app sonra)
- [ ] AI-0.9 — ADR + Runbook templates (ADR-0010/0011/0012 artıq mövcuddur)
- [ ] AI-0.10 — CLAUDE.md tamamla (hub modelinə uyğunlaşdırıldı ✅)
- [ ] AI-0.11 — Smoke test: `make bootstrap`

## Açıq Suallar (İnsan üçün)
(yox)

## Bloklar / Həll olunmuş
- ✅ Git identity · Python 3.12.12 (uv) · make 3.81 · Docker Desktop v29.4.3 · **node v24.8 + pnpm 10.18**
- ✅ **İki ayrı posnet layihəsi:** bu = `adapter_*`; `posnet-help-center` = `posnet_*` (toxunma)
- ✅ **Port toqquşmaları həll:** keycloak mgmt 9100, minio console 9101, caddy 8443
- ✅ **pnpm 10 esbuild build script** icazələndi (`pnpm.onlyBuiltDependencies`)
- ⏳ **CVE remediation** (ADR-0010): 3 CVE müvəqqəti ignored — Faza AI-7 G7 gate-də məcburi həll

## Gate vəziyyəti
- G0 (Bootstrap): ⏳ Faza AI-0 sonu (**6/11** task tamamlanıb)
- G1 (Foundation): planlandı — eventbus/outbox prioritet (hub onurğası)
- G2 (POS Core): planlandı — canonical model "hub-a hazır"
- **AI-2.5 (Adapter framework + 1 kanal):** 🆕 ADR-0012 — MVP-yə daxil (mock→real Birmarket)
- **G-V (Validasiya):** ADR-0012 — "online çıxış" dilimini retail satıcıya demo (kill/continue)
- G3-G6, G7, G8: ❄️ təxirdə (G-V sonrası); G7-də ADR-0010 starlette CVE məcburi

---

## Preflight Checklist (İnsan)
- [x] Python 3.12.12 (uv) · uv · make 3.81 · Docker Desktop v29.4.3 · **node v24.8 + pnpm 10.18** ✅
- [x] ~~mkcert~~ — lazım deyil (Caddy daxili-CA TLS)
- [ ] Flutter 3.24+ + fvm (AI-0.7 — təxirdə, gec OK)
- [ ] GitHub hesabı + private org + SSH key + remote (AI-0.8 işləməsi üçün)
- [ ] VS Code + Claude Code extension hazır

---

## Endpointlər (lokal dev — `make up` sonrası)

| Servis | Ünvan | Giriş |
|---|---|---|
| Postgres+pgmq | `localhost:5432` | posnet / posnet_dev_pw / posnet_core |
| Redis | `localhost:6379` | — |
| Vault | `localhost:8200` | token `dev-root-token` |
| Keycloak | `localhost:8080` (`:9100/health`) | admin / admin |
| Jaeger | `localhost:16686` | — |
| Prometheus | `localhost:9090` | — |
| Grafana | `localhost:3000` | admin / admin |
| Loki | `localhost:3100` | — |
| OTLP | `localhost:4317` (gRPC), `4318` (HTTP) | — |
| Mailpit | `localhost:8025` (UI), `:1025` (SMTP) | — |
| MinIO | `localhost:9000` (S3), `:9101` (console) | minioadmin / minioadmin |
| Caddy (TLS) | `https://localhost:8443` | daxili CA |
| admin-web (dev) | `pnpm --filter @posnet/admin-web dev` → `:5173` | — |

---

## CVE Status (ADR-0010 → docs/adr/0010-cve-exceptions.md)

| CVE | Paket | Status | Plan |
|---|---|---|---|
| CVE-2026-32274 | black | ✅ Düzəldildi (26.3.1+) | — |
| CVE-2025-71176 | pytest | ⏳ Ignored | schemathesis 4.x stable çıxdıqda pytest>=9.0.3 |
| CVE-2025-62727 | starlette | ⏳ Ignored | **G7 gate-də MƏCBURİ** |
| PYSEC-2026-161 | starlette | ⏳ Ignored | **G7 gate-də MƏCBURİ** |
