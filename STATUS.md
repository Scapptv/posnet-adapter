# STATUS — Posnet

**Cari faza:** AI-1 (FOUNDATION) — G0 ✅ təsdiqləndi (2026-06-01, operator Huseyn)
**Cari task:** AI-1.8 (`libs/auth` JWT verify + JWKS Redis cache + require_permission — posnet realm hazır, canlı round-trip mümkün) — növbəti sessiya
**Son commit:** `f0d9ccc` — feat(keycloak): AI-1.7 posnet realm (realm-as-code, secret-siz)
**Son uğurlu verify:** 2026-06-02; AI-1.7 TAM (Keycloak realm: OIDC round-trip canlı ✅, 8 struktur test, ümumi coverage 99.8%)
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
- [x] **AI-1.6** RLS policies (migration 0002) + cross-tenant izolasiya testi — 2026-06-02
  - `posnet_app` role + `tenant_isolation` policy (USING + WITH CHECK); SELECT izolasiya + insert-reject test ✅
- [x] **AI-1.14** Piece B — eventbus (pgmq + outbox + consumer + DLQ, hub onurğası) — 2026-06-02
  - `libs/eventbus`: Event envelope · `enqueue` (transactional outbox) · `OutboxRelay`
    (FOR UPDATE SKIP LOCKED, atomik publish+mark) · `Consumer` (retry/backoff + DLQ) · `pgmq.py`
  - pgmq SQLAlchemy üzərindən (ümumi pool → relay genuine-atomik; ADR-0013); `tembo-pgmq-python` istifadəolunmur
  - Consumer handler-dən əvvəl `SET LOCAL app.current_tenant` (RLS scope)
  - Test infra: `tests/integration/conftest.py`-a async fixture-lər (async_engine/session_factory/migrated_db);
    Windows psycopg async üçün `event_loop_policy` selector-loop fix (root conftest)
  - ⚠️ **AI-1.9/1.11 follow-up:** relay/consumer cross-tenant → DB rolu RLS bypass etməli (owner/BYPASSRLS);
    queue bootstrap (`pgmq.ensure_queue`) app startup-da; EVENTBUS_* env → EventBusConfig wiring
- [x] **AI-1.4** `libs/canonical_model` skeleton (v1) — 2026-06-02
  - frozen + strict (`extra=forbid`) Pydantic v2; `schema_version` ClassVar "v1" (ADR-0012 §17.1)
  - CanonicalProduct (listing snapshot) · Inventory (`available`=qty−reserved) · Price · Order (line+customer+totals)
  - `price_minor`+`currency` → `Money` property körpüsü; `validate_currency_code` libs/common-a çıxarıldı (DRY)
- [x] **AI-1.3** `libs/vault` `get_secret()` Vault helper — 2026-06-02
  - `vault://<mount>/<path...>/<key>` ref (son segment = key); `VaultClient`(hvac KV-v2) + `resolve_ref` passthrough
  - `SecretError` (sehv ref / InvalidPath / key yox / forbidden); sirr dəyərləri cache/log olunmur (ADR-0003)
  - testcontainers `VaultContainer` fixture (`tests/integration/conftest.py`) — auth/digər task-lar üçün
- [x] **AI-1.7** Keycloak `posnet` realm (realm-as-code) — 2026-06-02
  - 5 rol (§15 RBAC) · 3 client: `posnet-web`/`posnet-pos` public+PKCE(S256), `api-gateway` **bearer-only** · test user `owner`
  - **secret YOX** (ADR-0014): foundation public+PKCE/bearer-only → client secret lazım deyil → **insan gate yox** (səhv çərçivələmə düzəldildi)
  - `docker-compose --import-realm` + volume; OIDC round-trip canlı ✅ (token + `realm_access.roles=[tenant_admin]` + JWKS RS256)
  - ⚠️ təxir: `tenant_id` claim strategiyası (Keycloak attr vs DB lookup) → AI-1.11; confidential secret → G7 (prod, insan/Vault)
- [ ] **AI-1.8 `libs/auth` (JWT verify + JWKS Redis cache + require_permission) (← növbəti; sintetik açar+respx ilə test)**
- [ ] AI-1.9 FastAPI app + middleware stack
- [ ] AI-1.10 Global error handler (RFC 7807)
- [ ] AI-1.11 Tenant context middleware (RLS injection)
- [ ] AI-1.12 CORS + security headers + rate limiter
- [ ] AI-1.13 OTel + Prometheus + Grafana + Loki wiring (app → mövcud stack)
- [x] **AI-1.14** pgmq publisher + outbox + consumer + DLQ — hub onurğası ✅ (2026-06-02, ADR-0013)
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
- **G1 (Foundation): 🔵 CARİ** — RLS ✅ · eventbus publish→consume→DLQ ✅ · Vault ✅ · canonical model ✅ · Keycloak OIDC round-trip ✅; qalan: `libs/auth` · app+middleware · observability · tenant onboarding · v0.1.0-alpha tag
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
