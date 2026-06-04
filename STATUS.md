# STATUS — Posnet

**Cari faza:** AI-2 (POS CORE) — G1 ✅ **şərti təsdiq** (2026-06-03, Scapptv); AI-1 Foundation TAM (18/18); **Faza AI-2.H TAM (H1-H5)**; **AI-2.5 IN_PROGRESS (5.1-5.4 ✅)**
**Cari task:** **AI-2.5.5** E2E MVP — POS məhsul → push_listing → mock görür → stok/qiymət dəyiş push → mock sifariş webhook → POS stok azalır → ack. **0 oversell**.
**Son commit:** `5275e3d` — feat(adapter): AI-2.5.3 mock marketplace + first concrete adapter + contract test
**Son uğurlu verify:** 2026-06-04; AI-2.5.4 TAM (544 test, coverage 83.4%)
**Vəziyyət:** AI-2 IN_PROGRESS (2.1–2.4 ✅; **AI-2.H1-H5 ✅ TAM**; **AI-2.5.1-5.4 ✅** contract + dispatcher + mock + webhook ingress). Növbəti AI-2.5 dilimi: E2E MVP. GitHub `Scapptv/posnet-adapter` (public), **CI bloklu** (Q-002, operator), push pauza (lokal-only).

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

> 🔄 Aktiv yol: AI-0 ✅ → AI-1 (Foundation) ✅ → AI-2.1–2.4 (POS/online qat) ✅ → **AI-2.H (Audit hardening) ✅ TAM** → **AI-2.5 (Adapter framework + 1 kanal) ◀ CARİ** → G-V.
> Detal: `docs/adr/0012-integration-hub-reframe.md`, `docs/adr/0016-audit-hardening-before-adapters.md`, `docs/adr/0017-db-security-posture.md`, `docs/adr/0018-sync-model-enabler.md`.

---

## Faza AI-2.H — AUDIT HARDENING ✅ TAMAMLANDI (2026-06-03 → 2026-06-04)

**Mənbə:** $100M audit (6 agent, 2026-06-03) — ADR-0016. Düzgün məntiqi sıra: təhlükəsizlik → data
identity/invariant → korrektlik/proof → sync enabler → sonra adapterlər. **Kritiklər ucuz mərhələdə
həll olundu**, AI-2.5 təmizlənmiş təməl üstündə qurula bilər.

### Çatdırma xülasə (H1-H5)

| Task | Tarix | ADR | Migration | Yeni test | Suite | Audit |
|---|---|---|---|---|---|---|
| H1 Security posture | 2026-06-03 | 0017 | 0009 | +14 | 365 | A1, A6, A7 |
| H2 Data identity & invariant | 2026-06-03 | — | 0010 | +20 | 385 | A2, A3, A4 |
| H3 Anti-oversell proof | 2026-06-04 | — | — | +21 | 406 | A4, A5 |
| H4 Sync change-feed | 2026-06-04 | — | — | +8 | 414 | B1, B5 |
| H5 Sync model enabler | 2026-06-04 | 0018 | 0011 | +29 | 443 | B2, B3, B4, B6 |

**Cəmi:** 5 task · 3 migration · 3 ADR · +92 test (351 → 443) · coverage **80% gate-i 99.88%-də saxlayır** (honest, fake-session paint silinmiş).

### Audit tapıntıları → həll xəritəsi

| # | Tapıntı | Risk | Həll yeri | Status |
|---|---|---|---|---|
| **A1** | RLS `FORCE` yox + app `posnet` (owner) ilə bağlanır → bir unudulmuş `SET LOCAL ROLE` = bütün tenant-lar sızar | 🔴 | **H1** — RLS FORCE bütün cədvəllərə, dual-pool, posnet_app non-owner LOGIN | ✅ |
| **A2** | SKU/barkod tenant daxilində unikal deyil; `find_variant_*` `ORDER BY`-sız | 🔴 | **H2** — `UNIQUE(tenant_id, sku)` + partial `UNIQUE(tenant_id, barcode)` + deterministik `ORDER BY id` | ✅ |
| **A3** | Inventory first-create race `IntegrityError` tutulmur → HTTP 500 | 🔴 | **H2** — `apply_movement` `IntegrityError` → `ConflictError(409)` | ✅ |
| **A4** | Anti-oversell üçün DB CHECK backstop yox; sıfır konkurentlik testi | 🔴 | **H2** + **H3** — `inventory` CHECK qty/reserved + real paralel-tx oversell testləri | ✅ |
| **A5** | "100% coverage" qismən saxta — fake-session, monkey-patch handler-lər | 🔴 | **H3** — fake-session unit-lər silindi, hypothesis property-test əlavə, `make verify`-ə `test` | ✅ |
| **A6** | `realm-posnet.json`-da hardcoded `tenant_admin` parolu (public repo) | 🔴 | **H1** — `${env.POSNET_OWNER_PASSWORD}` substitusiyası, compose dev default | ✅ |
| **A7** | JWT `exp/iat/sub` məcburi deyil; audience yox | 🔴 | **H1** — `require_exp/iat/sub`, audience local/test xaricində enforce | ✅ |
| **B1** | Catalog/inventory/pricing **sıfır outbox event** emit → sync engine-in change-feed-i yoxdur | 🔴 | **H4** — `catalog.product.created` / `.variant.added` / `inventory.movement.applied` / `pricing.override.set` | ✅ |
| **B2** | Store↔warehouse modeli online-sellable-stock saxlamır | 🟡 | **H5** — `warehouses.is_online_sellable` flag + `aggregate_online_stock` helper | ✅ |
| **B3** | `online-published` flag yox | 🟡 | **H5** — `products.online_published` (default false, explicit opt-in) | ✅ |
| **B4** | Channel schema yox (channels, channel_listings) | 🟡 | **H5** — `channels` + `channel_listings` (UNIQUE constraints, RLS) | ✅ |
| **B5** | Consume idempotency yox (`idempotency_keys` wiring) | 🔴 | **H4** — `idempotent(handler)` wrapper, `INSERT ... ON CONFLICT DO NOTHING` | ✅ |
| **B6** | Canonical mapper yox (ORM → CanonicalProduct) | 🟡 | **H5** — `sync/canonical.py`: pure helpers + `build_canonical_product` orchestrator | ✅ |

### Yeni çatdırılan modullar (AI-2.H daxilində)

| Modul | Faylı | Məqsəd |
|---|---|---|
| Idempotency wrapper | `services/core/app/idempotency.py` | Consume-side `event_id` dedup |
| Domain events | `services/core/app/domain/events.py` | Event tip-lərin mərkəzi siyahısı |
| Canonical mapper | `services/core/app/sync/canonical.py` | ORM → CanonicalProduct/Inventory/Price |
| Channel models | `models.py`-də `Channel`, `ChannelListing` | Per-channel variant mapping |

### Açıq qalan (AI-2.H sonrası, AI-2.5-yə qədər)

- ✅ **AI-2.H1 canlı yoxlama (operator smoke)** — Q-001 PASSED (2026-06-04, AI sessiya canlı icrası): (a) Keycloak parol substitusiyası + OIDC round-trip realm `posnet`-də access_token qaytardı (sub/exp/iat/realm_roles=[tenant_admin]); (b) `DATABASE_APP_URL` pool — `posnet_app` non-owner LOGIN tenant-suz 0 sətir, scope ilə öz tenant-ı, `posnet_resolve_tenant` SECURITY DEFINER, journal lockdown UPDATE/DELETE rədd, UNIQUE(tenant_id, sku) live, 3 CHECK constraint live. Detal: HUMAN-GATES.md → Q-001.
- ⏳ **GitHub CI billing** (HUMAN-ONLY, Q-002) — hesabda "failed payment" Actions runner-ləri dayandırır. **AI bu sahədə icra edə bilməz** (kart + GitHub Support ticket — operator). Lokal `make verify` + 443 test yaşıl, kod tərəfdən bloklamır; `v0.1.0-alpha` tag CI yaşıl olduqda çəkiləcək. Detal: HUMAN-GATES.md → Q-002.
- 🔮 **AI-2.5 ərzində açılır** (qətnamə H-də tutulmayıb, sonradan həll olunur):
  - FTS gin tenant-aware (per-tenant index hint)
  - Per-tenant + per-kanal rate-limit
  - Eventbus health (DLQ depth, queue lag metrik)
  - OTel trace propagation outbox → consumer → adapter
  - Aggregation override mexanizmi (per-channel buffer, safety-stock) — ADR-0018 §5 amendment
  - `channels.config` JSONB üçün Pydantic schema (adapter-spesifik)

### H1-H5 detalları (tarixi qeyd üçün — keçmişdən gələcəyə)

- [x] **AI-2.H1 🔴 Security posture** ✅ — 2026-06-03 (ADR-0017). RLS `FORCE` bütün policy cədvəllərinə (dinamik DO-loop) + `posnet_app` **non-owner LOGIN** rolu (NOSUPERUSER NOBYPASSRLS); **dual-pool**: app pool (`DATABASE_APP_URL`→posnet_app, per-request) + system pool (`DATABASE_URL`→superuser: migration/super_admin/relay/consumer/onboarding). Role-suz/tenant-siz sorğu **0 sətir** regression. `posnet_resolve_tenant` SECURITY DEFINER (sabit search_path, PUBLIC-dən REVOKE) — kilidli pool üçün tək cross-tenant subject→tenant. `realm-posnet.json` parolu → `${env.POSNET_OWNER_PASSWORD}` (compose dev default, A6). JWT `require_exp/iat/sub` + boş/whitespace sub rədd + audience enforce local/test xaricində (A7). migration **0009**; 14 yeni test → suite **365 @ 100%**. *(audit A1, A6, A7)*
- [x] **AI-2.H2 🔴 Data identity & invariant** ✅ — 2026-06-03. migration **0010**: `variants` köhnə `UNIQUE(product_id, sku)` → **`UNIQUE(tenant_id, sku)`** + partial **`UNIQUE(tenant_id, barcode) WHERE barcode IS NOT NULL`** (adapter contract-ları SKU-keyed, POS scan deterministik); `inventory` üç **CHECK** (`qty>=0`, `reserved_qty>=0`, `reserved_qty<=qty`) — domain `_effect`-dən kənar yol qalsa belə anti-oversell DB-də qoruyur; **journal lockdown** — `stock_movements`/`cash_movements`/`audit_logs`-dan `posnet_app` üzərində UPDATE+DELETE REVOKE (append-only, FK CASCADE owner-priv ilə işləyir). domain: `find_variant_by_sku/barcode` `ORDER BY id` deterministik backstop; `add_variant` flush IntegrityError → ConflictError (sku VƏ ya barcode); `apply_movement` ilk-yaranma race INSERT IntegrityError → ConflictError(409). 20 yeni test (19 integration + 1 unit) → suite **385 @ 100%**. *(audit A2, A3, A4, schema)*
- [x] **AI-2.H3 🔴 Anti-oversell proof** ✅ — 2026-06-04. **Real paralel-tx oversell** ([test_oversell_concurrency.py](tests/integration/test_oversell_concurrency.py)): 4 integration testi — 10 reservation 3 unit-ə (7 conflict), N=5/units=5 (hamısı ok), concurrent `out` 2 unit-ə (4 conflict, qty min 0), `expected_version` stale race deterministik loser. `SELECT FOR UPDATE` lock real `asyncio.gather` ilə sübut; CHECK DB belt-and-braces. **Hypothesis property-tests**: `_effect` üçün 10 invariant ([test_anti_oversell_properties.py](tests/unit/app/test_anti_oversell_properties.py)) — `qty>=0 ∧ reserved>=0 ∧ reserved<=qty` post-condition, hər kind üçün either-raises-or-preserves, in/out + reserve/unreserve + adjust round-trip, anti-oversell core; Money üçün 9 əlavə property test (sub identity, mul linearity, currency strictness, major round-trip). **Coverage-theater təmizlik (audit A5)**: `test_onboard_endpoint_builds_response` + `test_onboard_endpoint_maps_integrity_error_to_conflict` (monkeypatched fake-session) silindi — real integration `test_onboard_endpoint_super_admin_creates_tenant` + `_duplicate_subject_conflicts` (real TestClient + DB + JWT) eyni path-i tutur. **`make verify`-ə `test` əlavə** (lint + type + test + security). suite **406 @ 99.88%** (honest — pytest-cov async-greenlet `tenants.onboard` daxilini ölçə bilmir; integration tam çıxır). *(audit A4, A5)*
- [x] **AI-2.H4 🔴 Sync change-feed** ✅ — 2026-06-04. **Outbox event emit** (audit B1, [domain/events.py](services/core/app/domain/events.py) mərkəzi tip-lər): `catalog.product.created` (create_product), `catalog.variant.added` (add_variant), `inventory.movement.applied` (apply_movement — payload-da `new_qty`/`new_reserved_qty`/`version`), `pricing.override.set` (set_override). Hər emit business write ilə eyni tx-də (atomik — mutation fail-i event-i də rollback edir). **Consume idempotency** (audit B5, [idempotency.py](services/core/app/idempotency.py)): `idempotent(handler)` wrapper — `INSERT INTO idempotency_keys ... ON CONFLICT (key) DO NOTHING`; `rowcount==0` → handler skip (redelivery dedup); handler exception → tx rollback, key də silinir (retry mümkün). `create_app` default-da `idempotent(handler)` wrap edir. 8 yeni integration test → suite **414 @ 99.88%**. *(audit B1, B5)*
- [x] **AI-2.H5 🟡 Sync model enabler** ✅ — 2026-06-04 (ADR-0018). migration **0011**: `warehouses.is_online_sellable` (default true — mövcud anbarlar onlayn sayılır), `products.online_published` (default **false** — explicit opt-in, inadvertent push qarşısı), yeni iki cədvəl `channels` (UNIQUE tenant_id+code) və `channel_listings` (UNIQUE channel_id+variant_id, partial UNIQUE channel_id+external_listing_id non-NULL) — RLS FORCE + posnet_app grant. **Canonical mapper** ([sync/canonical.py](services/core/app/sync/canonical.py)): pure helper-lər (`aggregate_online_stock`, `to_canonical_inventory/price/product`) + orchestrator `build_canonical_product(session, variant_id, at)` — Variant+Product oxu, `online_published=false` → None, `is_online_sellable=true` anbarları aqreqasiya, `resolve_price`, ImageURL-lar (sort_order), `CanonicalProduct` qaytarır. `stock_qty=max(qty-reserved, 0)` — kanal heç vaxt mənfi görmür (canonical anti-oversell qatı). 29 yeni test (13 unit pure helper + 16 integration: schema default-ları, channel uniqueness, RLS isolation, mapper happy/edge path-lar, migration sanity) → suite **443 @ 99.88%**. *(audit B2, B3, B4, B6)*

**Hardening sonrası → AI-2.5** adapter framework + 1 kanal (mock-marketplace → real) təmizlənmiş təməl üstündə.

---

## Faza AI-2.5 — ADAPTER FRAMEWORK + 1 KANAL (★ HUB NÜVƏSİ, ADR-0012 §17)

**Məqsəd:** "Merchant məhsulunu kanala çıxarır, online satılır, sifariş POS-a düşür, stok hər yerdə azalır." Crown jewel — məhsul tezisini sübut edir.

**Dilimlər (incremental, hər biri öz commit-i ilə):**
- [x] **AI-2.5.1** ✅ — 2026-06-04. **Adapter contract** ([libs/adapter](libs/adapter)): `ChannelAdapter` Protocol (push_listing/push_stock/push_price/pull_orders/acknowledge_order/map_category) · `AdapterCapabilities` dataclass (code, auth_kind, supports_*, rate_limit_rps/burst, tags) · 4-tier error hierarchy (`AdapterError` → Retryable/RateLimit, Auth/Permanent — sync engine retry/DLQ classifier) · process-wide registry (`register_adapter/get_adapter/list_adapters/clear_registry`, code-mismatch + collision detection) · `ChannelListingResult` frozen dataclass. 34 yeni unit test → suite **477**. *(roadmap §17.2)*
- [x] **AI-2.5.2** ✅ — 2026-06-04. **Sync dispatcher** ([services/core/app/sync/dispatcher.py](services/core/app/sync/dispatcher.py)): `SyncDispatcher` EventHandler — outbox event → adapter operation routing. Event tip map: `catalog.variant.added` → push_listing (online_published gate + channel_listings create), `inventory.movement.applied` → push_stock (new_qty - new_reserved), `pricing.override.set` → push_price (resolve_price). **Per-channel token-bucket rate limit** ([libs/adapter/rate_limit.py](libs/adapter/rate_limit.py)): async, fair, monotonic clock, asyncio.timeout-based. **Async circuit breaker** ([libs/adapter/circuit_breaker.py](libs/adapter/circuit_breaker.py)): hand-rolled CLOSED → OPEN → HALF_OPEN state machine — pybreaker 1.0 `call_async` bug-ı vardı (Tornado-asılı gen.coroutine import-suz). Error classification: Retryable → re-raise (consumer backoff); Auth/Permanent → log + swallow (reconciliation 5.6 catches up); Breaker open → silent skip. 24 yeni test (7 rate limit + 7 breaker + 10 dispatcher integration) → suite **501** (dispatcher.py 94.4%). *(roadmap §17.3 outbound)*
- [x] **AI-2.5.3** ✅ — 2026-06-04. **Mock marketplace** ([mocks/mock_marketplace/](mocks/mock_marketplace)): standalone FastAPI app (`create_app`) — `POST /listings` (upsert idempotent by seller_sku → external_listing_id `MOCK-{hex}`), `PATCH /listings/{sku}/stock`, `PATCH /listings/{sku}/price`, `GET /orders?since=`, `POST /orders/{id}/ack`, `POST /_test/orders` (test seed). In-memory `MockStore` (per-app isolated). **MockMarketplaceAdapter** ([services/core/app/adapters/mock_marketplace/](services/core/app/adapters/mock_marketplace)): ChannelAdapter Protocol satışı, httpx async client (config-driven, ASGI transport test-friendly). HTTP error → AdapterError classification (5xx → Retryable, 429 → RateLimit + Retry-After, 401/403 → Auth, 4xx → Permanent, timeout/transport → Retryable). **Adapter contract test template** ([tests/contract/adapter_contract.py](tests/contract/adapter_contract.py)): abstract `AdapterContractTests` pytest class — capabilities present + class-level, push_listing returns one-per-input + idempotent on SKU, push_stock/push_price success returns None, map_category pure + empty-path stable. 27 yeni test (9 mock service + 8 contract suite via subclass + 10 mock-specific including 5 error classification with synthetic transports) → suite **528** @ 86.2%. *(§17.5)*
- [x] **AI-2.5.4** ✅ — 2026-06-04. **Webhook ingress** ([services/core/app/api/v1/webhooks.py](services/core/app/api/v1/webhooks.py)): `POST /v1/channels/{tenant_id}/{code}/webhook` (channel code per-tenant UNIQUE → tenant_id URL-də). **HMAC verify** ([libs/adapter/hmac_verify.py](libs/adapter/hmac_verify.py)): constant-time `hmac.compare_digest`, `sha256=<hex>` Stripe-style + bare hex. **Protocol extended**: `normalize_webhook(body, headers) → CanonicalOrder` (pure, sync); `AdapterCapabilities.webhook_signature_header` (per-channel HMAC header name). **MockMarketplaceAdapter** updated: capabilities.supports_webhook_orders=True, `X-Mock-Signature` header, normalize_webhook (json.loads → OrderDTO shape → `_normalise_order`). **Migration 0011** → **0012**: `channel_orders` (tenant_id, channel_id, channel_order_id UNIQUE per channel, canonical_payload JSONB, status [received/reserved/fulfilled/rejected], received_at) — RLS FORCE + posnet_app grant. **Idempotency:** `UNIQUE(channel_id, channel_order_id)` SAVEPOINT pattern — redelivered webhook → 200 OK status=duplicate (no second row). **Status codes:** 200 ok/duplicate, 401 bad/missing HMAC, 404 channel not found / inactive, 400 malformed body (AdapterPermanentError), 503 secret/factory not configured. 16 yeni test (7 HMAC unit + 9 integration: happy + idempotent + 2 HMAC failure + 2 channel lookup + secret-missing + body-malformed + factory-unwired) → suite **544** @ 83.4%. *(§17.3 inbound)*
- [ ] **AI-2.5.5** E2E MVP — POS məhsul → push_listing → mock görür → stok/qiymət dəyiş push → mock sifariş webhook → POS stok azalır → ack. **0 oversell**. *(§17.6)*
- [ ] **AI-2.5.6** Reconciliation cron + OTel observability — kanal stoku vs POS drift təpib + təmir; sync metrik (lag, push success rate, DLQ depth). *(§17.4)*

**Gate (AI-2.5 done):** adapter kontraktı + mock contract test 100% · E2E dilim idempotent **0 oversell** · reconciliation drift təmir · rate-limit + retry + DLQ test · OTel sync metrik · swap-ready (real adapter eyni kontrakt).

---

## Faza AI-2 — POS CORE / online qat (2.1–2.4 ✅ + AI-2.H ✅; sale = AI-2.5-ə köçdü)

**Məqsəd:** Catalog + inventory + pricing + shift + sale = **canonical tək həqiqət mənbəyi** (hub-a hazır).
**Hardening sonrası vəziyyət:** schema + canonical mapper + outbox change-feed artıq hazırdır; AI-2.5 sale yolunu və 1 real kanal-ı bağlayır.

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

**Follow-up (G2-yə qədər həll — AI-2.H sonrası vəziyyət):**
- AI-2.1: `/variants/lookup` cavabına `currency` (+ product_name) əlavə (POS qiymət göstərimi); `list_products` paginasiya. ~~`UNIQUE(tenant_id, barcode)` partial constraint~~ ✅ **H2-də həll** (migration 0010)
- AI-2.2: `transfer` movement (2 warehouse atomik). ~~inventory ilk-yaranma konkurent race~~ ✅ **H2-də həll** (IntegrityError → ConflictError 409)
- **GitHub CI:** hesab "failed payment" blokunu həll et (billing) — sonra push + CI yaşıl + `v0.1.0-alpha` tag

**GATE G2:** məhsul yarat→barkod axtar→satış→stok düş E2E · canonical map · coverage ≥80% (pul path 95%) · make verify · CI yaşıl.

---

## Schema xəritəsi (cari) — migration 0001-0011

Hər migration nə əlavə etdi (`services/core/alembic/versions/`):

| # | Faza | Mövzu | Əsas cədvəl/dəyişiklik |
|---|---|---|---|
| 0001 | AI-1.5 | Identity (9 cədvəl) | tenants, stores, users, roles, permissions, user_roles, audit_logs, idempotency_keys, outbox_events |
| 0002 | AI-1.6 | RLS | `posnet_app` role, `tenant_isolation` policy hər identity cədvəlinə |
| 0003 | AI-1.9.3 | Tenant resolver | `users.external_subject` qlobal unique (ADR-0015) |
| 0004 | AI-1.17 | Feature flags | `feature_flags(tenant_id, key, enabled)` + RLS + grant |
| 0005 | AI-2.1 | Catalog | products + variants + product_images, FTS gin index |
| 0006 | AI-2.2 | Inventory | warehouses + inventory + stock_movements + version optimistic lock |
| 0007 | AI-2.3 | Pricing | `price_overrides(tenant_id, variant_id, store_id?, valid_from/to)` |
| 0008 | AI-2.4 | Shifts | `shifts` + partial UNIQUE açıq vardiya + `cash_movements` |
| **0009** | **AI-2.H1** | **Security posture (A1)** | `posnet_app` non-owner LOGIN, RLS **FORCE** dinamik DO-loop, `posnet_resolve_tenant()` SECURITY DEFINER |
| **0010** | **AI-2.H2** | **Data identity (A2/A3/A4)** | `variants` `UNIQUE(tenant_id, sku)` + partial `UNIQUE(tenant_id, barcode)`, `inventory` 3 CHECK, journal lockdown REVOKE UPDATE/DELETE |
| **0011** | **AI-2.H5** | **Sync model (B2/B3/B4)** | `warehouses.is_online_sellable`, `products.online_published`, `channels`, `channel_listings` |

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
