# STATUS — Posnet

**Cari faza:** AI-2 (POS CORE) — G1 ✅ **şərti təsdiq** (2026-06-03, Huseyn); AI-1 Foundation TAM (18/18)
**Cari task:** AI-2.1 (Catalog domain + CRUD API — product/variant/barkod axtarış)
**Son commit:** `a8b5402` — feat(core): AI-1.18 health/shutdown + DB pool + backup
**Son uğurlu verify:** 2026-06-03; AI-1.18 TAM (health/shutdown drain + pool_pre_ping + DB backup: 7 yeni test, **ümumi coverage 100%**, 269 test)
**Vəziyyət:** G1 ✅ ŞƏRTİ TƏSDİQ (kod ✓ lokal) — AI-2 başlayır. **Paralel (insan):** GitHub repo → CI yaşıl → sonra `v0.1.0-alpha` tag

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
  - ✅ **follow-up həll (AI-1.9.5):** relay/consumer owner (RLS-exempt) sessionmaker üzərində = cross-tenant rol;
    `pgmq.ensure_queue` app startup-da; PGMQ_*/EVENTBUS_* → EventBusConfig; graceful start/stop lifespan-da
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
- [x] **AI-1.8** `libs/auth` (JWT verify + JWKS Redis cache + RBAC) — 2026-06-02
  - `TokenVerifier`: RS256 JWKS verify (iss/exp/alg/kid) → `Principal`; xəta → `AuthError`(401)
  - `JwksClient`: JWKS Redis cache (TTL), kid-miss → 1 refetch (rotation heal); fetch xətası propagate
  - `require_role` / `require_permission` (statik foundation RBAC map, super_admin bypass) → `ForbiddenError`(403)
  - audience verify konfiqurabel (default off, G7-də mapper+enable); 21 test (real Redis+respx+sintetik RSA); auth 100%
- [x] **AI-1.9 FastAPI app + middleware stack ✅ — 5/5 dilim TAM (hər biri TDD + atomik commit)** — 2026-06-03
  - **Middleware sırası (LOCKED):** RequestId → Logging → Tracing(1.13) → Auth → TenantContext(RLS) → RateLimit → ErrorHandler
  - [x] **AI-1.9.1** — App skeleton: `app/main.py` `create_app(settings)` factory · `lifespan` (engine+redis app.state, dispose/aclose) ·
    Settings genişləndi (app_name/version/environment/redis_url, `populate_by_name`) · `/healthz` (liveness) + `/readyz` (DB+Redis ping→503) ·
    Windows: qlobal selector event-loop policy (TestClient portal + psycopg async) · *əhatə: AI-1.9 core + AI-1.18 health hissəsi* — 2026-06-02
  - [x] **AI-1.9.2** — RequestId middleware (pure ASGI, contextvar + scope key; X-Request-ID echo/generate) · structlog
    (JSON prod / console local, request_id processor; AI-1.2-dən təxir edilmiş logger) · access-log middleware ·
    global RFC 7807 handler-lər (DomainError→problem+json, ValidationError→422, HTTPException, generic→500 leak-siz) · *əhatə: **AI-1.10*** — 2026-06-02
  - [x] **AI-1.9.3** — Auth dependency (`get_principal`: Bearer→verify→Principal; TokenVerifier lifespan-da) + `requires_role`/`requires_permission` Depends ·
    TenantContext: `get_tenant_session` subject→`users.external_subject` DB lookup (owner, RLS-exempt) → `SET LOCAL ROLE posnet_app` + `app.current_tenant` (RLS) ·
    super_admin cross-tenant; naməlum/deaktiv subject→403 · **ADR-0015** (subject→DB lookup; JWT-claim/email redd) · **migration 0003** (`users.external_subject` qlobal unique) · *əhatə: **AI-1.11*** — 2026-06-03
  - [x] **AI-1.9.4** — CORS (CORSMiddleware, konfiqurabel) · SecurityHeaders middleware (pure ASGI: nosniff/DENY/no-referrer + konfiqurabel CSP/HSTS, route header-i clobber etmir) ·
    slowapi `SlowAPIASGIMiddleware` (async handler; BaseHTTP variantı async handler-i atır) → Redis storage (memory:// testdə), IP key, global limit, health exempt, `RateLimitExceeded`→RFC 7807 429 · *əhatə: **AI-1.12*** — 2026-06-03
  - [x] **AI-1.9.5** — `EventBusWorkers`: outbox relay + consumer-i `lifespan`-da background task; **owner (RLS-exempt) sessionmaker = cross-tenant rol** (per-request yol `posnet_app`-ə keçir, ADR-0013) ·
    startup `pgmq.ensure_queue` (queue+DLQ) · graceful stop (cancel+gather) · `EVENTBUS_ENABLED` gate · `create_app(event_handler=)` inject (foundation default = log handler; AI-2 dispatcher) · *əhatə: **AI-1.14 follow-up*** — 2026-06-03
- [x] **AI-1.10** Global error handler (RFC 7807) ✅ — **AI-1.9.2-də** (2026-06-02)
- [x] **AI-1.11** Tenant context (RLS injection) ✅ — **AI-1.9.3-də** (2026-06-03, ADR-0015)
- [x] **AI-1.12** CORS + security headers + rate limiter ✅ — **AI-1.9.4-də** (2026-06-03)
- [x] **AI-1.13** OTel tracing (FastAPI HTTP + SQLAlchemy DB span → OTLP) + Prometheus `/metrics` + trace_id log/RFC7807 korelyasiya ✅ — 2026-06-03
  - `libs/observability` (TelemetryConfig + provider/sampler + instrument + metrics); `otel_enabled` gate (default False, .env-də açıq); Redis/httpx instrumentation təxir (process-global)
- [x] **AI-1.14** pgmq publisher + outbox + consumer + DLQ — hub onurğası ✅ (2026-06-02, ADR-0013)
- [x] **AI-1.15** Tenant onboarding API (`POST /v1/tenants`, super_admin → owner cross-tenant write) + admin user + `identity.tenant.onboarded` outbox event; idempotent `seed_first_tenant` + `scripts/seed_data.py` (make seed) ✅ — 2026-06-03
- [x] **AI-1.16** User/Role/Permission CRUD (tenant-scoped, `tenant_admin`): `POST/GET /v1/users`, `POST/GET /v1/roles`(+permissions), `POST /v1/users/{id}/roles` (assign); RLS izolyasiya + cross-tenant assign 404 (RLS lookup, FK leak qarşısı); `require_tenant` dep ✅ — 2026-06-03
- [x] **AI-1.17** Feature flags + i18n backend ✅ — 2026-06-03
  - `libs/i18n` (mexanizm): Accept-Language parse (q-sıralama) + `negotiate_locale` (Babel); `Translator` fallback locale→default→key (format gap → template toxunulmaz)
  - core: az(default)/en/tr/ru kataloqları · `get_locale` dep (`?locale=` override → header → default) · translator app.state-də · `GET /v1/i18n/messages` **auth-suz** (login ekranı üçün) negotiated kataloqu qaytarır
  - `libs/feature_flags`: `FlagRegistry` (default-lar + `resolve(overrides)`; naməlum açar iqnor) · `UnknownFlagError` write-validasiyası; REGISTRY: marketplace_sync/online_storefront/delivery_integration (off) + multi_store (on)
  - migration **0004** `feature_flags` (tenant_id,key,enabled, unique) + RLS policy + **posnet_app GRANT** (0002 blanket grant yalnız mövcud cədvəlləri tuturdu); `GET /v1/feature-flags` (tenant üzvü) · `PUT /v1/feature-flags/{key}` (tenant_admin, naməlum→404); upsert + RLS izolyasiya
- [x] **AI-1.18** Health probes + graceful shutdown + DB pool + backup ✅ — 2026-06-03
  - health: `/healthz`+`/readyz` (1.9.1-də) + **readiness drain** — `app.state.ready` lifespan startup-da True, shutdown başında False; `/readyz` lifecycle gate → starting/draining-də 503 `unavailable` (dep yoxlamasından əvvəl)
  - DB pool: `DATABASE_POOL_PRE_PING` (default true) → `create_async_engine(pool_pre_ping=...)` (stale bağlantı recycle)
  - backup: `services/core/app/backup.py` (pure helpers: `pg_dump_command` DSN→argv+env/PGPASSWORD, `backup_filename` UTC, `select_expired` retention) + `scripts/db_backup.py` (`make backup`: pg_dump→BACKUP_DIR, opsional S3/MinIO upload, retention prune)

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
- **G1 (Foundation): ✅ APPROVED (şərti)** (2026-06-03, Huseyn; 18/18 task TAM) — RLS ✅ · eventbus publish→consume→DLQ ✅ · Vault ✅ · canonical model ✅ · Keycloak OIDC ✅ · `libs/auth` ✅ · app skeleton+health+errors(RFC7807) ✅ · auth dep + per-request tenant RLS ✅ · CORS+sec-headers+rate-limit(101→429) ✅ · eventbus lifespan workers (cross-tenant) ✅ · **AI-1.9 TAM** · OTel trace + Prometheus metrics ✅ · tenant onboarding API + seed ✅ · user/role CRUD (tenant RLS) ✅ · feature flags + i18n backend ✅ · health/shutdown drain + pool + backup ✅;
  **şərt + paralel (insan):** GitHub repo → CI yaşıl → sonra `v0.1.0-alpha` tag (AI çəkə bilər). Bax HUMAN-GATES.md → G1.
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
