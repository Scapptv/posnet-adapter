# STATUS — Posnet

**Cari faza:** AI-2 (POS CORE) — G1 ✅ **şərti təsdiq** (2026-06-03, Scapptv); AI-1 Foundation TAM (18/18)
**Cari task:** **AI-2.H2** (Data identity & invariant — UNIQUE(tenant_id, sku/barcode) + deterministik lookup + IntegrityError→409 + DB CHECK + journal grant) — bax Faza AI-2.H
**Son commit:** `2463f96` — refactor(core): dual-engine OTel dedupe (AI-2.H1 tam)
**Son uğurlu verify:** 2026-06-03; AI-2.H1 TAM (365 test, coverage 100% lokal)
**Vəziyyət:** AI-2 IN_PROGRESS (2.1–2.4 ✅; **AI-2.H1 ✅ təhlükəsizlik duruşu**). **$100M audit** (6 agent) → **Faza AI-2.H (hardening) AI-2.5-dən ƏVVƏL** (ADR-0016); növbəti AI-2.H2. GitHub `Scapptv/posnet-adapter` (public), **CI bloklu** (hesab billing), push pauza (lokal-only).

---

## 🎯 STRATEGİYA (ADR-0012 + ADR-0016 — Posnetin İnteqrasiya Nüvəsi)

**Məhsul:** **Posnetin inteqrasiya nüvəsi** — necə ki **CLOPOS** = **Wolt/Bolt** (delivery) inteqratoru,
**TSoft** = **Trendyol** (marketplace) inteqratorudur, Posnet eyni nüvə ilə delivery + marketplace +
booking kanallarına bağlanır. Bu servis = satıcının **online/inteqrasiya qatı** (mövcud Posnet ERP
məhsul/stok/qiymətin sahibidir; bu, online-a çıxan curated alt-çoxluq + online qiymət/kampaniya + online
sifariş emalı + online çek).
- **Outbound:** məhsul/stok/qiymət/endirim → (canonical) → kanallar (Trendyol/Birmarket/Wolt/Bolt) **push**
- **Inbound:** sifariş/ödəniş/kargo → (canonical) → **Posnet** yaz
- **Beachhead:** **Azərbaycan · pərakəndə · ilk kanal = Birmarket/Trendyol (marketplace)**
- **Crown jewel:** adapter SDK + canonical model + sync engine (idempotency + reconciliation 1-ci gündən)

> 🔄 Aktiv yol: AI-0 ✅ → AI-1 (Foundation) ✅ → AI-2.1–2.4 (POS/online qat) ✅ → **AI-2.H (Audit hardening) ◀ CARİ** → AI-2.5 (Adapter framework + 1 kanal) → G-V.
> Detal: `docs/adr/0012-integration-hub-reframe.md`, **`docs/adr/0016-audit-hardening-before-adapters.md`**.

---

## Faza AI-2.H — AUDIT HARDENING (icra ardıcıllığı; **CARİ** — AI-2.5-dən əvvəl)

**Mənbə:** $100M audit (6 agent, 2026-06-03) — ADR-0016. Düzgün məntiqi sıra: təhlükəsizlik → data
identity/invariant → korrektlik/proof → sync enabler → sonra adapterlər. **Kritiklər indi ucuz,
kanallardan sonra baha.** Hər task: TDD + lokal `make verify`/pytest 100% + commit (push yox).

- [x] **AI-2.H1 🔴 Security posture** ✅ — 2026-06-03 (ADR-0017). RLS `FORCE` bütün policy cədvəllərinə (dinamik DO-loop) + `posnet_app` **non-owner LOGIN** rolu (NOSUPERUSER NOBYPASSRLS); **dual-pool**: app pool (`DATABASE_APP_URL`→posnet_app, per-request) + system pool (`DATABASE_URL`→superuser: migration/super_admin/relay/consumer/onboarding). Role-suz/tenant-siz sorğu **0 sətir** regression. `posnet_resolve_tenant` SECURITY DEFINER (sabit search_path, PUBLIC-dən REVOKE) — kilidli pool üçün tək cross-tenant subject→tenant. `realm-posnet.json` parolu → `${env.POSNET_OWNER_PASSWORD}` (compose dev default, A6). JWT `require_exp/iat/sub` + boş/whitespace sub rədd + audience enforce local/test xaricində (A7). migration **0009**; 14 yeni test → suite **365 @ 100%**. *(audit A1, A6, A7)*
- [ ] **AI-2.H2 🔴 Data identity & invariant** — `UNIQUE(tenant_id, sku)` + `UNIQUE(tenant_id, barcode) WHERE barcode IS NOT NULL` + `find_variant_*` deterministik `ORDER BY`; inventory first-create `IntegrityError → 409`; DB `CHECK(qty>=0, reserved_qty>=0, reserved_qty<=qty)`; journal cədvəlləri (stock_movements/cash_movements/audit_logs) INSERT/SELECT-only grant *(audit A2, A3, A4, schema)*
- [ ] **AI-2.H3 🔴 Anti-oversell proof** — real paralel-tx oversell testi (asyncio.gather, son vahid); coverage-theater testləri (fake-session, `session=None`) real et və ya işarələ; `_effect`/Money üçün hypothesis property-test; `make verify`-ə `test` əlavə *(audit A4, A5)*
- [ ] **AI-2.H4 🔴 Sync change-feed** — catalog/inventory/pricing domain mutasiyaları **outbox event** emit (onboarding template) + consume **idempotency** (`idempotency_keys` wiring, event_id dedup) *(audit B1, B5)*
- [ ] **AI-2.H5 🟡 Sync model enabler** — store↔warehouse / **online-sellable-stock** modeli + **online-published** flag + **channel schema** dizaynı (`channels`, `channel_listings`: sku↔external_listing_id, category/attribute map) + **canonical mapper** (Product/Inventory/Price → CanonicalProduct, aggregation ADR) *(audit B2, B3, B4, B6)*

> ⚠️ **AI-2.H1 canlı yoxlama (paralel, operator):** (a) Keycloak `${env.POSNET_OWNER_PASSWORD}` substitusiyası import-da — avtomatik realm testi strukturaldır, OIDC round-trip canlı təsdiq istəyir; (b) dev app `DATABASE_APP_URL` (posnet_app pool) ilə `docker compose up` + smoke. Boş `DATABASE_APP_URL` system pool-a düşür (işləyir, amma kilidli deyil).

**Hardening sonrası → AI-2.5** adapter framework + 1 kanal (mock-marketplace → real) təmizlənmiş təməl üstündə.
**FTS gin tenant-aware** + per-tenant/per-kanal rate-limit + eventbus health (DLQ/queue depth) + trace propagation = AI-2.5 ərzində.

## Faza AI-2 — POS CORE / online qat (2.1–2.4 ✅; sale = AI-2.5-ə köçdü)

**Məqsəd:** Catalog + inventory + pricing + shift + sale = **canonical tək həqiqət mənbəyi** (hub-a hazır).

- [x] **AI-2.1** Catalog domain + CRUD API ✅ — 2026-06-03
  - migration **0005**: products/variants/product_images (RLS + posnet_app grant, 0004 pattern); `gin(to_tsvector('simple', name))` dil-agnostik ad axtarışı; sku/barcode index
  - domain/catalog.py (RLS-scoped): `create_product`(+images) · `list_products` (FTS plainto_tsquery) · `get_product` (variant+image detail) · `add_variant` · `find_variant_by_barcode/sku`. store_id/product_id RLS-lookup ilə yoxlanır → cross-tenant 404 (FK leak qarşısı)
  - API: `POST/GET /v1/products` · `GET /v1/products/{id}` · `POST /v1/products/{id}/variants` · `GET /v1/variants/lookup?barcode|sku` (POS scan). Gating: `catalog:read` (bütün store rolları) / `catalog:write` (store_manager/clerk/tenant_admin). Money integer-minor; currency ISO-4217 (default AZN)
- [x] **AI-2.2** Inventory + anti-oversell ✅ — 2026-06-03
  - migration **0006**: warehouses/inventory/stock_movements (RLS + grant); `inventory(qty, reserved_qty, min_qty, version, UNIQUE(variant_id,warehouse_id))`
  - domain/inventory.py: `_effect` (pure: in/out/reserve/unreserve/adjust + anti-oversell guard) · `apply_movement` (variant/warehouse RLS-lookup→404 · `SELECT FOR UPDATE` lock · version++ · movement insert · `expected_version` optimistic check) · create/list_warehouse · get_inventory
  - API: `POST/GET /v1/warehouses` · `POST /v1/inventory/movements` (vahid yazı yolu) · `GET /v1/inventory?variant_id` (`available` computed). Gating: inventory:read/write
- [x] **AI-2.3** Pricing — effective price + overrides ✅ — 2026-06-03
  - migration **0007**: `price_overrides(tenant_id, variant_id, store_id?, price_minor, valid_from?, valid_to?)` (RLS + grant)
  - domain/pricing.py: `set_override` (variant/store RLS-lookup→404) · `resolve_price` (base ⊕ aktiv override; precedence store-specific > tenant-wide, newest wins; validity window). `ResolvedPrice` (base/effective/source/override_id)
  - API: `POST /v1/variants/{id}/price-overrides` · `GET /v1/variants/{id}/price?store_id&at` (default now). Gating pricing:read/write. Tam rule engine (percent/tiered) təxir
- [x] **AI-2.4** Shift/vardiya + cash management ✅ — 2026-06-03
  - migration **0008**: `shifts(store_id, cashier_id, status, opening/closing_cash_minor, opened/closed_at)` + **partial UNIQUE(store_id,cashier_id) WHERE status='open'** (tək açıq vardiya) · `cash_movements(shift_id, kind[in/out], amount_minor, reason)`
  - domain/shift.py: `open_shift` (RLS-lookup→404, ikiqat açılış→Conflict) · `close_shift` (already-closed→Conflict) · `record_cash` (bağlı vardiya→ValidationError) · list/get · `cash_summary` (expected = opening + in − out)
  - API: `POST/GET /v1/shifts` · `GET /v1/shifts/{id}` (detail+summary) · `POST /{id}/close` · `POST /{id}/cash-movements`. Gating shift:read/write
- [ ] AI-2.5-POS Sale/çek (yarat → stok düş, atomik) + X/Z report
- [ ] AI-2.6 CanonicalProduct/Inventory/Price map (catalog ↔ canonical_model — hub üçün kritik)
- [ ] AI-2.7 Admin-web minimal (məhsul/stok idarəsi)
- [ ] AI-2.8 Flutter kassir minimal (offline-first satış) — opsional, gec OK

**Follow-up (təxir — G2-yə qədər həll):**
- AI-2.1: `/variants/lookup` cavabına `currency` (+ product_name) əlavə (POS qiymət göstərimi); `UNIQUE(tenant_id, barcode)` partial constraint; `list_products` paginasiya
- AI-2.2: `transfer` movement (2 warehouse atomik); inventory ilk-yaranma konkurent race (INSERT ON CONFLICT)
- **GitHub CI:** hesab "failed payment" blokunu həll et (billing) — sonra push + CI yaşıl + `v0.1.0-alpha` tag

**GATE G2:** məhsul yarat→barkod axtar→satış→stok düş E2E · canonical map · coverage ≥80% (pul path 95%) · make verify · CI yaşıl.

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
- ✅ **GitHub:** `Scapptv/posnet-adapter` (**public**) push olundu (2026-06-03); git identity = `Scapptv <scapptv@gmail.com>` (köhnə huseyn/hc kimlikləri tarixçə+config-dən silindi).
- ⏳ **CI bloklu (hesab-tərəfli, kod yox):** Actions job-ları runner götürmür (0 step, log yox) — hesabda "recent payments failed" vəziyyəti Actions icrasını dayandırır. Billing təmiz ($0) görünür → ehtimal ödəniş-üsulu/verifikasiya. Həll: kart əlavə/billing → işləməsə GitHub Support. Public etmək "spending limit" hissəsini həll etdi (startup işləyir), "failed payment" hissəsi qalır. Lokal `make verify` + 289 test yaşıl.
- ⏳ CVE remediation (ADR-0010): 3 CVE ignored — G7-də məcburi

## Gate vəziyyəti
- **G0 (Bootstrap): ✅ APPROVED** (2026-06-01, Scapptv)
- **G1 (Foundation): ✅ APPROVED (şərti)** (2026-06-03, Scapptv; 18/18 task TAM) — RLS ✅ · eventbus publish→consume→DLQ ✅ · Vault ✅ · canonical model ✅ · Keycloak OIDC ✅ · `libs/auth` ✅ · app skeleton+health+errors(RFC7807) ✅ · auth dep + per-request tenant RLS ✅ · CORS+sec-headers+rate-limit(101→429) ✅ · eventbus lifespan workers (cross-tenant) ✅ · **AI-1.9 TAM** · OTel trace + Prometheus metrics ✅ · tenant onboarding API + seed ✅ · user/role CRUD (tenant RLS) ✅ · feature flags + i18n backend ✅ · health/shutdown drain + pool + backup ✅;
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
