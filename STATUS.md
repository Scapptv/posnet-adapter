# STATUS — Posnet

**Cari faza:** AI-1 (FOUNDATION) — G0 ✅ təsdiqləndi (2026-06-01, operator Huseyn)
**Cari task:** AI-1.6 (RLS policies migration 0002 + cross-tenant izolasiya testi)
**Son commit:** `b84e641` — feat(common): AI-1.2 libs/common
**Son uğurlu verify:** 2026-06-02; AI-1.5 schema yaşıl (migration up/down/up, coverage 99.5%)
**Vəziyyət:** AI-1 IN_PROGRESS

---

## 🎯 STRATEGİYA (ADR-0012 — POS-anchored İnteqrasiya Hub)

**Məhsul:** POS-anchored omnichannel **inteqrasiya hub** (TSoft/Entegra/ChannelEngine modeli).
POS = tək həqiqət mənbəyi; hub məhsul/stok/qiyməti marketplace/delivery/booking-ə çıxarır.

- **Beachhead:** **Azərbaycan · pərakəndə · ilk kanal = Birmarket/Trendyol (marketplace)**
- **İlk MVP dilimi:** POS-da məhsul → Birmarket-ə listing → stok/qiymət sync → sifariş POS-a → stok hər yerdə azalır
- **Crown jewel:** adapter SDK + canonical model + sync engine (idempotency + reconciliation 1-ci gündən)
- **Paralel insan trekləri:** (1) retail satıcı müsahibələri · (2) **Birmarket/Trendyol seller API access** (D-002)

> 🔄 Aktiv yol: AI-0 ✅ → **AI-1 (Foundation)** → AI-2 (POS Core) → AI-2.5 (Adapter framework, MVP) → G-V.
> Detal: `docs/adr/0012-integration-hub-reframe.md`.

---

## Faza AI-1 — FOUNDATION (18 task; ~25-40 saat)

**Məqsəd:** Auth + multi-tenant + RLS + DB + **eventbus/outbox (hub onurğası)** + observability.
**Middleware sırası:** RequestId → Logging → Tracing → Auth → TenantContext(RLS) → RateLimit → ErrorHandler.

- [x] **AI-1.1** Test infra (conftest + testcontainers Postgres/Redis + harness) — 2026-06-01
  - pytest filterwarnings: testcontainers + jsonschema 3rd-party deprecation ignore
- [x] **AI-1.2** `libs/common` (errors/RFC7807, Money integer-minor, types, request-id) — 2026-06-01
  - mypy --strict ✅ · ruff ✅ · coverage 100% → **gate 80%-ə qaldırıldı** · logger AI-1.9-a təxir
- [x] **AI-1.5** SQLAlchemy models + Alembic migration 0001 (identity 9 cədvəl, TIMESTAMPTZ) — 2026-06-02
  - autogenerate; **up/down/up** testcontainers test ✅; `tenant_id` RLS üçün bütün cədvəllərdə; coverage 99.5%
- [ ] **AI-1.6** RLS policies (migration 0002) + cross-tenant izolasiya testi ← **CARİ**
- [ ] AI-1.3 Vault helper · AI-1.4 canonical_model (schema/RLS-dən sonra)
- [ ] AI-1.7 Keycloak realm + 3 client + 4 role + test user
- [ ] AI-1.8 `libs/auth` (JWT verify + JWKS cache + require_permission)
- [ ] AI-1.9 FastAPI app + middleware stack
- [ ] AI-1.10 Global error handler (RFC 7807)
- [ ] AI-1.11 Tenant context middleware (RLS injection)
- [ ] AI-1.12 CORS + security headers + rate limiter
- [ ] AI-1.13 OTel + Prometheus + Grafana + Loki wiring (app → mövcud stack)
- [ ] **AI-1.14** pgmq publisher + outbox + consumer + DLQ — **hub onurğası (prioritet)**
- [ ] AI-1.15 Tenant onboarding API + ilk tenant seed
- [ ] AI-1.16 User/Role/Permission CRUD
- [ ] AI-1.17 Feature flags + i18n backend
- [ ] AI-1.18 Health probes + graceful shutdown + DB pool + backup

**G1 acceptance:** RLS izolasiya · OIDC round-trip · migration up/down/up · pgmq publish→consume→DLQ · coverage ≥80% · OTel trace · tag v0.1.0-alpha.

## Faza AI-0 — ✅ TAMAMLANDI (G0 APPROVED 2026-06-01)
- 0.1-0.6, 0.8-0.11 ✅ (0.7 Flutter təxirdə). 13 servis dev stack; CI workflows; ADR 0001-0003/0010-0012.

## Bloklar / Həll olunmuş
- ✅ Toolchain: Python 3.12 (uv) · make · Docker v29.4.3 · node v24.8 + pnpm 10.18
- ✅ İki ayrı posnet layihəsi (`adapter_*` vs help-center `posnet_*`); port toqquşmaları həll
- ✅ pytest cov no-data fix; secrets baseline təmizləndi (lock/node_modules exclude)
- ⏳ **GitHub remote/repo** — CI işləməsi üçün insan qurmalı (paralel)
- ⏳ CVE remediation (ADR-0010): 3 CVE ignored — G7-də məcburi

## Gate vəziyyəti
- **G0 (Bootstrap): ✅ APPROVED** (2026-06-01, Huseyn)
- **G1 (Foundation): 🔵 CARİ** — eventbus/outbox prioritet (hub onurğası)
- G2 (POS Core): canonical model "hub-a hazır"
- **AI-2.5 (Adapter framework + 1 kanal):** ADR-0012 — MVP-yə daxil
- **G-V (Validasiya):** retail satıcı demo (kill/continue)
- G3-G8: ❄️ təxirdə (G-V sonrası); G7-də starlette CVE məcburi

---

## Endpointlər (lokal dev — `docker compose up -d` sonrası)

| Servis | Ünvan | Giriş |
|---|---|---|
| Postgres+pgmq | `localhost:5432` | posnet / posnet_dev_pw / posnet_core |
| Redis | `localhost:6379` | — |
| Vault | `localhost:8200` | token `dev-root-token` |
| Keycloak | `localhost:8080` (`:9100/health`) | admin / admin |
| Jaeger / Prometheus / Grafana / Loki | `16686 / 9090 / 3000 / 3100` | grafana: admin/admin |
| OTLP | `localhost:4317` (gRPC), `4318` (HTTP) | — |
| Mailpit / MinIO | `8025` · `9000` (S3), `9101` (console) | minio: minioadmin/minioadmin |
| Caddy (TLS) | `https://localhost:8443` | daxili CA |

---

## CVE Status (ADR-0010)

| CVE | Paket | Status |
|---|---|---|
| CVE-2026-32274 | black | ✅ Düzəldildi |
| CVE-2025-71176 | pytest | ⏳ Ignored |
| CVE-2025-62727 / PYSEC-2026-161 | starlette | ⏳ Ignored (**G7-də MƏCBURİ**) |
