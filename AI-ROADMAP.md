# AI-ROADMAP — Posnet Platforması

**Vahid İcra İstinad Sənədi — Claude Opus üçün**

**Versiya:** 4.0 (1 İyun 2026 — POS-anchored İnteqrasiya Hub modelinə yenidən yazıldı)
**Status:** ACTIVE — beachhead-first icra üçün hazırdır
**İcra modeli:** AI-autonomous (1 AI + 1 insan operator)
**Əvvəlki:** v3.0 (8-fazalı, all-channels waterfall) — git tarixində; ADR-0011 + ADR-0012 ilə əvəz olundu

> ⚠️ **SCOPE — ADR-0012: POS-anchored İnteqrasiya Hub.** Məhsul = POS (tək həqiqət mənbəyi)
> + marketplace/delivery/booking inteqrasiya hub-ı (TSoft/Entegra/ChannelEngine modeli).
> **Beachhead:** Azərbaycan · pərakəndə · ilk kanal = Birmarket/Trendyol (marketplace).
> **Aktiv yol:** AI-0 → AI-1 → AI-2 → **AI-2.5 (adapter framework + 1 kanal)** → **G-V validasiya**.
> **Dondurulub (G-V sonrası):** 2-ci kanal, delivery & booking domain, fiskal, accounting, multi-country, cloud, TR.
> Dəyişiklik yeni ADR tələb edir. Detal: `docs/adr/0012-integration-hub-reframe.md`.

---

# PART I — VİZYON VƏ MODEL

## 1. Layihə Vizyonu

**Posnet — POS-anchored omnichannel inteqrasiya hub-ı.**

Sahibkar öz fiziki mağazasını Posnet POS-da idarə edir; **bir paneldən** öz məhsullarını
marketplace, delivery və booking portallarına çıxarır; bütün online sifarişlər vahid yerə
düşür; stok/qiymət hər kanalda avtomatik sinxron olur.

```
            [ POS = tək həqiqət mənbəyi ]
       məhsul · qiymət · stok · vardiya · çek
                       │
         ┌─────────────┼─────────────┐  ← Posnet Hub (canonical model + adapterlər + sync engine)
         ▼             ▼             ▼
    MARKETPLACE     DELIVERY       BOOKING
    Birmarket       Wolt           (rezervasiya/
    Trendyol        Bolt Food       appointment)
    Hepsiburada     Yemeksepeti
         │             │             │
         └─────────────┼─────────────┘
                       ▼
   [ Vahid sifariş paneli → geri POS-a + stok hər yerdə azalır ]
```

**Dəyər təklifi:** "Mağazanı 1 saata online-a çıxar, oversell olmadan bütün kanalları tək yerdən idarə et."

**Tip:** Multi-tenant SaaS · modular monolit · event-driven · adapter-first

## 2. Posnet-in Bazar Mövqeyi

Bu bazarda 3 oyunçu tipi var — Posnet ikisini birləşdirir:

| Oyunçu tipi | Nümunə | Var | Yox |
|---|---|---|---|
| Pure-play integrator | Entegra, Sentos, TSoft, ChannelEngine, Linnworks | Çoxlu kanal sync | POS, fiziki mağaza, fiskal |
| POS / ÖKC vendor | lokal AZ/TR kassa firmaları | Fiziki satış, fiskal | Yaxşı çoxkanallı hub |
| **POS + Hub (Posnet)** | (Square + ChannelEngine kombinasiyası) | **Hər ikisi + fiskal** | — |

**Fərqləndirici (wedge):** Pure-play integratorların POS-u yox (mövcud e-mağaza/ERP-dən
başlayırlar); lokal POS vendorların yaxşı hub-ı yox. Posnet fiziki mağazadan başlayıb
online-a çıxarır + lokal fiskal uyğunluq.

**Dünya referansları (arxitektura nümunəsi):**
- **Marketplace:** ChannelEngine (1300+ kanal), Linnworks, ChannelAdvisor/Rithum, TSoft, Entegra
- **Delivery:** Wolt/Bolt Food/Yemeksepeti (Menu+Order API; OAuth2/JWT)
- **Booking:** SiteMinder (otel channel manager, 350+ bağlantı; availability/rate push + rezervasiya pull)
- **Vahid pattern:** canonical model + event-driven + idempotent + orchestration + observability (MACH/iPaaS)

## 3. Beachhead (ADR-0012)

| Ölçü | Qərar | Səbəb |
|---|---|---|
| Coğrafiya | **Azərbaycan** | Ev sahəsi; kanallar konsolidasiya (Birmarket+Trendyol); integrator rəqabəti az |
| Merchant | **Pərakəndə (market/butik)** | SKU/barkod-mərkəzli; marketplace üçün təbii |
| İlk kanal | **Birmarket / Trendyol** (marketplace) | Birmarket (ex-Umico) = AZ #1; Trendyol public API sənədli |
| Canonical model | SKU/barkod-mərkəzli | İlk adapteri və data modelini müəyyən edir |

**AZ kanal mənzərəsi:** Marketplace — Birmarket, Trendyol AZ · Delivery — Wolt, Bolt Food, Yango ·
Booking — (sonra). Az sayda kanal = asan beachhead.

**TR (sonra):** Trendyol, Hepsiburada, Yemeksepeti, Getir — nəhəng amma 14+ pure-play integrator ilə qızğın rəqabət.

## 4. 12 LOCKED Texniki Qərar

Dəyişməz — yalnız ADR + insan icazəsi ilə.

| # | Sahə | Qərar |
|---|---|---|
| 1 | Arxitektura | **POS nüvə + adapter-first inteqrasiya hub** (canonical model + sync engine) |
| 2 | Backend | Python 3.12+ / FastAPI |
| 3 | Pul | `Decimal` / integer minor units (qəpik itirməmək) |
| 4 | DB | PostgreSQL 16+ + RLS + JSONB |
| 5 | Messaging | pgmq + Outbox + EventBus abstraksiyası (hub onurğası) |
| 6 | Kassir | Flutter (offline-first, SQLite) |
| 7 | Web | TypeScript + React (admin) / Next.js (storefront, sonra) |
| 8 | Secrets | Vault/KMS (kodda yox) |
| 9 | Xarici giriş | Zero-trust + HMAC + JSON Schema + idempotency |
| 10 | Ödəniş | Kart saxlanmır, PSP tokenizasiya |
| 11 | Auth | Keycloak (OIDC) + RBAC + MFA |
| 12 | Broker | pgmq default; yalnız sübut olunmuş darboğazda Kafka |

## 5. Bounded Context-lər (12) — aktiv vs təxirdə

| # | Context | Beachhead-də |
|---|---|---|
| 1 | Identity & Access | ✅ AKTİV (AI-1) |
| 2 | Catalog | ✅ AKTİV (AI-2) |
| 3 | Inventory | ✅ AKTİV (AI-2) |
| 4 | Pricing | ✅ AKTİV (AI-2, sadə) |
| 5 | Sales/POS | ✅ AKTİV (AI-2) |
| 6 | **Integration** | ✅ AKTİV (AI-2.5) — **hub nüvəsi** |
| 7 | Order Management | 🔶 minimal (AI-2.5: kanal sifarişi ingest) |
| 8 | Payments | ❄️ təxirdə |
| 9 | Accounting | ❄️ təxirdə |
| 10 | CRM/Loyalty | ❄️ təxirdə |
| 11 | Notification | ❄️ təxirdə (AI-2.5: minimal sifariş bildirişi) |
| 12 | Analytics/Reporting | ❄️ təxirdə |

## 6. AI İcra Modeli — Aktyorlar

| Aktyor | Rolu | Edə bilər | Edə bilməz |
|---|---|---|---|
| **Claude Opus** | Full-stack dev + arxitekt + QA + DevOps | Kod, test, schema, migration, infra-as-code (plan), adapter, mock, sənəd, debug | Kart, müqavilə, **partner API müraciəti**, fiskal cihaz, prod deploy |
| **İnsan operator** | PM + Gate-keeper + Compliance | Hesab, kart, domain, **Birmarket/Trendyol API access**, müsahibə, gate icazəsi, sirr | Kod (məcburi deyil) |
| **GitHub Actions** | CI | Lint, type, test, security, build | Auto-deploy |

---

# PART II — STACK VƏ STRUKTUR

## 7. Texnoloji Stack (LOCKED)

| Sahə | Qərar | Versiya |
|---|---|---|
| Backend | Python + FastAPI | 3.12 / 0.115+ |
| DB | PostgreSQL + RLS + pgmq + JSONB | 16+ |
| Migrations | Alembic | latest |
| Cache | Redis | 7+ |
| Queue | pgmq | 1.x |
| Auth | Keycloak (OIDC) | 25.x |
| Secrets | HashiCorp Vault | 1.15+ |
| Kassir | Flutter (offline-first) | 3.24+ |
| Frontend | TypeScript + React (admin) | — |
| Schema | Pydantic v2 | 2.6+ |
| HTTP klient (adapter) | httpx + tenacity + pybreaker | — |
| Container | Docker + Compose (lokal) / K8s (cloud, sonra) | — |
| Observability | OTel + Prometheus + Grafana + Jaeger + Loki | — |
| Test | pytest + pytest-asyncio + testcontainers + schemathesis + hypothesis + locust | — |
| Type/Lint | mypy --strict + ruff + black | — |
| Security | bandit + detect-secrets + pip-audit | — |

## 8. Monorepo Strukturu (libs = crown jewel)

```
posnet/
├── CLAUDE.md · AI-ROADMAP.md · STATUS.md · HUMAN-GATES.md · README.md
├── docs/adr/  (0001–0012)  · docs/runbooks/ · docs/openapi/ · docs/asyncapi/ · docs/threat-model/
│
├── libs/                          ← ★ HUB NÜVƏSİ — ən yüksək dəyər
│   ├── canonical_model/           ← kanal-agnostik Pydantic schemalar (Product/Order/Inventory/Price)
│   ├── adapter/                   ← adapter kontraktı (Protocol/ABC) + contract test şablonu + registry
│   ├── eventbus/                  ← pgmq + Outbox + DLQ + retry (hub onurğası)
│   ├── auth/                      ← Keycloak JWT + JWKS cache
│   ├── observability/             ← OTel + Prometheus + Loki
│   ├── i18n/ · feature_flags/
│   └── common/                    ← logger, errors, types (Money), request-id
│
├── services/
│   ├── core/                      ← POS monolit (Identity+Catalog+Inventory+Pricing+Sales)
│   │   └── app/{main.py, api/v1/, domain/, infrastructure/, middleware/}
│   ├── marketplace-svc/           ← marketplace adapterləri (Birmarket, Trendyol)
│   │   └── adapters/{birmarket/, trendyol/}
│   ├── webhook-ingress/           ← kanal webhook qəbulu (HMAC) → eventbus
│   ├── delivery-svc/ · booking-svc/ · notification-svc/   ← ❄️ təxirdə
│
├── apps/  (pos-flutter ❄️ · admin-web · storefront ❄️)
├── mocks/  (mock-marketplace ★ = mock Birmarket; mock-courier/psp/efaktura/fiscal ❄️)
├── infra/  (postgres · keycloak · prometheus · grafana · loki · otel · caddy · terraform ❄️)
├── tests/  (unit · integration · contract · e2e · load)
└── scripts/  · .github/workflows/
```

## 9. Sirr İdarəsi (məcburi)

- AI **heç vaxt** sirri kodda/log-da/commit-də yazmasın
- `.env.example` placeholder; `.env` `.gitignore`-da; hər sirr Vault-da, kod yalnız `vault://path` ref
- **Kanal sirləri:** hər adapter üçün `secret/posnet/channels/{code}/{api_key,hmac}` — insan Vault-a yazır
- `detect-secrets` pre-commit hook məcburi

---

# PART III — PROSES

## 10. Faza Asılılıq Diaqramı (hub sequence)

```
   PREFLIGHT (insan) → AI-0 BOOTSTRAP → G0
                            ↓
                       AI-1 FOUNDATION (auth + tenant + RLS + ★eventbus★) → G1
                            ↓
                       AI-2 POS CORE (catalog + inventory + pricing + sale = canonical mənbə) → G2
                            ↓
                       AI-2.5 ★ ADAPTER FRAMEWORK + BİRMARKET (mock) + SYNC ENGINE
                            ↓
                       ═══ MVP DİLİMİ ═══  (məhsul → kanal → stok sync → sifariş ingest)
                            ↓
                       G-V VALİDASİYA (retail satıcı demo; kill/continue)
                            ↓
   ❄️ POST-G-V: real Birmarket swap → 2-ci kanal → delivery → booking → fiskal → accounting → TR → cloud
```

**Paralel insan trekləri (AI-2.5 ilə eyni vaxtda):**
1. Retail satıcı müsahibələri (validation toolkit)
2. Birmarket/Trendyol seller API access (partner gate D-002)

## 11. Sessiya Protokolu + Task Dövrü

**Hər sessiya:** CLAUDE.md → STATUS.md → AI-ROADMAP.md (cari faza) → HUMAN-GATES.md → (HANDOFF.md varsa).

**Task dövrü:**
```
1. STATUS.md → cari task
2. Mövcud kodu axtar (Glob/Grep) — dublikat yox
3. Acceptance test ƏVVƏL (TDD)
4. İmplementasiya
5. make verify — keçməsə fix, 3 cəhd, sonra STOP
6. Self-review + commit (Conventional Commits)
7. STATUS.md yenilə → növbəti task və ya Gate-də DAYAN
```

**Self-review (commit öncəsi):** make verify ✅ · detect-secrets ✅ · ölü kod yox · type-hint hər funksiyada ·
OpenAPI yeni · yeni env var `.env.example`-da · yeni dep pin-li · yeni qərar ADR-da.

## 12. Human Gate Davranışı + Kontekst Budcəsi

**AI DAYANIR:** `requires_human` task · 3 cəhddən sonra fail · yeni external dep seçimi · faza gate (G0/G1/G2/G-V) ·
sirr yaradılması · **partner API müraciəti**.
→ STATUS.md `BLOCKED`, HUMAN-GATES.md `Q-NNN`, sessiyanı bitir.

**Kontekst:** <50% normal · 50-70% yeni böyük task başlama · 70-85% HANDOFF + commit · >85% dərhal HANDOFF.

## 13. NFR Hədəflər (aktiv fazalar)

| Faza | Metrik | Hədəf | Ölçü |
|---|---|---|---|
| AI-1 | Auth middleware overhead | < 20ms p95 | OTel |
| AI-1 | RLS query overhead | < 10ms | EXPLAIN ANALYZE |
| AI-1 | pgmq publish latency | < 100ms p95 | DB trace |
| AI-1 | Test coverage (core) | ≥ 80% | pytest-cov |
| AI-2 | Catalog list API p95 | < 300ms (≤1000 məhsul) | OTel |
| AI-2 | Stock movement write | < 50ms | DB trace |
| AI-2.5 | Stok/qiymət push p95 | < 5s (POS dəyişiklik → kanal) | OTel |
| AI-2.5 | Sifariş ingest p95 | < 5s (webhook → POS görünür) | OTel |
| AI-2.5 | Oversell hadisəsi | **0** (idempotency + reconciliation) | reconciliation cron |
| AI-2.5 | Adapter contract test | 100% (şablon + Birmarket mock) | CI gate |

---

# PART IV — AKTİV FAZA İCRASI

## 14. AI-0: BOOTSTRAP (icrada — 2/11)

**Məqsəd:** Boş qovluqdan `make verify` keçən karkas + Docker stack.

| Task | Status |
|---|---|
| AI-0.1 Monorepo skeleton + git | ✅ |
| AI-0.2 Python tooling (pyproject + Makefile + pre-commit) | ✅ |
| **AI-0.3 Docker stack: postgres(pgmq)+redis+vault+keycloak** | ⏭️ NÖVBƏTİ |
| AI-0.4 Observability stack (jaeger+prometheus+grafana+loki+otel) | ⏳ |
| AI-0.5 Dev infra (mailpit+minio+caddy+mkcert) | ⏳ |
| AI-0.6 Frontend tooling (pnpm workspace) | ⏳ |
| AI-0.7 Flutter skeleton (gec OK) | ⏳ |
| AI-0.8 GitHub Actions CI (lint+test+security+build) | ⏳ |
| AI-0.9 ADR + runbook template | ⏳ (ADR-0010/0011/0012 mövcud) |
| AI-0.10 CLAUDE.md tamamla | ⏳ |
| AI-0.11 Smoke: make bootstrap | ⏳ |

**AI-0.3 qeyd:** `pgmq` standart Postgres-də YOXDUR → pgmq-enabled image (`ghcr.io/pgmq/pg16-pgmq`
və ya `quay.io/tembo/pg16-pgmq`) istifadə et; `init.sql`: `CREATE EXTENSION pgmq; CREATE EXTENSION pg_trgm`.

**GATE G0:** make bootstrap keçir · docker-compose ps healthy · CI yaşıl · STATUS `AI-0 done`.

## 15. AI-1: FOUNDATION

**Məqsəd:** Auth + multi-tenant + RLS + DB + **eventbus (hub onurğası)** + observability.

### Identity schema (kompakt — tam DDL migration-da, TDD)
`tenants(id, name, country_code, plan, status)` · `stores(id, tenant_id, name, timezone, open_status)` ·
`users(id, tenant_id, email, phone, mfa_enabled, UNIQUE(tenant_id,email))` · `roles` · `permissions(role_id, resource, action)` ·
`user_roles(user_id, role_id, store_id NULL=tenant-wide)` · `audit_logs(BIGSERIAL, tenant_id, actor, action, target, meta_jsonb)` ·
`idempotency_keys(key PK, tenant_id, result_ref)` · `outbox_events(id, tenant_id, event_type, payload, published)`.

**RLS:** hər tenant-cədvəlində `USING (tenant_id = current_setting('app.current_tenant')::uuid)`.
**Pulu:** integer minor units. **Vaxt:** `TIMESTAMPTZ` (naive yox — ruff DTZ qaydası).
**RBAC:** super_admin (system) · tenant_admin · store_manager · cashier · clerk.
**Error:** RFC 7807 problem+json (type/title/status/detail/instance/trace_id).

**Middleware ardıcıllığı:** RequestId → Logging → Tracing → Auth(JWT/JWKS) → TenantContext(SET LOCAL) → RateLimit → ErrorHandler.

### Tasklar (kritiklər)
- **AI-1.1** Test infra + coverage gate 80% (FIRST) · conftest + testcontainers
- **AI-1.2** `libs/common` (logger, errors, types/Money, request-id)
- **AI-1.3** Vault setup + `get_secret()` helper
- **AI-1.4** `libs/canonical_model` skeleton (CanonicalBase) — **hub üçün erkən**
- **AI-1.5** SQLAlchemy models + Alembic + migration 0001 (identity)
- **AI-1.6** RLS policies migration 0002 + cross-tenant izolasiya testi
- **AI-1.7** Keycloak realm + 3 client + 4 role + test user
- **AI-1.8** `libs/auth` (JWT verify + JWKS Redis cache + require_permission)
- **AI-1.9** FastAPI app + middleware stack
- **AI-1.10** Global error handler (RFC 7807)
- **AI-1.11** Tenant context middleware (RLS injection)
- **AI-1.12** CORS + security headers (HSTS/CSP) + rate limiter (slowapi+Redis)
- **AI-1.13** OTel + Prometheus + Grafana + Loki (end-to-end trace)
- **AI-1.14 ★** `libs/eventbus`: pgmq publisher + Outbox worker + consumer + retry(backoff) + DLQ — **hub onurğası, prioritet**
- **AI-1.15** Tenant onboarding API + ilk tenant seed
- **AI-1.16** User/Role/Permission CRUD
- **AI-1.17** Feature flags + i18n backend
- **AI-1.18** Health probes (`/healthz`,`/readyz`) + graceful shutdown + DB pool + backup

**GATE G1:** servislər healthy · make verify (coverage ≥80%) · CI yaşıl · OIDC round-trip · RLS izolasiya ·
migration up/down/up · **pgmq publish→consume→DLQ** · OpenAPI + RFC 7807 · OTel trace · Vault secret · rate limit (101→429) · tag `v0.1.0-alpha`.

## 16. AI-2: POS CORE (retail beachhead)

**Məqsəd:** Catalog + inventory + pricing + shift + sale = **canonical tək həqiqət mənbəyi** (hub-a hazır).

### Schema (kompakt)
**Catalog:** `products(id, tenant_id, store_id, name, brand, category_path, status)` ·
`variants(id, product_id, sku, barcode, name, attributes_jsonb, base_price_minor, cost_price_minor, UNIQUE(product_id,sku))` ·
`product_images(product_id, url, sort_order)`. İndekslər: `gin(to_tsvector(name))`, `variants(barcode)`, `variants(sku)`.

**Inventory:** `warehouses(id, tenant_id, type)` · `inventory(variant_id, warehouse_id, qty, reserved_qty, min_qty, version optimistic-lock, UNIQUE(variant_id,warehouse_id))` ·
`stock_movements(id, tenant_id, variant_id, warehouse_id, type[in/out/transfer/adjust/reserve/unreserve], qty, reference, moved_at)`.

**Sales:** `shifts/vardiya(id, store_id, cashier_id, opened_at, closed_at, opening_cash, closing_cash)` ·
`sales/çek(id, tenant_id, store_id, shift_id, total_minor, status, created_at)` · `sale_lines(sale_id, variant_id, qty, unit_price_minor, line_total_minor)` ·
`pricing` (sadə: variant base_price + opsional rule). X/Z report (vardiya cəmləri).

### Tasklar (kritiklər)
- AI-2.1 Catalog domain + CRUD API (product/variant/barkod axtarış)
- AI-2.2 Inventory domain (stock movement journal + optimistic lock + reserve/unreserve)
- AI-2.3 Pricing (sadə: base price + currency; rule engine sonra)
- AI-2.4 Shift (vardiya aç/bağla) + cash management
- AI-2.5-POS Sale (çek yarat → stok düş → atomik) + X/Z report
- AI-2.6 **CanonicalProduct/Inventory/Price map** — catalog ↔ canonical_model (hub üçün kritik)
- AI-2.7 Admin-web minimal: məhsul/stok idarəsi (React)
- AI-2.8 Flutter kassir minimal (offline-first satış) — opsional, gec OK

**Qeyd:** Bu fazada **fiskal MOCK** (mock-fiscal); real OPK G-V sonrası. Pul math `hypothesis` property-test ilə.

**GATE G2:** məhsul yarat→barkod axtar→satış→stok düş E2E · canonical map işləyir · coverage ≥80% (pul path 95%) · make verify · CI yaşıl.

## 17. AI-2.5 ★ ADAPTER FRAMEWORK + BİRMARKET (HUB NÜVƏSİ)

**Məqsəd:** "Merchant məhsulunu kanala çıxarır, online satılır, sifariş POS-a düşür, stok hər yerdə azalır."
Bu faza **bütün məhsul tezisini** sübut edir. Crown jewel.

### 17.1 Canonical model (`libs/canonical_model`)
Kanal-agnostik Pydantic v2 (frozen): `CanonicalProduct(sku, barcode, name, attributes, category_path, price_minor, currency, stock_qty, images, status)` ·
`CanonicalInventory(sku, qty, reserved)` · `CanonicalPrice(sku, price_minor, currency)` ·
`CanonicalOrder(channel_order_id, lines[], customer, totals, status, fulfillment)`. Versiyalı (`v1`).

### 17.2 Adapter kontraktı (`libs/adapter`)
Hər kanal = bu Protocol-u implement edən 1 adapter:
```
class ChannelAdapter(Protocol):
    capabilities: AdapterCapabilities          # auth tipi, rate limit, push/pull dəstəyi
    async def push_listing(products) -> list[ChannelListingId]
    async def push_stock(sku, qty) -> None
    async def push_price(sku, price) -> None
    async def pull_orders(since) -> list[CanonicalOrder]   # və ya webhook ingest
    async def acknowledge_order(channel_order_id, status) -> None
    def map_category(canonical_category) -> ChannelCategory
```
**Contract test şablonu:** hər adapter eyni `tests/contract/adapter_contract.py`-dan keçməlidir (schemathesis + Pact tərzi).
**Registry:** adapterlər `register_adapter(code, cls)` ilə qeydiyyatdan keçir; "yeni kanal = 1 adapter + contract test".

### 17.3 Sync engine
**Outbound (POS → kanal):** POS-da məhsul/stok/qiymət dəyişikliyi → Outbox event → sync worker →
`adapter.push_*`. Idempotent (idempotency_key), per-channel rate-limit (slowapi/token-bucket), retry exponential backoff, **pybreaker** circuit breaker, fail → DLQ.
**Inbound (kanal → POS):** `webhook-ingress` (HMAC verify) → eventbus → `adapter.normalize` → `CanonicalOrder` →
Order context → POS-da stok reserve/decrement → `acknowledge_order`. Idempotent (təkrar webhook = 1 sifariş).
**Mapping:** `channel_product_map(sku ↔ listing_id)` · `channel_category_map` · `channel_attribute_map`.

### 17.4 Etibarlılıq (1-ci gündən — reputasiya)
- **Anti-oversell:** reservation + `inventory.version` optimistic lock; sifariş gələndə bütün kanallarda stok azalır
- **Reconciliation:** cron — kanal stoku vs POS stoku drift yoxla → təmir + alert
- **Observability:** OTel span per sync op (`channel.push`, `channel.ingest`); metriklər: sync lag, push success rate, DLQ depth
- **Idempotency + event sequencing** (drift-in qarşısı — dünya nümunəsi)

### 17.5 Mock Birmarket adapter (`mocks/mock-marketplace`)
Real Birmarket seller API-ni təqlid edən **real FastAPI servisi**: listing endpoint, stock/price update,
order webhook (HMAC), realistik davranış (latency, occasional 5xx, rate limit). İnsan asılılığını **bloklamır**.
Real credential gələndə: `services/marketplace-svc/adapters/birmarket/` real adapter eyni kontrakta yazılır, mock → real swap.

### 17.6 MVP dilimi (acceptance)
1. POS-da məhsul yarat (canonical mənbə)
2. Birmarket-ə listing (`push_listing`) → mock Birmarket-də görünür
3. POS-da stok/qiymət dəyiş → Birmarket-ə sync (`push_stock`/`push_price`)
4. Mock Birmarket-də sifariş → webhook → `CanonicalOrder` → POS → **stok hər yerdə azalır** (anti-oversell)
5. Sifariş status geri (`acknowledge_order`)

**GATE (AI-2.5 done):** adapter kontraktı + Birmarket mock contract test 100% · E2E dilim idempotent, **0 oversell** ·
reconciliation injected drift-i tapıb təmir edir · rate-limit + retry + DLQ test · OTel trace + sync metriklər ·
swap-ready (real adapter = eyni kontrakt).

## 18. G-V — VALİDASİYA GATE (ADR-0011/0012)

AI-2.5 MVP-dən sonra, genişlənmədən ƏVVƏL:
- MVP-ni operator-un retail satıcılarına (5–10) demo et ("məhsulunu Birmarket-ə 5 dəqiqəyə çıxar")
- Strukturlaşmış geri-bildirim (validation toolkit)

**Kill / Continue:**
- [ ] ≥ 5 satıcı MVP gördü
- [ ] ≥ 3 satıcı konkret ağrı + ödəmə istəyi ("istifadə edərdim")
- [ ] ≥ 1 satıcı pilot razılığı
- [ ] Qiymət hipotezi ≥ 3 satıcıda rədd olunmadı

✅ → genişlənmə açılır · ❌ → narrow / pivot.

---

# PART V — DONDURULMUŞ / GƏLƏCƏK (G-V sonrası, qısa)

G-V keçənə qədər **başlanmır**. Detal həmin faza açılanda ayrıca planning sessiyasında yazılacaq.

| Sahə | Qısa məzmun | Referans pattern |
|---|---|---|
| **Real Birmarket/Trendyol** | mock → real adapter swap (partner credential gələndə) | TSoft/Entegra |
| **2-ci marketplace** | Trendyol (və ya əksinə) — eyni kontrakta 2-ci adapter | ChannelEngine |
| **Delivery domain** | kafe/restoran üçün; menyu sync + sifariş injection + KDS/status | Wolt Menu/Order API |
| **Booking domain** | availability/rate push + rezervasiya pull + channel mapping | SiteMinder (channel manager) |
| **Fiskal** | real OPK/e-Kassa (AZ) — pilotdan əvvəl məcburi | — |
| **Accounting** | double-entry ledger + faktura + e-invoice | — |
| **Multi-country** | TR genişlənmə (config-driven) + KVKK | — |
| **Cloud + DR** | K8s + Helm + Terraform apply + RPO/RTO | — |

**Diqqət:** delivery (kafe) və booking — hub-ın eyni nümunəsi (canonical + adapter + sync), sadəcə fərqli kanal.
Marketplace adapteri qurulandan sonra bunlar daha ucuzdur.

---

# PART VI — ƏLAVƏLƏR

## 19. Glossariy (qısa)

ADR (Architecture Decision Record) · Bounded Context (DDD modul sərhədi) · Canonical Model (kanal-agnostik schema) ·
DLQ (Dead-Letter Queue) · HMAC (keyed-hash auth) · Idempotency-Key (təkrar request qoruması) · JWKS (Keycloak public key) ·
Outbox Pattern (DB tx + event atomik) · pgmq (Postgres queue) · RLS (Row-Level Security, tenant izolasiya) ·
RFC 7807 (problem+json error) · Sync engine (kanal ↔ POS sinxronizasiya) · Vardiya (kassir növbəsi) · Çek (satış sənədi) ·
OPK (AZ Onlayn Nəzarət-Kassa, fiskal).

## 20. Risk Reyestri (aktiv)

| Risk | Ehtimal | Təsir | Azaltma |
|---|---|---|---|
| Birmarket API mövcudluğu qeyri-müəyyən | Orta | Yüksək | Mock-first + Trendyol fallback (sənədli API) |
| İnteqrasiya drift / oversell | Orta | Yüksək | Idempotency + reconciliation + version lock (1-ci gündən) |
| Keycloak OIDC mürəkkəbliyi | Orta | Yüksək | Erkən POC (AI-1.7) |
| RLS performansı | Orta | Yüksək | Index + EXPLAIN ANALYZE + composite tenant_id |
| pgmq throughput | Aşağı | Orta | Benchmark; Kafka migration planı (LOCKED #12) |
| Partner access gecikməsi (insan) | Orta | Orta | Mock MVP-ni bloklamır; paralel müraciət |
| Validasiya uğursuz (G-V) | Orta | Yüksək | Erkən müsahibə; narrow/pivot hazır |

## 21. ADR İndeksi

| ADR | Mövzu | Status |
|---|---|---|
| 0001 | Stack seçimi | ACCEPTED |
| 0002 | Monorepo strukturu | ACCEPTED |
| 0003 | Sirr idarəsi (Vault-only) | ACCEPTED |
| 0010 | CVE istisnaları (pip-audit ignore) | ACCEPTED |
| 0011 | Beachhead re-scope (faza dondurma + G-V) | ACCEPTED |
| 0012 | POS-anchored İnteqrasiya Hub reframe | ACCEPTED (0011-i incələşdirir) |
| 0013 | EventBus: pgmq transactional outbox (hub onurğası) | ACCEPTED (AI-1.14) |
| 0014 | Dev/prod sirr sərhədi + Keycloak foundation client topologiyası | ACCEPTED (AI-1.7) |
| 0004–0009 | (rezerv — boşluq; lazım olduqca yaradılır) | — |

---

**Versiya:** 4.0 · **Tarix:** 1 İyun 2026 · **Dəyişiklik:** yalnız ADR + insan icazəsi ilə
