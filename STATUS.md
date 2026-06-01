# STATUS — Posnet

**Cari faza:** AI-0 (BOOTSTRAP) — ✅ **TAMAMLANDI** (G0 təsdiq gözləyir)
**Cari task:** **G0 gate** (insan təsdiqi) → sonra **AI-1 (Foundation)**
**Son commit:** `43e631e` — ci: AI-0.8 GitHub Actions workflows
**Son uğurlu verify:** 2026-06-01; AI-0.11 bootstrap smoke yaşıl (12 servis up + verify)
**Vəziyyət:** AI-0 DONE — **G0 GÖZLƏYİR**

---

## 🎯 STRATEGİYA (ADR-0012 — POS-anchored İnteqrasiya Hub)

**Məhsul:** POS-anchored omnichannel **inteqrasiya hub** (TSoft/Entegra/ChannelEngine modeli).
POS = tək həqiqət mənbəyi; hub məhsul/stok/qiyməti marketplace/delivery/booking-ə çıxarır.

- **Beachhead:** **Azərbaycan · pərakəndə (market/butik) · ilk kanal = Birmarket/Trendyol (marketplace)**
- **İlk MVP dilimi:** POS-da məhsul → Birmarket-ə listing → stok/qiymət sync → sifariş POS-a → stok hər yerdə azalır
- **Crown jewel:** adapter SDK + canonical model + sync engine (idempotency + reconciliation 1-ci gündən)
- **Paralel insan trekləri:** (1) retail satıcı müsahibələri · (2) **Birmarket/Trendyol seller API access** (partner gate, D-002)
- **AI build (blok deyil):** framework + **mock Birmarket adapter** → real credential gələndə swap

> 🔄 ADR-0011 dondurması incələşdirildi: adapter framework + 1 kanal CORE (yeni task **AI-2.5**, MVP-yə daxil).
> Hələ təxirdə: 2-ci kanal, delivery & booking, fiskal, multi-country, cloud, TR. Detal: `docs/adr/0012-integration-hub-reframe.md`.

---

## Faza AI-0 — TAMAMLANDI (10/11; AI-0.7 təxirdə)

- [x] **AI-0.1** Monorepo skeleton + Git init
- [x] **AI-0.2** Python tooling (pyproject + Makefile + pre-commit; ADR-0010 CVE)
- [x] **AI-0.3** Docker backend (postgres+pgmq, redis, vault, keycloak) — `adapter_*`
- [x] **AI-0.4** Observability (otel, jaeger, prometheus, loki, grafana); OTLP→Jaeger E2E ✅
- [x] **AI-0.5** Dev infra (mailpit, minio + bucket-lar, caddy daxili-TLS)
- [x] **AI-0.6** Frontend tooling (pnpm workspace + admin-web Vite/React/TS; build ✅)
- [x] **AI-0.8** GitHub Actions CI (lint/test/security/build + CODEOWNERS; lokal CI-equivalent yaşıl)
- [x] **AI-0.9** ADR + Runbook şablonları + ADR-0001/0002/0003 (stack/monorepo/secrets)
- [x] **AI-0.10** CLAUDE.md tamamlandı (hub modeli, v1.2)
- [x] **AI-0.11** Bootstrap smoke (up + verify yaşıl)
- [ ] ~~AI-0.7~~ Flutter tooling — ⏸️ **TƏXİRDƏ** (gec OK; kassir app AI-2-də)

## İcrada
- **G0 gate** — insan təsdiqi gözləyir (HUMAN-GATES.md → G0 girişi). Təsdiqdən sonra → AI-1.

## Bloklar / Həll olunmuş
- ✅ Git identity · Python 3.12.12 (uv) · make 3.81 · Docker v29.4.3 · node v24.8 + pnpm 10.18
- ✅ **İki ayrı posnet layihəsi:** bu = `adapter_*`; `posnet-help-center` = `posnet_*` (toxunma)
- ✅ **Port toqquşmaları:** keycloak mgmt 9100, minio console 9101, caddy 8443
- ✅ **pytest cov no-data** (CovReportWarning) düzəldildi — `filterwarnings` ignore
- ⏳ **GitHub remote/repo** — AI-0.8 CI-nin işləməsi üçün insan qurmalıdır (G0 təsdiqindən sonra da OK)
- ⏳ **CVE remediation** (ADR-0010): 3 CVE ignored — Faza AI-7 G7 gate-də məcburi

## Gate vəziyyəti
- **G0 (Bootstrap): 🟡 TƏSDİQ GÖZLƏYİR** (10/11 task; AI-0.7 təxirdə)
- G1 (Foundation): növbəti — eventbus/outbox prioritet (hub onurğası)
- G2 (POS Core): canonical model "hub-a hazır"
- **AI-2.5 (Adapter framework + 1 kanal):** ADR-0012 — MVP-yə daxil (mock→real Birmarket)
- **G-V (Validasiya):** ADR-0012 — "online çıxış" dilimini retail satıcıya demo
- G3-G8: ❄️ təxirdə (G-V sonrası); G7-də ADR-0010 starlette CVE məcburi

---

## G0 üçün İnsan addımları (təsdiqdən sonra / paralel)
1. **GitHub:** private repo + org yarat → remote əlavə et → push → CI aktivləşir; `CODEOWNERS @OWNER` doldur
2. (opsional) hosts faylı: `127.0.0.1 posnet.local keycloak.posnet.local ...` (Caddy domenləri üçün)
3. AI-1 paralel insan trekləri: retail satıcı müsahibələri · Birmarket/Trendyol API access (D-002)

---

## Endpointlər (lokal dev — `make up` / `docker compose up -d` sonrası)

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

## CVE Status (ADR-0010)

| CVE | Paket | Status |
|---|---|---|
| CVE-2026-32274 | black | ✅ Düzəldildi |
| CVE-2025-71176 | pytest | ⏳ Ignored (schemathesis 4.x) |
| CVE-2025-62727 / PYSEC-2026-161 | starlette | ⏳ Ignored (**G7-də MƏCBURİ**) |
