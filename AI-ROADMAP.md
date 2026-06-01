# AI-ROADMAP — Posnet Platforması
**Vahid İcra İstinad Sənədi — Claude Opus (claude-opus-4-7) üçün**

**Versiya:** 3.0 (1 İyun 2026 — bütün referans sənədlər vahid faylda birləşdirildi)
**Status:** ACTIVE — Tək başına icra üçün hazırdır
**İcra modeli:** AI-autonomous (1 AI + 1 insan operator)
**Infra:** Lokal-əvvəl → Cloud (Faza AI-7)
**Scope:** Bütün 8 faza (AI-0 … AI-7)
**Pilot kanal:** Mock adapter (real partnerlik asılılığı yox)

> ⚠️ **SCOPE FREEZE — ADR-0011 (2026-06-01).** İcra fokusu yalnız **AI-0 → AI-1 → AI-2**
> (fiziki POS MVP, mock fiskal). Sonra **G-V (Validasiya) gate**. **AI-3…AI-7 DONDURULUB**
> — G-V keçənə qədər BAŞLANMIR. Beachhead: Azərbaycan · kafe/restoran + kiçik pərakəndə.
> Bu banner-i pozma; dondurmanın ləğvi yeni ADR tələb edir. Detal:
> `docs/adr/0011-beachhead-rescope.md`.

---

## SƏNƏDİN YENİDƏN STRUKTURLAŞDIRILMASI (v2.1 → v3.0)

**Əvvəl:** AI-ROADMAP.md + 6 referans sənəd (02/03/04/05-FAZA, MASTER, FAZA-0-TDD) — AI başqa faylları açmalı idi → kontekst dağılması.

**İndi:** Hər şey burada. Bir sessiya yalnız 4 fayl yükləyir:
- `AI-ROADMAP.md` (bu — vahid texniki istinad)
- `CLAUDE.md` (qaydalar)
- `STATUS.md` (live state)
- `HUMAN-GATES.md` (insan ↔ AI dialoq)

Köhnə 6 referans sənəd silindi — bütün dəyəri bu sənədə inteqra edildi: epik təsvirləri, SQL DDL, API kontraktları, NFR hədəfləri, risk reyestri, KPI-lar, acceptance kriteriyaları, təhlükəsizlik checklist-ləri.

---

# PART I — LAYİHƏ VƏ MODEL

## 1. LAYİHƏ VİZYONU

**Ad:** Posnet — Qlobal Multi-POS və Çoxkanallı İnteqrasiya Platforması

**Vizyon:** Sahibkarın bütün satış kanallarını (fiziki kassa, online, marketplace, delivery, rezervasiya) tək platformadan idarə etmə.

**Tip:** Multi-tenant SaaS, modular monolit, event-driven

**Bazarlar:**
- 1-ci faza: Azərbaycan (lokal kanal: Birmarket / mock)
- 2-ci faza: Türkiyə (Trendyol, Hepsiburada, Wolt, Yandex)
- 3-ci faza: Qlobal genişləşmə (config-driven)

**Məhsul komponentləri:**
- Offline-first Flutter kassir tətbiqi
- Web/admin paneli (React)
- Storefront (Next.js — Faza AI-5)
- Real-time stok + qiymət sinxronizasiyası
- Event-driven multi-channel order management
- Modular adapter çərçivəsi (marketplace, delivery, booking)

## 2. 12 LOCKED TEXNİKİ QƏRAR

Bu qərarlar dəyişməz — yalnız ADR + insan icazəsi ilə.

| # | Sahə | Qərar |
|---|---|---|
| 1 | Arxitektura | Modular monolit nüvə + 3 adapter servisi (marketplace/delivery/booking) |
| 2 | Backend | Python 3.12+ / FastAPI |
| 3 | Pul hesablama | `Decimal` / integer minor units (qəpik/kuruş itirməmək üçün) |
| 4 | DB | PostgreSQL 16+ + RLS + JSONB |
| 5 | Messaging | pgmq (Postgres-queue) + EventBus abstraksiyası |
| 6 | Kassir | Flutter (offline-first, SQLite local) |
| 7 | Web | TypeScript + React (admin) / Next.js (storefront) |
| 8 | Secrets | Vault/KMS (kodda yox) |
| 9 | Xarici giriş | Etibarsız (zero-trust) + HMAC + JSON Schema validasiya |
| 10 | Ödəniş | Kart saxlanmır, PSP tokenizasiya |
| 11 | Auth | Keycloak (OIDC) + RBAC + MFA |
| 12 | Broker | Yalnız sübut olunmuş darboğazda Kafka-ya keç (default: pgmq) |

## 3. 12 BOUNDED CONTEXT

DDD prinsipləri əsasında 12 müstəqil domain. Hər biri öz schema-sı, öz API-si, mümkün qədər digərindən asılı olmayan business logic.

1. **Identity & Access** — tenant, user, role, permission, MFA
2. **Catalog** — məhsul, variant, kateqoriya, attribut, şəkil
3. **Inventory** — anbar, qalıq, hərəkət (movement), rezerv, batch (lot)
4. **Pricing** — qiymət, qayda (rule), promosyon, valyuta, FX
5. **Sales/POS** — satış, çek, vardiya, kassa, X/Z report
6. **Order Management** — sifariş, line, status, event, fulfillment, return
7. **Payments** — ödəniş metodu, transaction, refund, settlement
8. **Accounting** — double-entry ledger, journal, faktura, fiskal, e-invoice
9. **Integration** — kanal, adapter, mapping, sync, webhook
10. **CRM/Loyalty** — müştəri, bonus, kupon, segment
11. **Notification** — email, SMS, push, template, preference
12. **Analytics/Reporting** — hesabat, dashboard, KPI, BI export

## 4. AI İCRA MODELİ — PARADİQMA

Mövcud planlar əvvəlcə **12-14 nəfərlik insan komandası** üçün hazırlanmışdı. Bu sənəd **AI-autonomous** modelə çevirir.

| İnsan komandası modeli | AI-autonomous modeli |
|---|---|
| 12-14 nəfər paralel | 1 AI sessiya ardıcıl |
| Sprint (2 həftə) | Faza / Task (kontekst-əsaslı) |
| Story points | Verification-əsaslı |
| Daily standup | STATUS.md auto-update |
| JIRA + Confluence | Markdown faylları |
| Code review (2 approval) | Self-review + automated gates |
| Knowledge sharing | CLAUDE.md + memory |
| Vacation, sick leave | Yoxdur |

## 5. AKTYORLAR VƏ ROLLAR

| Aktyor | Rolu | Edə bilər | Edə bilməz |
|---|---|---|---|
| **Claude Opus** | Full-stack dev + arxitekt + QA + DevOps | Kod, test, infra-as-code (plan), schema, migration, sənəd, refactor, debug | Kart işlətmək, müqavilə imzalamaq, fiskal cihaz almaq, partner ilə danışmaq, prod-a deploy etmək |
| **İnsan operator** | PM + Gate-keeper + Compliance | Hesab açmaq, kart, domain, müqavilə, hüquqi qərar, gate icazəsi, sirr yaratmaq | Kod yazmaq (məcburi deyil) |
| **GitHub Actions** | Automated CI | Lint, mypy, pytest, bandit, detect-secrets, build, security scan | Heç bir avtomatik deploy |
| **STATUS.md** | Live state | Cari task, son verify, açıq suallar | Versiya idarəsi (git) |
| **HUMAN-GATES.md** | İnsan dialoq | Açıq suallar + gate keçidləri | Live state |
| **HANDOFF.md** | Session estafet | Kontekst doldukda növbəti sessiyaya | Uzun-müddətli plan |

## 6. GLOSSARİY VƏ AKRONİMLƏR

| Termin | İzah |
|---|---|
| **ADR** | Architecture Decision Record |
| **AsyncAPI** | Event-driven API spesifikasiyası (OpenAPI ekvivalenti) |
| **Bounded Context** | DDD-də müstəqil modul sərhədi |
| **Canonical Model** | Servislər arası ortaq Pydantic schemalar |
| **CSP** | Content Security Policy |
| **DLQ** | Dead-Letter Queue |
| **DR** | Disaster Recovery |
| **HMAC** | Keyed-hash message authentication |
| **HSTS** | HTTP Strict-Transport-Security |
| **i18n** | Internationalization |
| **Idempotency-Key** | Eyni request-in 2 dəfə icra olunmaması üçün |
| **JWKS** | JSON Web Key Set (Keycloak public key endpoint) |
| **JWT** | JSON Web Token |
| **K8s** | Kubernetes |
| **KVKK** | Kişisel Verilerin Korunması Kanunu (TR — GDPR ekvivalenti) |
| **NFR** | Non-Functional Requirements (latency, throughput, uptime) |
| **OIDC** | OpenID Connect |
| **OPK** | AZ Onlayn Nəzarət-Kassa (fiskal) |
| **OTel** | OpenTelemetry |
| **Outbox Pattern** | DB transaction + event publish atomik olması üçün |
| **PCI** | Payment Card Industry compliance |
| **pgmq** | Postgres-native message queue extension |
| **PII** | Personally Identifiable Information |
| **POS** | Point of Sale (kassa) |
| **Problem+JSON** | RFC 7807 error response formatı |
| **PSP** | Payment Service Provider |
| **RBAC** | Role-Based Access Control |
| **RLS** | Row-Level Security (Postgres tenant izolasiyası) |
| **RPO/RTO** | Recovery Point/Time Objective |
| **SDK** | Software Development Kit |
| **SLI/SLO/SLA** | Service Level Indicator/Objective/Agreement |
| **SSE** | Server-Sent Events |
| **TDD** | Test-Driven Development |
| **trgm** | pg_trgm — Postgres trigram search |
| **WAF** | Web Application Firewall |
| **Vardiya** | Shift (kassir növbəsi) |
| **Çek** | Receipt (satış sənədi) |
| **OPK** | AZ Onlayn Nəzarət-Kassa (Azərbaycan fiskal sistemi) |

---

# PART II — STACK VƏ STRUKTUR

## 7. TEXNOLOJİ STACK (LOCKED)

| Sahə | Qərar | Versiya |
|---|---|---|
| Backend | Python + FastAPI | 3.12 / FastAPI 0.110+ |
| Pul | `Decimal` / integer minor units | — |
| DB | PostgreSQL + RLS + pgmq + JSONB | 16+ |
| Migrations | Alembic | latest |
| Cache | Redis | 7+ |
| Message Queue | pgmq | 1.x |
| Auth | Keycloak (OIDC) | 25.x |
| Secrets | HashiCorp Vault | 1.15+ |
| Kassir | Flutter | 3.24+ |
| Frontend | TypeScript + React (admin) + Next.js 15 (storefront) | — |
| Container | Docker + Compose (lokal) / K8s + Helm (cloud) | latest |
| Reverse proxy lokal | Caddy + mkcert | 2.x |
| Object storage lokal | MinIO (S3-compat) | latest |
| Email mock lokal | Mailpit | latest |
| IaC | Terraform | 1.7+ |
| CI/CD | GitHub Actions | — |
| Observability | OpenTelemetry + Prometheus + Grafana + Jaeger + Loki | latest |
| Test | pytest + pytest-asyncio + testcontainers + Playwright + k6 | latest |
| Type check | mypy --strict | 1.10+ |
| Lint/Format | ruff + black | latest |
| Security | bandit + detect-secrets + pip-audit + nuclei (AI-7) | latest |
| Schema | Pydantic v2 | 2.6+ |
| Search | pg_trgm (Faza AI-2) → Meilisearch (Faza AI-5+) | — |

## 8. MONOREPO STRUKTURU

```
posnet/
├── CLAUDE.md                                 ← Claude Code auto-load
├── AI-ROADMAP.md                             ← Bu sənəd (vahid istinad)
├── STATUS.md                                 ← Live state
├── HUMAN-GATES.md                            ← İnsan dialoq jurnalı
├── HANDOFF.md                                ← Sessiya estafeti (lazımdırsa)
├── README.md
├── .gitignore
├── .env.example
├── .pre-commit-config.yaml
├── .secrets.baseline
├── pyproject.toml + uv.lock
├── pnpm-workspace.yaml + package.json
├── Makefile
├── docker-compose.yml
├── docker-compose.prod.yml
│
├── docs/
│   ├── adr/                                  ← ADR-NNNN-*.md
│   │   └── _template.md
│   ├── runbooks/
│   │   └── _template.md
│   ├── openapi/                              ← FastAPI auto-generate
│   ├── asyncapi/                             ← AI-3+
│   └── threat-model/                         ← AI-1+
│
├── services/
│   ├── core/                                 ← AI-1+2+3: əsas monolit
│   │   ├── app/{main.py, api/v1/, domain/, infrastructure/, middleware/}
│   │   ├── alembic/
│   │   └── tests/
│   ├── webhook-ingress/                      ← AI-3: webhook qəbulu
│   ├── marketplace-svc/                      ← AI-4+
│   ├── delivery-svc/                         ← AI-5+
│   ├── booking-svc/                          ← AI-7+
│   └── notification-svc/                     ← AI-2+: email/SMS/push (mock)
│
├── libs/                                     ← Servislər arası ortaq (snake_case — Python paket)
│   ├── canonical_model/                      ← Pydantic schemalar
│   ├── eventbus/                             ← pgmq + outbox + DLQ
│   ├── auth/                                 ← Keycloak JWT + JWKS cache
│   ├── observability/                        ← OTel + Prometheus + Loki
│   ├── i18n/                                 ← Babel
│   ├── feature_flags/                        ← DB-backed per-tenant
│   └── common/                               ← Logger, errors, types, request-id
│
├── apps/
│   ├── pos-flutter/                          ← AI-2: kassir
│   ├── admin-web/                            ← AI-2: React admin
│   └── storefront/                           ← AI-5: Next.js vitrin
│
├── mocks/                                    ← External system mock-ları
│   ├── mock-marketplace/                     ← AI-4
│   ├── mock-courier/                         ← AI-5
│   ├── mock-psp/                             ← AI-6
│   ├── mock-efaktura/                        ← AI-6
│   └── mock-fiscal/                          ← AI-2
│
├── infra/
│   ├── keycloak/realm-posnet.json
│   ├── grafana/dashboards/
│   ├── prometheus/prometheus.yml
│   ├── loki/loki-config.yaml
│   ├── otel/otel-collector-config.yaml
│   ├── caddy/Caddyfile
│   ├── postgres/init.sql                     ← pgmq + extensions
│   ├── terraform/                            ← AI-7
│   │   ├── modules/
│   │   └── envs/{staging,prod}/
│   └── helm/                                 ← AI-7
│
├── tests/
│   ├── unit/                                 ← (per-svc öz qovluğunda)
│   ├── integration/                          ← testcontainers
│   ├── contract/                             ← schemathesis + Pact
│   ├── e2e/                                  ← Playwright + curl
│   └── load/                                 ← k6 / Locust
│
├── scripts/
│   ├── keycloak_setup.py
│   ├── vault_init.sh
│   ├── seed_data.py
│   ├── db_backup.sh
│   └── ...
│
└── .github/workflows/{lint,test,security,build}.yml
```

## 9. SİRR İDARƏSİ — MƏCBURİ QAYDALAR

- **AI HEÇ VAXT** sirri kodda, log-da, commit-də yazmasın
- `.env.example` placeholder ilə commit, `.env` `.gitignore`-da
- Hər sirr Vault-da, kod yalnız `vault://path` ref istifadə edir
- Yeni sirr lazımdır → STATUS.md qeyd → HUMAN-GATES.md sual → insan Vault-a yazır → AI ref istifadə edir
- `detect-secrets` pre-commit hook məcburi

### Sirr kateqoriyaları

| Kateqoriya | Vault path | Kim yaradır | Faza |
|---|---|---|---|
| DB credentials | `secret/posnet/db/{env}` | AI lokal; insan prod | AI-1.3 / G7 |
| Keycloak client secret | `secret/posnet/keycloak/{client}` | AI (script) | AI-1.7 |
| Channel HMAC secret | `secret/posnet/channels/{code}/hmac` | Per-channel onboarding | AI-3+ |
| PSP API key | `secret/posnet/psp/{provider}` | İnsan | AI-7.12 |
| Fiskal certificate | `secret/posnet/fiscal/{country}` | İnsan | AI-7.11 |
| E-faktura credentials | `secret/posnet/efaktura/{country}` | İnsan | AI-7.13 |

## 10. FAZA ASILILIQ DİAQRAMI

```
       PREFLIGHT (insan, ~1-2 saat)
       ↓
       AI-0 BOOTSTRAP (11 task, ~6-10 saat)
       ↓ G0
       AI-1 FOUNDATION (18 task, ~25-40 saat)
       ↓ G1
       AI-2 POS CORE (14 task, ~60-80 saat)
       ↓ G2
       AI-3 ORDER + ADAPTER (12 task, ~40-55 saat)
       ↓ G3
       AI-4 MOCK PILOT — ★MVP★ (9 task, ~25-35 saat)
       ↓ G4
       AI-5 ONLINE + CATEGORY (13 task, ~35-50 saat)
       ↓ G5
       AI-6 ACCOUNTING + MULTI-COUNTRY (14 task, ~40-60 saat)
       ↓ G6 (hüquqi tövsiyə)
       AI-7 SCALE + DR + CLOUD (20 task, ~50-80 saat)
       ↓ G7 (staging) → G8 (production)
       LIVE
```

**Cəmi:** 111 task, ~280-410 saat AI work

## 11. NFR HƏDƏFLƏR (qeyri-funksional tələblər)

Hər faza Gate-də ölçülür və yoxlanılır.

### 11.1 Faza AI-1 (Foundation)
| Kateqoriya | Hədəf | Ölçü |
|---|---|---|
| Auth middleware overhead | < 20ms p95 | OTel histogram |
| RLS query overhead | < 10ms | EXPLAIN ANALYZE |
| pgmq publish latency | < 100ms p95 | DB trace |
| Health probe response | < 50ms | curl |
| Test coverage (core) | ≥ 80% | pytest-cov |

### 11.2 Faza AI-2 (POS Core)
| Kateqoriya | Hədəf | Ölçü |
|---|---|---|
| Kassa əməliyyat latency | < 100ms (lokal SQLite) | Flutter perf trace |
| Catalog list API (p95) | < 300ms (≤ 1000 məhsul) | OTel histogram |
| Stock movement journal write | < 50ms | DB trace |
| Offline → online sync | 100% data integrity, idempotent | Integration test |
| Fiskal cihaz round-trip (mock) | < 2s normal, queue >5s | Mock timer |
| Flutter cold start | < 2s | DevTools profile |

### 11.3 Faza AI-3 (Order + Adapter)
| Kateqoriya | Hədəf | Ölçü |
|---|---|---|
| Webhook → Unified Inbox latency (p95) | < 5s | OTel: ingress.received → modal.visible |
| Order injection success rate | ≥ 99.9% | Prometheus counter |
| HMAC validation overhead | < 10ms per request | OTel histogram |
| State machine transition validation | 100% (heç bir invalid keçid) | Unit + integration test |
| Adapter contract test pass | 100% (template + 1 mock kanal) | CI gate |

### 11.4 Faza AI-4 (Mock Pilot)
| Kateqoriya | Hədəf | Ölçü |
|---|---|---|
| Load: webhook RPS sustained | ≥ 100 req/s, 10 dəq | k6 |
| Status push p95 | < 3s | OTel |
| Reconciliation drift | 0 sifariş | Cron job |

### 11.5 Faza AI-7 (Cloud)
| Kateqoriya | Hədəf | Ölçü |
|---|---|---|
| Load: webhook RPS sustained | ≥ 1000 req/s, 30 dəq | k6 |
| System uptime | ≥ 99.9% | Prometheus |
| RPO | < 1 saat | DR test |
| RTO | < 30 dəq | DR test |

## 12. KPI / UĞUR METRİKLƏRİ

### Texniki
- Order injection: ≥ 99.9% success rate
- API latency (p95): < 300ms
- Stock sync (p95): < 60s
- System uptime: ≥ 99.9% (Faza AI-7 sonra)
- Test coverage: ≥ 80% (core 95%+)

### AI-spesifik
- Task uğur dərəcəsi (cəhd-1-də keçən): ≥ 70%
- Gate keçidi orta insan vaxtı: ≤ 1 saat
- "Stuck" hadisəsi per faza: ≤ 2
- Sirr leak insidenti: 0 (məcburi)
- Context overflow (HANDOFF) per faza: ≤ 3

### Məhsul
- Onboarding time: < 4 saat (mock pilot ilə)
- Modal acceptance: < 3 dəq
- New channel go-live: < 2 həftə

---

# PART III — HAZIRLIQ

## 13. PREFLIGHT — YALNIZ İNSAN (~1-2 saat)

### 13.1 Hesablar
- [ ] **GitHub** hesabı + private organization (`posnet-platform`)
- [ ] **Domain** opsional, AI-4 sonra (Namecheap/Cloudflare ~$10/il)
- [ ] **GitHub Container Registry** (GHCR) — pulsuz

### 13.2 Lokal mühit
- [ ] **Docker Desktop**, `docker info` işləyir
- [ ] **Python 3.12.x**
- [ ] **Node.js 20 LTS**
- [ ] **pnpm** (`npm install -g pnpm`)
- [ ] **Flutter 3.24+** + `fvm` (AI-2-yə qədər gözləyə bilər)
- [ ] **uv** (`pip install uv`) — opsional
- [ ] **VS Code + Claude Code extension**
- [ ] **git** + SSH key + GitHub-a əlavə
- [ ] **mkcert** + `mkcert -install`

### 13.3 Sirr-lər (one-time, AI heç vaxt görmür — offline saxla)
- [ ] Postgres root password (32-char təsadüfi)
- [ ] Keycloak admin password (32-char təsadüfi)
- [ ] Vault root token (lokal dev: `dev-root-token`; prod: real)
- [ ] GitHub PAT (CI/CD üçün, repository secret-da)

### 13.4 Layihə qovluğu
- [ ] Kök: `c:\Users\PC\OneDrive\Desktop\adapter` (artıq mövcud)

### 13.5 Gözləyə bilən qərarlar (AI-6/AI-7 öncəsi)
- AZ vergi qeydiyyatı (ƏDV mükəlləfi)
- E-faktura provayder (AZ: e-Faktura.az; TR: Logo, Mikro)
- PSP seçimi (AZ: Pasha, Kapital; TR: iyzico, PayTR)
- Hüquqi məsləhət (KVKK / GDPR / PCI)
- Cloud provider (Hetzner / DigitalOcean / Vultr / AWS) — AI-7

## 14. SESSİYA BAŞLANĞIC PROTOKOLU

Hər yeni Claude sessiyası bu ardıcıllıqla başlamalıdır:

```
1. CLAUDE.md oxu (project context, qaydalar)
2. STATUS.md oxu (cari faza, cari task, son commit, açıq suallar)
3. AI-ROADMAP.md — YALNIZ cari faza bölməsi (bütün sənədi yox)
4. HUMAN-GATES.md oxu (açıq insan suallar)
5. HANDOFF.md varsa, oxu (əvvəlki sessiyanın estafeti)
6. Cari task icra et
```

## 15. TASK İCRA DÖVRÜ

```
┌──────────────────────────────────────────────────┐
│ 1. STATUS.md oxu → cari task-ı tap                │
│ 2. AI-ROADMAP.md-də task detal-ını oxu (bu sənəd) │
│ 3. Mövcud kodu axtar (Glob/Grep) — dublikat yox   │
│ 4. Acceptance test-i ƏVVƏL yaz (TDD)              │
│ 5. İmplementasiya                                 │
│ 6. `make verify` — keçməsə fix, 3 cəhd, sonra STOP│
│ 7. Self-review (skill: simplify)                  │
│ 8. `git add . && git commit`                      │
│ 9. STATUS.md yenilə (commit hash, timestamp)      │
│ 10. Növbəti task və ya Gate-də DAYAN              │
└──────────────────────────────────────────────────┘
```

## 16. SELF-REVIEW CHECKLIST (commit-dən əvvəl)

- [ ] `make verify` keçdi
- [ ] `detect-secrets scan` keçdi (sirr yox)
- [ ] Ölü kod silindi (commented-out, unused imports)
- [ ] Test mock-u prod-a sızmadı
- [ ] Type-hint hər funksiyada
- [ ] OpenAPI schema yenidir
- [ ] Yeni env var `.env.example`-da
- [ ] Yeni dep `pyproject.toml`-da pin-li
- [ ] Yeni texniki qərar ADR-da
- [ ] Conventional Commits formatında commit mesajı

## 17. HUMAN GATE DAVRANIŞI

AI bu hallarda **MÜTLƏQ DAYANIR**:

1. Task `requires_human: true` (kart, credential, partner, fiskal)
2. 3 cəhddən sonra test hələ fail-dir (loop detection)
3. Eyni xəta düzəltmə cəhdi 2 dəfə uğursuz (sirkulyar refactor)
4. Yeni external dependency seçimi
5. Faza Gate-inə çatıldı (G0-G8)
6. Sirr yaradılması lazım

**Davranış:**
1. `STATUS.md`-də `BLOCKED: <səbəb>` yaz
2. `HUMAN-GATES.md`-də Q-NNN giriş yarat
3. Sessiyanı bitir, insan cavabını gözlə

## 18. KONTEKST BÜDCƏ PROTOKOLU

| Kontekst dolma | AI davranışı |
|---|---|
| < 50% | Normal icra |
| 50-70% | Yeni böyük task başlama, cari-ni tamamla |
| 70-85% | HANDOFF.md hazırla, commit et, sessiyanı bağla |
| > 85% | DƏRHAL HANDOFF + commit + sessiya bitir |

---

# PART IV — FAZA İCRA TƏFƏRRÜATLARI

## 19. FAZA AI-0: BOOTSTRAP (~6-10 saat AI)

**Məqsəd:** Boş qovluqdan `make verify` keçən tam karkas (backend + frontend + mobile tooling + observability + dev infra)

### Task AI-0.1 — Monorepo skeleton + Git init
**Prereq:** Preflight tamamlandı
**Goal:** Qovluq strukturu + git init + köhnə `*.md` faylları `docs/phases/`-ə köçür

**Steps:**
1. `git init`
2. §8 qovluq strukturunu yarat (boş `__init__.py`, README skeleton)
3. Mövcud `*.md` faylları `docs/phases/`-ə köçür (saxla: `AI-ROADMAP.md`, `STATUS.md`, `HUMAN-GATES.md`, `CLAUDE.md`, `README.md`)
4. `.gitignore` (Python + Node + Flutter + IDE + .env + volumes + .terraform)
5. İlk commit: `chore: initial monorepo structure`

**Acceptance:**
```bash
git status                    # clean
ls services/core/app/api/v1/  # mövcuddur
```

---

### Task AI-0.2 — Python tooling (pyproject + Makefile + pre-commit)
**Prereq:** AI-0.1
**Goal:** Python deps + əmrlər + commit-time qoruma

**Steps:**
1. `pyproject.toml`: FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg, redis, OTel SDK, prometheus-client, pgmq-py, slowapi, Babel, hvac, python-jose, structlog
2. Dev deps: pytest, pytest-asyncio, pytest-cov, pytest-rerunfailures, mypy, ruff, black, bandit, detect-secrets, pre-commit, testcontainers, schemathesis, locust
3. `Makefile` target-ləri: `bootstrap`, `up`, `down`, `verify`, `format`, `test`, `lint`, `type`, `security`, `migrate`, `clean`, `smoke`, `load`, `seed`, `backup`
4. `.pre-commit-config.yaml`: ruff, black, mypy, bandit, detect-secrets, yamllint
5. `.secrets.baseline`: `detect-secrets scan > .secrets.baseline`
6. `uv lock` (deterministic lock fayl)

**Acceptance:** `make lint` keçir, `pre-commit run --all-files` keçir

---

### Task AI-0.3 — Docker stack: backend services
**Prereq:** AI-0.2
**Goal:** PostgreSQL + Redis + Vault + Keycloak healthy

**Steps:**
1. `docker-compose.yml`:
   - `postgres` (16-alpine) + healthcheck + named volume + `init.sql` mount
   - `redis` (7-alpine) + healthcheck
   - `vault` (1.15+, dev mode, root token: `dev-root-token`)
   - `keycloak` (25.x) + health endpoint + persistent volume
2. `infra/postgres/init.sql`: `CREATE EXTENSION IF NOT EXISTS pgmq; CREATE EXTENSION pg_trgm; CREATE DATABASE posnet_core;`
3. `infra/keycloak/realm-posnet.json` — boş placeholder

**Acceptance:**
```bash
docker-compose up -d postgres redis vault keycloak
sleep 20 && docker-compose ps   # 4 healthy
psql -h localhost -U posnet -c "\dx" | grep pgmq
curl http://localhost:8080/health/live      # Keycloak
vault status                                 # Vault sealed=false
```

---

### Task AI-0.4 — Docker stack: observability
**Prereq:** AI-0.3
**Goal:** Jaeger + Prometheus + Grafana + Loki + OTel Collector healthy

**Steps:**
1. `docker-compose.yml`-ə əlavə: `jaeger`, `prometheus`, `grafana`, `loki`, `otel-collector`
2. `infra/prometheus/prometheus.yml` — scrape `services/*`
3. `infra/loki/loki-config.yaml` — single-binary mode
4. `infra/otel/otel-collector-config.yaml` — OTLP → Jaeger + Prometheus + Loki
5. `infra/grafana/datasources.yml` — preconfigured

**Acceptance:**
```bash
curl http://localhost:16686    # Jaeger
curl http://localhost:9090     # Prometheus
curl http://localhost:3000     # Grafana
curl http://localhost:3100/ready   # Loki
```

---

### Task AI-0.5 — Docker stack: dev infrastructure
**Prereq:** AI-0.3
**Goal:** Mailpit + MinIO + Caddy (TLS reverse proxy)

**Steps:**
1. `docker-compose.yml`-ə: `mailpit`, `minio`, `caddy`
2. `infra/caddy/Caddyfile`:
   - `posnet.local` → `core:8000`
   - `keycloak.posnet.local` → `keycloak:8080`
   - `admin.posnet.local` → `admin-web:5173`
   - `mail.posnet.local` → `mailpit:8025`
   - `s3.posnet.local` → `minio:9000`
3. `/etc/hosts` qeydlərini README-də göstər
4. mkcert wildcard cert
5. MinIO bucket-lar: `posnet-uploads`, `posnet-backups`

**Acceptance:** `curl https://mail.posnet.local`, `curl https://s3.posnet.local/minio/health/live`

---

### Task AI-0.6 — Frontend tooling (Node + pnpm workspace)
**Prereq:** AI-0.1
**Goal:** Monorepo frontend setup

**Steps:**
1. `pnpm-workspace.yaml`: `apps/admin-web`, `apps/storefront`
2. Root `package.json` + workspace + lint-staged + husky-light
3. Shared: `tsconfig.base.json`, `.eslintrc.cjs`, `.prettierrc.json`
4. `apps/admin-web/` Vite + React + TS skeleton (real impl AI-2.10)
5. `apps/storefront/` Next.js 15 skeleton (real impl AI-5.9)

**Acceptance:** `pnpm install`, `pnpm -r lint`

---

### Task AI-0.7 — Flutter tooling skeleton
**Prereq:** AI-0.1
**Goal:** `apps/pos-flutter/` project init

**Steps:**
1. `fvm install 3.24.x`
2. `flutter create` (cross-platform)
3. `pubspec.yaml` baseline: dio, riverpod, drift (offline DB), go_router, intl, flutter_appauth (Keycloak), mobile_scanner
4. `.gitignore` Flutter-specific

**Acceptance:** `cd apps/pos-flutter && flutter test`

**Note:** Flutter lokal quraşdırılmayıbsa AI-2-yə təxir et

---

### Task AI-0.8 — GitHub Actions CI
**Prereq:** AI-0.2
**Goal:** PR-də avtomatik lint + test + security + build

**Steps:**
1. `.github/workflows/lint.yml` — ruff + black + mypy + ESLint
2. `.github/workflows/test.yml` — pytest + coverage gate (80%) + frontend test
3. `.github/workflows/security.yml` — bandit + pip-audit + detect-secrets + npm-audit + Dependabot config
4. `.github/workflows/build.yml` — Docker → GHCR (main branch)
5. CODEOWNERS faylı

**Acceptance:** Branch yarat, push, GitHub Actions yaşıl

---

### Task AI-0.9 — ADR + Runbook template + ilk 3 ADR
**Prereq:** AI-0.1
**Goal:** Texniki qərarlar üçün format

**Steps:**
1. `docs/adr/_template.md` (§51 format)
2. `docs/runbooks/_template.md` (§52 format)
3. ADR-0001: "Stack — Python 3.12 + FastAPI + Postgres 16 + Keycloak"
4. ADR-0002: "Monorepo strukturu (services/libs/apps/mocks/infra)"
5. ADR-0003: "Sirr idarəsi — Vault, kodda yox"

**Acceptance:** 5 fayl mövcuddur

---

### Task AI-0.10 — CLAUDE.md tamamla
**Prereq:** AI-0.1 ... AI-0.9
**Goal:** Hər gələcək Claude sessiyası bu faylı oxuyacaq

**Steps:** `CLAUDE.md`-də mövcud skeleton-u tamamla — bütün §-lərə istinad

---

### Task AI-0.11 — Smoke test: `make bootstrap`
**Prereq:** AI-0.1 ... AI-0.10
**Goal:** Tək əmrlə bütün mühit qaçır

**Steps:**
1. `Makefile`-də `bootstrap` target: `up + sleep 30 + verify`
2. README quickstart bölməsi yenilə

**Acceptance:** `make clean && make bootstrap` keçir

---

### **GATE G0 — Bootstrap done** (insan, ~10 dəq)
- [ ] `make bootstrap` keçir
- [ ] `docker-compose ps` — 12+ servis healthy
- [ ] `https://posnet.local` (Caddy) cavab verir
- [ ] GitHub Actions yaşıl
- [ ] 11 commit
- [ ] STATUS.md `Faza AI-0 done`

---

## 20. FAZA AI-1: FOUNDATION (~25-40 saat AI)

**Məqsəd:** Auth + multi-tenant + DB + RLS + pgmq + observability + tenant onboarding

### 20.1 Texniki məzmun (köhnə FAZA-0-TDD-dən inteqra)

#### SQL Schema (Identity)
```sql
-- Tenants
CREATE TABLE public.tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  country_code VARCHAR(2) NOT NULL,
  plan VARCHAR(50) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP DEFAULT NOW()
);

-- Stores (per-tenant branches)
CREATE TABLE public.stores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  status VARCHAR(20) DEFAULT 'active',
  open_status VARCHAR(20) DEFAULT 'closed',
  timezone VARCHAR(100) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Users
CREATE TABLE public.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  status VARCHAR(20) DEFAULT 'active',
  mfa_enabled BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(tenant_id, email)
);

-- Roles (RBAC)
CREATE TABLE public.roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(tenant_id, name)
);

-- Permissions
CREATE TABLE public.permissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  resource VARCHAR(100) NOT NULL,
  action VARCHAR(100) NOT NULL,
  UNIQUE(role_id, resource, action)
);

-- User-Role
CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  store_id UUID,  -- NULL = tenant-wide
  UNIQUE(user_id, role_id, COALESCE(store_id, 'null'::uuid))
);

-- Audit log (append-only)
CREATE TABLE public.audit_logs (
  id BIGSERIAL PRIMARY KEY,
  tenant_id UUID NOT NULL,
  actor UUID,
  action VARCHAR(100) NOT NULL,
  target TEXT NOT NULL,
  meta_jsonb JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_audit_logs_tenant ON audit_logs(tenant_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at);

-- Idempotency keys
CREATE TABLE public.idempotency_keys (
  key VARCHAR(255) PRIMARY KEY,
  tenant_id UUID NOT NULL,
  result_ref TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Outbox events
CREATE TABLE public.outbox_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  event_type VARCHAR(100) NOT NULL,
  payload JSONB NOT NULL,
  published BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### RLS Policy template
```sql
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_rls ON public.users
USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- Hər tenant-cədvəlinə eyni pattern
```

#### RBAC rolları
- `super_admin` — system-level (Keycloak system role, normal tenant-larda yox)
- `tenant_admin` — tenant səviyyəsində bütün icazələr
- `store_manager` — bir store üçün manager
- `cashier` — kassir əməliyyatları
- `clerk` — yardımçı (read-only kataloq + inventory view)

#### Error format (RFC 7807 problem+json)
```json
{
  "type": "https://posnet.io/errors/not-found",
  "title": "User not found",
  "status": 404,
  "detail": "User 123 does not exist in tenant abc",
  "instance": "/v1/users/123",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "req-abc-123"
}
```

#### Middleware ardıcıllığı (kritik!)
```
1. RequestIdMiddleware       (header → state, generate if missing)
2. LoggingMiddleware         (structlog binding: trace_id, tenant_id)
3. TracingMiddleware         (OTel span start)
4. AuthMiddleware            (JWT verify, JWKS cache)
5. TenantContextMiddleware   (RLS SET LOCAL app.current_tenant)
6. RateLimitMiddleware       (slowapi, per-tenant)
7. ErrorHandlerMiddleware    (Exception → RFC 7807)
```

### 20.2 Task siyahısı (18 task)

#### Task AI-1.1 — Test infra + coverage gate (FIRST)
**Goal:** Bütün sonrakı task-lar 80% gate altında yazılır

**Steps:**
1. `tests/conftest.py`: pytest fixture (DB rollback per test, Redis flush, Vault token, Keycloak token mock)
2. `tests/integration/conftest.py`: testcontainers (real Postgres 16 + pgmq + Redis 7)
3. `pyproject.toml`-da pytest: `--cov=services --cov=libs --cov-fail-under=80`
4. CI workflow yenilə: coverage badge
5. Smoke stub: `tests/smoke/test_health.py`

**Acceptance:** `make test` keçir, `make verify` keçir

#### Task AI-1.2 — libs/common (logger + errors + types + request-id + structured logging)
**Goal:** Bütün servislərin istifadə edəcəyi infrastruktur kitabxanası

**Steps:**
1. `libs/common/logger.py`: structlog + JSON + trace_id binding
2. `libs/common/errors.py`: `DomainError`, `NotFoundError`, `ConflictError`, `ValidationError`, `AuthError`, `RateLimitError` (HTTP status mapping ilə)
3. `libs/common/types.py`: `TenantId`, `UserId`, `Money` (Decimal + currency), `Email`, `UUIDv7`
4. `libs/common/request_id.py`: middleware (header oxu / generate)
5. `libs/common/utils.py`: `now_utc()`, `parse_idempotency_key()`

**Acceptance:** `pytest libs/common/` — 90% coverage

#### Task AI-1.3 — Vault setup + secrets helper
**Goal:** Bütün sirr-lər Vault-da; heç bir env password

**Steps:**
1. `libs/common/secrets.py`: `get_secret(path)` (hvac + retry + 5dəq cache)
2. `scripts/vault_init.sh`: lokal dev Vault, KV v2, ilk sirr-lər (postgres, redis, keycloak admin)
3. ADR-0004: "Vault-only secrets"
4. Integration test

**Acceptance:** `bash scripts/vault_init.sh`, `vault kv get secret/posnet/db`

#### Task AI-1.4 — libs/canonical-model skeleton
**Goal:** Servislər arası ortaq Pydantic schema base

**Steps:**
1. `libs/canonical-model/base.py`: `CanonicalBase(BaseModel)` (timestamp, version, tenant_id)
2. `libs/canonical-model/identity.py`: `Tenant`, `User`, `Role`, `Permission`
3. Pydantic v2 + `ConfigDict(frozen=True, strict=True)`
4. Versiyalı: `models_v1.py`

#### Task AI-1.5 — SQLAlchemy models + Alembic init + migration 0001
**Goal:** Core DB schema mövcuddur (§20.1 SQL DDL)

**Steps:**
1. `services/core/app/infrastructure/db/base.py`: SQLAlchemy 2 declarative
2. Models §20.1-dəki kimi
3. UUID v7 primary key
4. Audit columns: `created_at`, `updated_at`, `created_by`
5. `alembic init` + `env.py` config
6. Migration 0001: bütün cədvəllər
7. `make migrate` Makefile-da

**Acceptance:** `make migrate`, `psql -c "\dt"` 8 cədvəl

#### Task AI-1.6 — RLS policies migration + ADR
**Goal:** Tenant izolasiyası DB səviyyəsində

**Steps:**
1. Migration 0002: hər tenant-cədvəlinə RLS policy
2. ADR-0005: "Multi-tenant via Postgres RLS"
3. Integration test: 2 tenant, A token ilə B data → 0 nəticə

#### Task AI-1.7 — Keycloak realm setup + admin script
**Goal:** `posnet` realm + 3 client + 4 role + test user

**Steps:**
1. `scripts/keycloak_setup.py`: idempotent (Keycloak admin API)
   - Realm: `posnet`
   - Clients: `api-gateway` (confidential), `admin-web` (public+PKCE), `pos-mobile` (public+PKCE)
   - Roles: `tenant_admin`, `cashier`, `store_manager`, `clerk` (super_admin system-level)
   - Test user: `test-user` / Vault-dakı password
2. Export: `infra/keycloak/realm-posnet.json`
3. Client secret-lər Vault-a

**Acceptance:**
```bash
python scripts/keycloak_setup.py
curl -X POST .../realms/posnet/protocol/openid-connect/token \
  -d "grant_type=password&client_id=admin-web&username=test-user&password=..." \
  # → access_token
```

#### Task AI-1.8 — libs/auth (JWT verify + JWKS cache)
**Goal:** JWT validate + cache-lənən kitabxana

**Steps:**
1. `libs/auth/jwt.py`: JWT verify (python-jose), JWKS Redis cache (TTL 1 saat)
2. `libs/auth/dependencies.py`: `get_current_user`, `require_role(role)`, `require_permission(resource, action)`
3. `libs/auth/exceptions.py`: `AuthError`, `TokenExpiredError`, `InsufficientPermissionsError`

#### Task AI-1.9 — FastAPI app skeleton + middleware stack
**Goal:** §20.1-dəki middleware ardıcıllığı + structured logging

**Steps:**
1. `services/core/app/main.py`: FastAPI app, lifespan, OpenAPI config
2. Middleware §20.1-dəki ardıcıllıqla
3. Structured logging config (JSON, trace_id, tenant_id, request_id)

**Acceptance:** `curl http://localhost:8000/openapi.json`

#### Task AI-1.10 — Global error handler (RFC 7807)
**Goal:** Bütün error response §20.1-dəki standart formatda

**Steps:**
1. `services/core/app/middleware/error_handler.py`
2. ADR-0006: "Error format = RFC 7807"
3. Test üçün domain error throw + format yoxlama

#### Task AI-1.11 — Tenant context middleware (RLS injection)
**Goal:** Hər request DB session-da RLS context

**Steps:**
1. `services/core/app/middleware/tenant_context.py`: token-dən `tenant_id` → `SET LOCAL app.current_tenant`
2. SQLAlchemy session dependency injection
3. Integration test: cross-tenant API → 0 nəticə

#### Task AI-1.12 — CORS + security headers + API rate limiter
**Goal:** Security baseline

**Steps:**
1. CORS: configurable origins (.env), credentials, max-age
2. Security headers: HSTS, CSP (default deny), X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin
3. Rate limiter: `slowapi` + Redis, default 100 req/dəq per-tenant
4. Threat model: `docs/threat-model/api-surface.md`

**Acceptance:** `curl -I` header-lər, 101 sürətli request → 429

#### Task AI-1.13 — OpenTelemetry + Jaeger + Prometheus + Grafana + Loki
**Goal:** End-to-end trace + metric + log + dashboard

**Steps:**
1. `libs/observability/tracing.py`: FastAPI + SQLAlchemy + Redis + httpx auto-instrument; OTLP → otel-collector
2. `libs/observability/metrics.py`: prometheus-fastapi-instrumentator; `http_requests_total{tenant_id, route, status}`, `db_query_duration_seconds`
3. Trace context W3C header propagation
4. Span attributes: `tenant_id`, `user_id`, `request_id`
5. Grafana dashboard: `infra/grafana/dashboards/api-overview.json` (RPS, p50/p95/p99, error rate)
6. Loki integration

#### Task AI-1.14 — pgmq publisher + consumer + outbox + DLQ
**Goal:** Event-driven foundation

**Steps:**
1. `libs/eventbus/publisher.py`: `publish(queue, payload, idempotency_key)` — outbox (DB tx-da OutboxEvent insert)
2. `libs/eventbus/outbox_worker.py`: outbox → pgmq background task
3. `libs/eventbus/consumer.py`: long-polling consumer
4. `libs/eventbus/retry.py`: exponential backoff (1s/2s/4s/8s/16s, max 5)
5. DLQ: `dlq_<queue>` max retry sonra
6. ADR-0007: "EventBus = pgmq + Outbox pattern"

#### Task AI-1.15 — Tenant onboarding API + first tenant seed
**Goal:** İlk tenant yaratma + seed

**Steps:**
1. `POST /v1/onboarding/tenant` — yalnız `super_admin`
2. Tenant + Keycloak subgroup + ilk admin user + JWT qaytar
3. Idempotent (slug ilə)
4. `scripts/seed_first_tenant.py` lokal dev üçün

#### Task AI-1.16 — User/Role/Permission CRUD + invite stub
**Goal:** Tenant admin user-ləri idarə edir

**Steps:**
1. `GET/POST/PATCH/DELETE /v1/users` (RLS)
2. `POST /v1/users/invite` (email send AI-2.9-da real)
3. Yalnız `tenant_admin` create/delete
4. Pagination + filtering (Pydantic Query)

#### Task AI-1.17 — Feature flags + i18n backend
**Goal:** Per-tenant feature flag + lokalizasiya

**Steps:**
1. `libs/feature-flags/`: DB-backed (`feature_flags{tenant_id, key, enabled, payload}`)
2. `flag_enabled(tenant_id, key)` + Redis 60s cache
3. Admin API: `GET/PATCH /v1/admin/flags`
4. `libs/i18n/`: Babel-based, `_("message")`, fallback `az → en`
5. Translation files: `libs/i18n/locales/{az,en,tr}/messages.po`

#### Task AI-1.18 — Health probes + graceful shutdown + backup + seed fixtures
**Goal:** Production-readiness baseline

**Steps:**
1. `GET /healthz` (liveness 200)
2. `GET /readyz` (DB + Redis + pgmq + Vault ping)
3. Graceful shutdown: SIGTERM → drain 30s → close DB pool
4. DB pool: `pool_size=20, max_overflow=10, pool_recycle=3600`
5. `scripts/db_backup.sh`: pg_dump → MinIO
6. `scripts/seed_data.py`: test tenant + users + sample
7. `make backup`, `make seed`

### 20.3 Acceptance criteria (Faza AI-1 Done)

- [ ] `docker-compose up -d` → bütün servislər healthy
- [ ] `make lint` ✅ (mypy --strict, black, ruff, bandit)
- [ ] `make test` ✅ coverage ≥ 80%
- [ ] GitHub Actions yaşıl
- [ ] Keycloak: realm "posnet" + 3 client + 4 role, OIDC round-trip işləyir
- [ ] RLS: T1 user T2 data görmür (integration test)
- [ ] DB: 2 migration upgrade/downgrade/upgrade cycle keçir
- [ ] pgmq: publish → consume → DLQ round-trip
- [ ] OpenAPI `/docs` açılır, RFC 7807 error format
- [ ] OTel: Jaeger UI-də trace, span-larda `tenant_id, user_id, trace_id`
- [ ] Grafana dashboard data ilə dolu
- [ ] Loki structured log
- [ ] Vault-dan secret oxunur (heç bir env password)
- [ ] Rate limit aktiv (101 → 429)
- [ ] DB backup MinIO bucket-da
- [ ] 4 ADR commit (0004-0007)
- [ ] Release tag: `v0.1.0-alpha`

### 20.4 Risklər və azaltma (Faza AI-1)

| Risk | Ehtimal | Təsir | Azaltma |
|---|---|---|---|
| Keycloak OIDC mürəkkəbliyi | Orta | Yüksək | Erkən sandbox test, POC ilk gün |
| RLS performansı | Orta | Yüksək | Index planning, EXPLAIN ANALYZE, tenant_id composite index |
| pgmq throughput limiti | Aşağı | Orta | Benchmark, gələcəkdə Kafka migrasiya planı |
| Docker Compose lokal performans (Win/Mac) | Orta | Aşağı | DevContainer alternativi |
| Vault dev → prod migrasiyası | Aşağı | Yüksək | Prod policy template + IaC erkən |

### 20.5 Təhlükəsizlik checklist (Faza AI-1)

- [ ] Bütün API endpoint-də `@require_permission(...)` decorator
- [ ] Bütün mutation → audit log entry
- [ ] JWT signature verify (JWKS), expiry check
- [ ] Rate limit aktiv (per-tenant)
- [ ] HTTPS only (Caddy + mkcert lokal, TLS prod)
- [ ] Secrets Vault-da, kodda yox
- [ ] CORS strict origins
- [ ] Security headers (HSTS, CSP, X-Frame-Options)

### **GATE G1 — Foundation done** (insan, ~30 dəq)

Yuxarıdakı acceptance criteria-ları yoxla.

---

## 21. FAZA AI-2: POS CORE (~60-80 saat AI)

**Məqsəd:** Catalog + inventory + pricing + shift + sales + Flutter kassir + admin paneli = fiziki kassa MVP

### 21.1 Texniki məzmun

#### SQL Schema (Catalog + Inventory + Sales)
```sql
-- Catalog
CREATE TABLE public.products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  store_id UUID NOT NULL,
  name TEXT NOT NULL,
  brand TEXT,
  category_path TEXT,  -- "electronics/phones"
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE public.variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  sku VARCHAR(100) NOT NULL,
  barcode VARCHAR(100),
  name TEXT NOT NULL,
  attributes_jsonb JSONB DEFAULT '{}',
  base_price_minor BIGINT NOT NULL,
  cost_price_minor BIGINT,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(product_id, sku)
);

CREATE TABLE public.product_images (
  id UUID PRIMARY KEY,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  sort_order INTEGER DEFAULT 0
);

-- Search index
CREATE INDEX idx_products_search ON products USING gin(to_tsvector('simple', name || ' ' || COALESCE(brand, '')));
CREATE INDEX idx_variants_barcode ON variants(barcode) WHERE barcode IS NOT NULL;
CREATE INDEX idx_variants_sku ON variants(sku);

-- Inventory
CREATE TABLE public.warehouses (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  name TEXT NOT NULL,
  type VARCHAR(20) NOT NULL,  -- store, central, dark
  address TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE public.inventory (
  id UUID PRIMARY KEY,
  variant_id UUID NOT NULL REFERENCES variants(id),
  warehouse_id UUID NOT NULL REFERENCES warehouses(id),
  qty BIGINT NOT NULL DEFAULT 0,
  reserved_qty BIGINT NOT NULL DEFAULT 0,
  min_qty BIGINT DEFAULT 0,
  version INTEGER DEFAULT 0,  -- optimistic lock
  last_counted_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(variant_id, warehouse_id)
);

CREATE TABLE public.stock_movements (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  variant_id UUID NOT NULL,
  warehouse_id UUID NOT NULL,
  type VARCHAR(20) NOT NULL,  -- in, out, transfer, adjust, reserve, unreserve
  qty BIGINT NOT NULL,
  reference TEXT,  -- "sale:<sale_id>", "order:<order_id>"
  reason TEXT,
  moved_at TIMESTAMP DEFAULT NOW(),
  moved_by UUID
);

CREATE TABLE public.batches (
  id UUID PRIMARY KEY,
  variant_id UUID NOT NULL,
  lot_number VARCHAR(100),
  expiry_date DATE,
  qty_on_hand BIGINT NOT NULL DEFAULT 0
);

-- Pricing
CREATE TABLE public.price_rules (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  channel_code VARCHAR(50),  -- NULL = base
  scope VARCHAR(20) NOT NULL,  -- product, category, all
  scope_ref TEXT,
  type VARCHAR(20) NOT NULL,  -- base, markup, discount
  value_minor BIGINT NOT NULL,
  priority INTEGER DEFAULT 0,
  valid_from TIMESTAMP,
  valid_to TIMESTAMP,
  conditions_jsonb JSONB DEFAULT '{}'
);

CREATE TABLE public.promotions (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  kind VARCHAR(50) NOT NULL,  -- discount, bundle, buy_x_pay_y
  conditions_jsonb JSONB,
  valid_from TIMESTAMP,
  valid_to TIMESTAMP
);

-- Shift
CREATE TABLE public.shifts (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  store_id UUID NOT NULL,
  user_id UUID NOT NULL,
  opened_at TIMESTAMP NOT NULL,
  closed_at TIMESTAMP,
  opening_cash_minor BIGINT NOT NULL,
  closing_cash_minor BIGINT,
  status VARCHAR(20) DEFAULT 'open'
);

CREATE TABLE public.cash_movements (
  id UUID PRIMARY KEY,
  shift_id UUID NOT NULL REFERENCES shifts(id),
  type VARCHAR(20) NOT NULL,  -- in, out
  amount_minor BIGINT NOT NULL,
  note TEXT,
  recorded_at TIMESTAMP DEFAULT NOW()
);

-- Sales
CREATE TABLE public.sales (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  store_id UUID NOT NULL,
  shift_id UUID NOT NULL,
  customer_id UUID,
  total_minor BIGINT NOT NULL,
  tax_minor BIGINT NOT NULL,
  discount_minor BIGINT DEFAULT 0,
  payment_method VARCHAR(50),
  status VARCHAR(20) DEFAULT 'completed',
  fiscal_receipt_url TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE public.sale_lines (
  id UUID PRIMARY KEY,
  sale_id UUID NOT NULL REFERENCES sales(id),
  variant_id UUID NOT NULL,
  qty INTEGER NOT NULL,
  unit_price_minor BIGINT NOT NULL,
  tax_minor BIGINT NOT NULL,
  discount_minor BIGINT DEFAULT 0
);

CREATE TABLE public.returns (
  id UUID PRIMARY KEY,
  sale_id UUID NOT NULL REFERENCES sales(id),
  reason TEXT,
  status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected
  refund_amount_minor BIGINT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### API kontrakt nümunələri

**Catalog: Create Product**
```http
POST /v1/stores/{store_id}/products
Authorization: Bearer <jwt>
Idempotency-Key: <uuid>
Content-Type: application/json

{
  "name": "Coca Cola 0.5L",
  "brand": "Coca-Cola",
  "category_path": "drinks/sodas",
  "variants": [
    {
      "sku": "CC-0.5",
      "barcode": "5449000000996",
      "base_price_minor": 150,
      "currency": "AZN",
      "attributes": {"volume_ml": 500}
    }
  ]
}

→ 201 Created { "id": "<uuid>", "created_at": "2026-06-01T10:00:00Z" }
→ 409 Conflict (barcode dublikası)
```

**Inventory: Record Movement (with optimistic lock)**
```http
POST /v1/inventory/{variant_id}/movements
Idempotency-Key: <uuid>
{
  "warehouse_id": "<uuid>",
  "type": "out",
  "qty": 1,
  "reference": "sale:<sale_id>",
  "reason": "POS sale",
  "expected_version": 42
}

→ 201 + Event: stock.changed
→ 409 if version mismatch (overselling protection)
```

**Sales: Complete Sale**
```http
POST /v1/stores/{store_id}/sales
Idempotency-Key: <uuid>
{
  "shift_id": "<uuid>",
  "lines": [{"variant_id": "<uuid>", "qty": 2, "unit_price_minor": 150}],
  "payment": {"method": "cash", "amount_minor": 300},
  "customer_id": null
}

→ 201 + fiskal receipt URL + ledger entries
```

#### Price Calculation API (internal)
```python
PriceCalculator.calculate(
    variant_id=...,
    channel_code="pos",
    qty=2,
    customer_segment=None,
    at=datetime.utcnow(),
) -> PriceQuote(
    base_minor=150,
    rules_applied=[{"rule_id": ..., "delta_minor": -10}],
    tax_minor=22,
    total_minor=290,
    currency="AZN",
)
```

#### Fiskal mock kontrakti
```http
# Mock fiskal HTTP servisi (mocks/mock-fiscal/)
POST http://mock-fiscal:9000/fiscal/print
{
  "tenant_id": "...",
  "shift_id": "...",
  "sale_id": "...",
  "lines": [...],
  "total_minor": 290,
  "tax_minor": 22
}
→ 200 { "receipt_id": "...", "receipt_url": "...", "fiscal_code": "AZE-XXXX" }
→ 503 (simulate downtime — adapter queue + retry)
```

### 21.2 Task siyahısı (14 task)

- **AI-2.1** — Catalog domain (Product, Variant, Category, Barcode, Attribute) + CRUD API + bulk CSV import + barcode uniqueness + audit
- **AI-2.2** — File storage (MinIO/S3): product image upload + signed URL + thumbnail generation
- **AI-2.3** — Search engine: pg_trgm + full-text (`name`, `barcode`, `sku`) + GIN index + `GET /v1/catalog/search`
- **AI-2.4** — Inventory domain (Warehouse, Stock, Reservation, Movement, Batch) + optimistic locking (version column) + reservation TTL (30 dəq) + `POST /reserve`, `/unreserve`, `/stock-take`
- **AI-2.5** — Pricing engine (PriceList, PriceRule, Discount, Tax) + rule composition (priority order) + effective price + multi-currency (Decimal) + FX apply + tax apply (country-profile)
- **AI-2.6** — Shift/Vardiya: open/close + X/Z-report + cash drawer + secondary approval > 500 AZN
- **AI-2.7** — Sales/Receipt: Transaction + LineItem + Payment + Refund + receipt number unique per shift + multi-payment (split)
- **AI-2.8** — Mock fiskal modul: `mocks/mock-fiscal/` HTTP servis + `services/core/app/infrastructure/fiscal/` adapter + retry + offline queue
- **AI-2.9** — Notification service skeleton (`services/notification-svc/`): email (Mailpit) + SMS mock + push mock + template engine (Jinja2) + per-tenant template override
- **AI-2.10** — Admin web (React + Vite + TanStack Query + shadcn/ui): layout + navigation + auth (Keycloak PKCE) + product CRUD + stock view + shift report
- **AI-2.11** — Admin web continuation: user management + role assignment + feature flags UI + audit log viewer + bulk import wizard
- **AI-2.12** — Flutter kassir app: login (Keycloak PKCE) + barcode scan (mobile_scanner) + catalog browsing + basket + payment + receipt print mock
- **AI-2.13** — Flutter offline-first: SQLite local DB (drift) + sync queue + conflict resolution (last-write-wins kataloq; version-based stok) + idempotent sync + network status indicator + auto-retry
- **AI-2.14** — End-to-end test ssenarisi (Playwright + Flutter integration_test): kassir login → məhsul seç (offline) → ödəniş → fiskal mock receipt → sync online → admin-də görünür → Z-report

### 21.3 Acceptance criteria (Faza AI-2 Done)

- [ ] Admin paneli ilə 5 məhsul yarat, stok qoy, qiymət təyin et
- [ ] Flutter: login → məhsul seç → ödəniş → fiskal mock receipt
- [ ] Offline: airplane mode → 3 satış → online qayıt → sync olur
- [ ] Overselling: 2 cihaz son ədədi sat → biri uğursuz (version mismatch)
- [ ] Z-report düzgün hesablanır (cash sum, payment method breakdown)
- [ ] Email notification Mailpit-də (sifariş təsdiqi)
- [ ] Cost movement > 500 AZN → secondary approval gözləyir
- [ ] coverage 80%+

### 21.4 Risklər (Faza AI-2)

| Risk | Ehtimal | Təsir | Azaltma |
|---|---|---|---|
| Offline sync mürəkkəbliyi | Yüksək | Yüksək | Mock server, conflict scheme, server-wins default |
| Flutter performansı (böyük kataloq) | Orta | Orta | Profiling, lazy load + index |
| Multi-warehouse race (stock) | Orta | Yüksək | Optimistic locking + ledger; integration test |
| Decimal/minor-unit səhvi | Aşağı | **Yüksək** | Bütün pul integer minor; Hypothesis property-based test |
| Receipt printer uyğunsuzluğu (real) | Orta | Orta | Mock-da abstract; ESC/POS Faza AI-7 |

### 21.5 Təhlükəsizlik checklist (Faza AI-2)

- [ ] Catalog mutation → audit log (before/after)
- [ ] Bulk import: file size limit (10 MB), content-type, CSV formula injection qoruması
- [ ] Cash movement > 500 AZN → audit + secondary approval (config)
- [ ] Fiskal credentials Vault-da
- [ ] Receipt PDF: PII opsional, GDPR uyğun
- [ ] Flutter secure_storage: token, fiskal session
- [ ] Flutter root/jailbreak detection (admin xəbərdarlığı)

### **GATE G2 — POS Core done** (insan, ~1 saat) — yuxarıdakı acceptance

---

## 22. FAZA AI-3: ORDER + ADAPTER FRAMEWORK (~40-55 saat AI)

**Məqsəd:** Event-driven sifariş idarəsi + adapter çərçivəsi

**KRİTİK ARDIVCILLIQ:** Adapter Protocol ÖNCƏ, Webhook Ingress SONRA (webhook adapter-dən asılı)

### 22.1 Texniki məzmun

#### Order Schema
```sql
CREATE TABLE public.orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  store_id UUID NOT NULL,
  source_channel VARCHAR(50) NOT NULL,  -- pos, mock_marketplace, ...
  external_order_id VARCHAR(255),
  status VARCHAR(50) NOT NULL,  -- NEW, VALIDATED, ACCEPTED, PREPARING, READY, DISPATCHED, COMPLETED, CANCELLED
  total_minor BIGINT NOT NULL,
  tax_minor BIGINT,
  currency VARCHAR(3) NOT NULL,
  customer_jsonb JSONB,  -- {name, phone, address}
  version INTEGER DEFAULT 0,  -- optimistic lock
  status_machine_version VARCHAR(20) DEFAULT 'v1',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(tenant_id, source_channel, external_order_id)
);

CREATE TABLE public.order_lines (
  id UUID PRIMARY KEY,
  order_id UUID NOT NULL REFERENCES orders(id),
  variant_id UUID,
  qty INTEGER NOT NULL,
  unit_price_minor BIGINT NOT NULL,
  tax_minor BIGINT,
  metadata_jsonb JSONB
);

CREATE TABLE public.order_events (
  id UUID PRIMARY KEY,
  order_id UUID NOT NULL,
  from_status VARCHAR(50),
  to_status VARCHAR(50) NOT NULL,
  actor_id UUID,
  note TEXT,
  at TIMESTAMP DEFAULT NOW()
);

-- Webhook DLQ
CREATE TABLE public.webhook_dlq (
  id UUID PRIMARY KEY,
  channel_code VARCHAR(50) NOT NULL,
  payload JSONB NOT NULL,
  error TEXT NOT NULL,
  received_at TIMESTAMP DEFAULT NOW()
);
```

#### State Machine
```
NEW → VALIDATED → ACCEPTED → PREPARING → READY → DISPATCHED → COMPLETED
                       ↓
                   CANCELLED (only from NEW, VALIDATED, ACCEPTED)
```

#### ChannelAdapter Protocol (Pydantic + typing.Protocol)
```python
from typing import Protocol
from libs.canonical_model.adapter import (
    ChannelConnection, AuthResult, PushResult,
    StockUpdate, CanonicalProduct, CanonicalOrder, OrderStatus,
    RawPayload, CanonicalEvent
)

class ChannelAdapter(Protocol):
    channel_code: str

    async def authenticate(self, conn: ChannelConnection) -> AuthResult: ...
    async def push_catalog(self, items: list[CanonicalProduct]) -> PushResult: ...
    async def update_stock(self, updates: list[StockUpdate]) -> PushResult: ...
    async def fetch_orders(self, since: datetime) -> list[CanonicalOrder]: ...
    async def push_order_status(self, ext_order_id: str, status: OrderStatus) -> None: ...

    def parse_webhook(self, raw: RawPayload) -> CanonicalEvent: ...
    def verify_signature(self, raw: bytes, sig: str, secret: str) -> bool: ...
```

#### Webhook Ingress Endpoint
```http
POST /webhooks/{channel_code}
X-Signature: sha256=<hex_hmac>
X-Channel-Event-Id: <external_id>
Idempotency-Key: <derived from external_id>
Content-Type: application/json
Content-Length: <max 1 MB>

{ "event": "order.created", "data": {...} }

→ 202 Accepted (queued — adapter parse async)
→ 401 invalid HMAC
→ 409 duplicate (idempotency hit)
→ 413 payload too large
→ 422 schema validation failed
→ 429 rate limit (per-channel 10 req/s)
```

#### Order State Transition
```http
PATCH /v1/orders/{order_id}/status
If-Match: <version>
{ "to_status": "ACCEPTED", "actor_id": "<user>", "note": "..." }

→ 200 OK + Event: order.status.changed
→ 409 version mismatch
→ 422 Invalid transition (state machine reject)
```

#### Event Schema (`order.received`)
```yaml
# AsyncAPI 2.6
asyncapi: 2.6.0
channels:
  posnet_events:
    publish:
      message:
        name: OrderReceived
        payload:
          type: object
          required: [id, type, tenant_id, payload, timestamp]
          properties:
            id: {type: string, format: uuid}
            type: {const: "order.received"}
            tenant_id: {type: string, format: uuid}
            timestamp: {type: string, format: date-time}
            payload:
              type: object
              required: [order_id, source_channel, external_order_id]
              properties:
                order_id: {type: string, format: uuid}
                source_channel: {type: string}
                external_order_id: {type: string}
                total_minor: {type: integer}
                currency: {type: string, pattern: "^[A-Z]{3}$"}
```

### 22.2 Task siyahısı (12 task)

- **AI-3.1** — Order domain + State Machine: Order/OrderLine/OrderEvent/Return + transitions + invalid reject + optimistic locking
- **AI-3.2** — Canonical event schemas: `libs/canonical-model/events/` (OrderReceived, OrderAccepted, StockChanged, OrderStatusChanged) + AsyncAPI spec başlanğıcı
- **AI-3.3** — `ChannelAdapter` Protocol: `libs/canonical-model/adapter_protocol.py` (yuxarıdakı Protocol)
- **AI-3.4** — Canonical ↔ channel mapping framework: `libs/canonical-model/mapping/` (Product/Order/Payment helpers)
- **AI-3.5** — Adapter lifecycle: register → configure → test → enable → live; admin API
- **AI-3.6** — Circuit breaker + fallback: `libs/common/circuit_breaker.py` (pybreaker)
- **AI-3.7** — Webhook ingress (`services/webhook-ingress/`): yuxarıdakı endpoint kontrakti + HMAC + Schema + Idempotency + Rate limit + DLQ + 1MB limit
- **AI-3.8** — Event publish/consume: webhook → `order.received` pgmq → state machine → `order.validated`
- **AI-3.9** — Order CRUD API: list (filter), detail, status update, cancel
- **AI-3.10** — Unified Order Inbox (admin-web React modal): real-time WebSocket/SSE + filtering (channel, status, date) + actions + sound alert + virtual scroll
- **AI-3.11** — Fulfillment workflow: picking (warehouse → variant) + packing + dispatch (shipping label mock) + tracking number
- **AI-3.12** — Outbound webhook: merchant-ə status update (HMAC sign, retry, DLQ); admin UI konfiqurasiya

### 22.3 Acceptance criteria (Faza AI-3 Done)

- [ ] Order CRUD: create, list, detail, update — bütün test
- [ ] Webhook curl test (HMAC): 202, duplicate Idempotency-Key → 409
- [ ] Invalid HMAC → 401, malformed → 422, oversized → 413
- [ ] State machine: invalid keçid → 422
- [ ] AsyncAPI validate (`asyncapi validate docs/asyncapi/posnet.yaml`)
- [ ] DLQ: malformed payload → `webhook_dlq` cədvəlində görünür
- [ ] Unified inbox: yeni sifariş 5s ərzində görünür (real-time)
- [ ] pgmq publish/consume + DLQ canlı, retry exponential backoff işləyir
- [ ] coverage 80%+

### 22.4 Risklər (Faza AI-3)

| Risk | Ehtimal | Təsir | Azaltma |
|---|---|---|---|
| EventBus throughput limiti | Orta | Yüksək | Erkən load test, Kafka migrasiya planı |
| Adapter abstraksiyası generic deyil | Yüksək | Yüksək | 2+ mock kanal sxemi yoxla |
| Webhook DLQ böyüməsi | Orta | Orta | Alert + automated reprocess job |
| HMAC validation performansı | Aşağı | Orta | Async validation + secret cache |
| Real-time updates (WebSocket) miqyaslanmır | Orta | Orta | Polling fallback, Redis pub/sub backend |
| State machine race (eyni sifariş, 2 status) | Orta | **Yüksək** | Optimistic locking + idempotency-key |
| Unified inbox UI yavaş | Orta | Orta | Pagination, virtual scroll, channel filter |

### 22.5 Təhlükəsizlik checklist (Faza AI-3)

- [ ] Rate limit per-channel (10 req/s) + per-tenant (100 req/s)
- [ ] HMAC secret rotation: Vault path + 90-gün TTL alert
- [ ] HMAC timing attack qoruması: `hmac.compare_digest`
- [ ] Payload max 1 MB → 413
- [ ] JSON Schema strict (`additionalProperties: false`) → bilinməyən sahə 422
- [ ] Channel credentials Vault-da
- [ ] DLQ entry → audit log + PII redaction
- [ ] WebSocket: token-based auth, tenant filter server-side

### **GATE G3** — yuxarıdakı acceptance

---

## 23. FAZA AI-4: MOCK PILOT (~25-35 saat AI)

**Məqsəd:** End-to-end mock kanal — heç bir real partner gözləməsi. **★MVP TAMAMLANIR★**

### 23.1 Mock kanal arxitekturası

`mocks/mock-marketplace/` — real marketplace-i təqlid edən FastAPI servisi:

```
┌──────────────────────────────────────────┐
│  mocks/mock-marketplace/                 │
│  ┌────────────────────────────────────┐  │
│  │ POST /api/orders        (push)     │  │  ← Posnet stock/catalog push
│  │ POST /webhooks/order    (out)      │  │  → Posnet webhook ingress
│  │ POST /api/status        (in)       │  │  ← Posnet status update
│  │ GET  /api/orders        (poll)     │  │  ← Posnet pull
│  │                                    │  │
│  │ Configurable:                      │  │
│  │  - random latency (100-2000ms)     │  │
│  │  - 5% 5xx error                    │  │
│  │  - HMAC validation                 │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
                ↓ HMAC-signed webhook
┌──────────────────────────────────────────┐
│  Posnet webhook-ingress                  │
│  → MockMarketplaceAdapter.parse_webhook  │
│  → order.received event                  │
│  → State machine → unified inbox         │
│  → Admin accept                          │
│  → MockMarketplaceAdapter.push_status    │
└──────────────────────────────────────────┘
```

### 23.2 Onboarding wizard flow (admin UI)

```
1. Admin: "Add channel" → kanal seçimi (mock_marketplace)
2. Sistem credentials yaradır (HMAC secret Vault-a)
3. "Test webhook" → mock kanal Posnet-ə test webhook göndərir
4. 202 alınırsa → "Test passed"
5. "Enable" → channel_connection live olur
6. İlk real sifariş gözlənilir
```

### 23.3 Task siyahısı (9 task)

- **AI-4.1** — `mocks/mock-marketplace/` FastAPI servisi (Posnet-dən asılı deyil) + random latency + 5% 5xx + HMAC verify
- **AI-4.2** — `MockMarketplaceAdapter` (Posnet-də): `ChannelAdapter` Protocol implementasiyası — parse_webhook, push_catalog, update_stock, push_order_status
- **AI-4.3** — Onboarding wizard (admin UI): channel select → credentials → HMAC secret generate → test webhook → enable
- **AI-4.4** — Real-time sinxron: catalog push (Posnet → mock görür), stock change (mock-a push), order status (push merchant)
- **AI-4.5** — E2E ssenari (Playwright):
  - **Happy path:** mock sifariş → Posnet alır → unified inbox → admin accept → mock-da status update
  - **Offline:** kassir local accept → online sync → channel update
  - **Overselling:** stok -1 → order attempt → rejection → status channel-ə
  - **Refund:** mock cancel → Posnet refund → stok restore
  - **Channel downtime:** mock 5xx → retry + DLQ + reconcile
- **AI-4.6** — Adapter contract test (schemathesis): OpenAPI-driven fuzz — gələcək real adapter-lər üçün şablon
- **AI-4.7** — Performance test (k6): 100 sifariş/sec, 10 dəq sustained, p95 < 5s
- **AI-4.8** — Adapter SDK skeleton: `libs/adapter-sdk/` + docs + "hello-world adapter" template
- **AI-4.9** — Admin UI onboarding tutorial mode (ilk dəfə təcrübə)

### 23.4 Acceptance criteria (Faza AI-4 Done — MVP)

- [ ] E2E Playwright happy path keçir
- [ ] 4 edge-case (offline, overselling, refund, channel down) keçir
- [ ] 100 sifariş/sec k6 keçir, p95 < 5s
- [ ] Resilience: mock 5xx → retry işləyir
- [ ] Adapter SDK ilə "hello-world adapter" 1 saatda yazılır
- [ ] Reconciliation cron job: hər saat avtomatik diff
- [ ] Onboarding wizard: yeni mock channel < 4 saatda canlı
- [ ] coverage 80%+

**★ MVP HAZIRDIR ★** İstənildiyi vaxt real partner adapter-i əlavə edilə bilər (sadəcə `MockMarketplaceAdapter`-i kopyala, real API ilə dəyiş).

### 23.5 Risklər (Faza AI-4)

| Risk | Ehtimal | Təsir | Azaltma |
|---|---|---|---|
| Mock kanal real-dən fərqli davranır | Orta | Yüksək | Real partner API docs oxu, mock-u uyğunlaşdır |
| Order mapping bug-ları | Yüksək | Yüksək | Geniş E2E test, canary deploy gələcəkdə |
| Reconciliation drift | Orta | Yüksək | Saatlıq cron + alert > 5 sifariş drift |
| WebSocket scale | Orta | Orta | SSE alternativ, Redis pub/sub |
| Refund race (Posnet ↔ mock) | Orta | **Yüksək** | Idempotency-key, saga compensation |

### **GATE G4** — MVP tamamlandı

---

## 24. FAZA AI-5: ONLINE + CATEGORY PROFILE (~35-50 saat AI)

**Məqsəd:** Çoxkateqoriyalı platforma + online vitrin + delivery adapter framework

### 24.1 Capability config

`libs/canonical-model/category_capability.json`:
```json
{
  "food": {
    "features": ["modifier", "expiry_tracking"],
    "ui": {"product_card": "FoodCard", "checkout": "FoodCheckout"}
  },
  "apparel": {
    "features": ["variant", "size_chart"],
    "ui": {"product_card": "ApparelCard"}
  },
  "cosmetics": {
    "features": ["batch", "expiry_tracking"],
    "ui": {...}
  },
  "books": {...},
  "electronics": {...}
}
```

### 24.2 Task siyahısı (13 task)

- **AI-5.1** — Category capability JSON Schema + validator + per-tenant override
- **AI-5.2** — Capability-driven catalog: variant-ləri kateqoriyaya görə dynamic (food → modifier, apparel → size+color)
- **AI-5.3** — Capability-driven Flutter UI: dynamic render kateqoriyaya görə
- **AI-5.4** — Capability-driven admin UI: dynamic form builder (JSON Schema → React form)
- **AI-5.5** — `delivery-svc/` skeleton + `mocks/mock-courier/`: rider request + location mock + ETA
- **AI-5.6** — `MockCourierAdapter` (delivery `ChannelAdapter` impl)
- **AI-5.7** — Promosyon engine (`libs/promotion/`): rule engine — BOGO, %off basket, %off product, basket threshold, time-bound
- **AI-5.8** — Coupon system: code, single/multi-use, per-tenant, expiry
- **AI-5.9** — `storefront/` Next.js 15 App Router: SSR catalog, product detail, basket (Zustand), guest+registered checkout
- **AI-5.10** — Storefront checkout: address, delivery method, payment (mock PSP), confirmation email
- **AI-5.11** — Multi-warehouse routing: sifariş → ən yaxın anbar (haversine distance + stock availability)
- **AI-5.12** — Service ayırma planı (ADR-0015): `catalog-svc`, `inventory-svc`, `order-svc` skeleton qovluqlar
- **AI-5.13** — Cross-service contract test (Pact): service ayrılmadan əvvəl contract-lar

### 24.3 Acceptance (Faza AI-5)

- [ ] Storefront → sifariş et → Posnet inbox → admin accept → confirmation email
- [ ] Food: modifier ("extra cheese") işləyir
- [ ] Apparel: variant (rəng + ölçü) işləyir
- [ ] Promosyon: 2 al 1 pulsuz keçir
- [ ] Coupon: invalid code → 422
- [ ] Multi-warehouse: 2 anbar arasından düzgün yönləndirilir
- [ ] Mock courier delivery flow E2E
- [ ] coverage 80%+

### **GATE G5**

---

## 25. FAZA AI-6: ACCOUNTING + MULTI-COUNTRY (~40-60 saat AI)

**Məqsəd:** Mühasibatlıq + 2-ci bazara hazırlıq + GDPR/KVKK

### 25.1 Texniki məzmun

#### Double-entry ledger schema
```sql
CREATE TABLE public.accounts (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  code VARCHAR(20) NOT NULL,  -- e.g. "1100" (cash), "4000" (revenue)
  name TEXT NOT NULL,
  type VARCHAR(20) NOT NULL,  -- asset, liability, equity, revenue, expense
  parent_id UUID REFERENCES accounts(id),
  UNIQUE(tenant_id, code)
);

CREATE TABLE public.journal_entries (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  reference TEXT NOT NULL,  -- "sale:<sale_id>", "refund:<refund_id>"
  posted_at TIMESTAMP DEFAULT NOW(),
  posted_by UUID
);

CREATE TABLE public.journal_lines (
  id UUID PRIMARY KEY,
  entry_id UUID NOT NULL REFERENCES journal_entries(id),
  account_id UUID NOT NULL REFERENCES accounts(id),
  debit_minor BIGINT DEFAULT 0,
  credit_minor BIGINT DEFAULT 0,
  CHECK ((debit_minor > 0 AND credit_minor = 0) OR (debit_minor = 0 AND credit_minor > 0))
);

-- Invariant: hər journal_entry üçün SUM(debit) = SUM(credit)
```

#### Country profile config
`libs/canonical-model/country/az.py`:
```python
COUNTRY_AZ = CountryProfile(
    code="AZ",
    currency="AZN",
    locale="az_AZ",
    timezone="Asia/Baku",
    tax_rates={"VAT": Decimal("0.18")},
    fiscal_provider="opk",  # AZ Onlayn Nəzarət-Kassa
    efaktura_provider="efaktura.az",
    psp_providers=["pasha", "kapital"],
    date_format="dd.MM.yyyy",
)
```

### 25.2 Task siyahısı (14 task)

- **AI-6.1** — Double-entry ledger: Account, JournalEntry, JournalLine + debit=credit invariant
- **AI-6.2** — Account chart: AZ standart (5 səviyyə) + TR standart + per-tenant override
- **AI-6.3** — Journal entry posting: event-driven (order paid → revenue + tax + receivable; refund → reverse)
- **AI-6.4** — Invoice generation: ReportLab PDF + structured JSON + per-country template
- **AI-6.5** — E-faktura provider abstraction (Protocol)
- **AI-6.6** — `mocks/mock-efaktura-az/`: e-Faktura.az format (UBL-AZ XML)
- **AI-6.7** — `mocks/mock-efaktura-tr/`: GİB format (UBL-TR XML — Logo/Mikro)
- **AI-6.8** — Country profile config: AZ + TR
- **AI-6.9** — Multi-currency: `Money` type genişləndir + FX provider (`libs/fx/`) + mock rates (sonra real CBAR/TCMB)
- **AI-6.10** — i18n full: frontend (admin + storefront) az/tr/en + lokalize tarix, valyuta, ədəd
- **AI-6.11** — Settlement engine: gündəlik PSP statement reconciliation (mock PSP → ledger match → discrepancy)
- **AI-6.12** — Tax calculation engine: AZ ƏDV 18%, TR KDV 8/18%, configurable per-category
- **AI-6.13** — GDPR/KVKK data subject rights: `POST /v1/privacy/export` (user data JSON), `POST /v1/privacy/delete` (anonymize, ledger qoruyur), audit log
- **AI-6.14** — Reporting: P&L, balance sheet, tax report, sales by channel/category (CSV + PDF)

### 25.3 Acceptance (Faza AI-6)

- [ ] AZ tenant: AZN sifariş → ƏDV 18%
- [ ] TR tenant: TRY sifariş → KDV
- [ ] Invoice PDF (AZ + TR formatları)
- [ ] Ledger balance: debit = credit hər zaman
- [ ] GDPR export: user data JSON
- [ ] GDPR delete: anonymize, ledger qoruyur

### **GATE G6 — hüquqi məsləhət tövsiyə**

---

## 26. FAZA AI-7: SCALE + DR + CLOUD (~50-80 saat AI)

**Məqsəd:** Lokal dev → cloud production-ready + real external inteqrasiyalar

### 26.1 Cloud provider matrisi

| Provider | $/ay (small) | Latency AZ/TR | Managed | AI |
|---|---|---|---|---|
| **Hetzner** | $50-100 | yaxşı (DE) | DIY | orta |
| **DigitalOcean** | $100-200 | yaxşı (DE/NL) | tam | yüksək |
| **Vultr** | $80-150 | yaxşı | tam | yüksək |
| **AWS** | $300-500 | əla (FRA) | əla | yüksək |

**Tövsiyə:** DigitalOcean (sadə, managed, ucuz). Scale-də AWS-ə miqrasiya.

### 26.2 Task siyahısı (20 task)

- **AI-7.1** — Cloud provider qərarı (ADR-0020) — **insan**
- **AI-7.2** — Terraform modul: `infra/terraform/modules/{network,kubernetes,database,cache,storage,secrets}`
- **AI-7.3** — Terraform environments: `infra/terraform/envs/{staging,prod}/`
- **AI-7.4** — Infracost integration: PR-də cost diff
- **AI-7.5** — Helm chart hər servis üçün
- **AI-7.6** — ArgoCD setup (GitOps): manifest sync, auto-deploy on tag
- **AI-7.7** — Vault prod: Raft storage + auto-unseal (cloud KMS) + TLS
- **AI-7.8** — Secret migration (lokal Vault → prod)
- **AI-7.9** — DB backup + restore + cross-region replication + runbook
- **AI-7.10** — Multi-region DR (active-passive): RPO < 1h, RTO < 30 dəq
- **AI-7.11** — **REAL fiskal cihaz (AZ+TR)**: vendor SDK adapter — **insan: cihaz alınıb**
- **AI-7.12** — **REAL PSP** (Pasha/Kapital AZ; iyzico TR): sandbox test — **insan: müqavilə + API key**
- **AI-7.13** — **REAL e-faktura** (e-Faktura.az; Logo/Mikro): sandbox — **insan: provider müqaviləsi**
- **AI-7.14** — PCI compliance review + remediation
- **AI-7.15** — Load test cloud-da: k6, 1000 sifariş/sec, 30 dəq sustained
- **AI-7.16** — Chaos engineering: network partition, DB failover, pod kill (Litmus)
- **AI-7.17** — ClickHouse analytics (opsional)
- **AI-7.18** — CRM/loyalty skeleton (points, tiers, redemption)
- **AI-7.19** — `booking-svc/` skeleton (rezervasiya)
- **AI-7.20** — Pen-test (nuclei + manual) + status page

### 26.3 Acceptance (Faza AI-7)

#### **GATE G7 — Staging** (insan, ~2 saat)
- [ ] Terraform plan oxudum
- [ ] Infracost: aylıq $X qəbul
- [ ] Backup test: DB restore staging
- [ ] Smoke test cloud staging keçir

#### **GATE G8 — Production go-live** (insan, ~4 saat)
- [ ] Pilot müştəri tapıldı + müqavilə
- [ ] DR test keçdi (RPO/RTO ölçüldü)
- [ ] On-call rotasiya
- [ ] Status page
- [ ] Real partner: sandbox credentials Vault-da, contract test keçir
- [ ] Real PSP: hüquqi PCI review keçdi
- [ ] Real e-faktura: provider müqaviləsi
- [ ] Real fiskal: cihaz alınıb, drayver test
- [ ] Pen-test passed (kritik vulnerability yox)
- [ ] Incident runbook hazır

---

# PART V — KONTROL VƏ TESTLƏMƏ

## 27. HUMAN CONTROL GATES — XÜLASƏ

| Gate | Faza | Niyə | İnsan vaxtı |
|---|---|---|---|
| **G0** | AI-0 done | Bootstrap verify | ~10 dəq |
| **G1** | AI-1 done | Auth + RLS kritik | ~30 dəq |
| **G2** | AI-2 done | Pul hesablanır | ~1 saat |
| **G3** | AI-3 done | Webhook canlı | ~45 dəq |
| **G4** | AI-4 done | MVP, hələ lokal | ~1 saat |
| **G5** | AI-5 done | Online satış başlayır | ~1 saat |
| **G6** | AI-6 done | **Hüquqi məsləhət** | ~2 saat |
| **G7** | AI-7 staging | **PUL XƏRCLƏNƏCƏK** | ~2 saat |
| **G8** | AI-7 prod | **REPUTASIYA RİSKİ** | ~4 saat |

**Mini-gate** — task `requires_human: true` olduqda AI dayanır.

## 28. VERİFİKASİYA STRATEGİYASI

### 28.1 Test piramidası
| Layer | Pay | Tool | Vaxt |
|---|---|---|---|
| Unit | 70% | pytest | <1s |
| Integration | 20% | pytest + testcontainers | 5-30s |
| Contract | 5% | schemathesis + Pact | 10-60s |
| E2E | 5% | Playwright + curl + Flutter integration_test | 30s-5dəq |
| Load | per-faza | k6 / Locust | 5-30 dəq |
| Security | per-faza | bandit + nuclei + custom | dəyişkən |

### 28.2 Coverage gate
- Per-PR: 80% minimum (CI fail əgər aşağı)
- Per-faza: 85% məqsəd
- Kritik path (auth, RLS, payment, fiscal, ledger): 95%

### 28.3 `make verify`
```makefile
verify:
    ruff check .
    ruff format --check .
    mypy --strict services/ libs/
    pytest --cov=services --cov=libs --cov-fail-under=80
    bandit -r services/ libs/ -q
    detect-secrets scan --baseline .secrets.baseline
    pnpm -r lint
    pnpm -r typecheck
```

### 28.4 `make smoke` (faza sonu)
Faza-spesifik script: kritik endpoint + healthcheck + sample flow

### 28.5 `make load` (AI-4+)
k6 script `tests/load/`; AI-4: 100/s; AI-7: 1000/s

## 29. TEST SSENARİLƏRİ KATALOQU (FAZA-0-TDD-dən inteqra)

### Auth testlər
```python
def test_jwt_validation_valid_token(keycloak_client):
    token = keycloak_client.get_token("user", "pass")
    decoded = decode_jwt(token)
    assert decoded["sub"] == "user_id"

def test_jwt_validation_expired_token():
    expired_token = create_token(expires_in=-1)
    with pytest.raises(TokenExpiredError):
        decode_jwt(expired_token)

def test_jwks_cache_hit(redis_mock):
    decode_jwt(token)
    decode_jwt(token)  # 2nd call from cache
    assert redis_mock.calls == 1
```

### RLS izolasiya
```python
def test_rls_isolation(db_session):
    set_tenant_context(db_session, TENANT_A_ID)
    result = db_session.execute(select(User))
    assert all(u.tenant_id == TENANT_A_ID for u in result)

def test_rls_no_context_returns_empty(db_session):
    # No SET LOCAL → no rows
    result = db_session.execute(select(User))
    assert result.scalar() is None
```

### EventBus
```python
async def test_pgmq_publish_consume():
    await eventbus.publish("test_q", {"hello": "world"})
    msg = await eventbus.consume("test_q", timeout=1)
    assert msg.payload == {"hello": "world"}

async def test_dlq_on_max_retry():
    # 5 fail → DLQ
    for _ in range(5):
        await eventbus.publish("test_q", bad_payload)
    dlq = await eventbus.consume("dlq_test_q", timeout=1)
    assert dlq is not None
```

### Idempotency
```python
async def test_idempotency_key_dedup(client):
    response1 = await client.post("/v1/orders", json={...}, headers={"Idempotency-Key": "key1"})
    response2 = await client.post("/v1/orders", json={...}, headers={"Idempotency-Key": "key1"})
    assert response1.json()["id"] == response2.json()["id"]
```

### Overselling protection
```python
async def test_overselling_optimistic_lock(client):
    # 2 cihaz eyni anda son ədədi satmaq istəyir
    results = await asyncio.gather(
        client.post(f"/v1/inventory/{vid}/movements", json={"qty": 1, "expected_version": 5}),
        client.post(f"/v1/inventory/{vid}/movements", json={"qty": 1, "expected_version": 5}),
    )
    successes = [r for r in results if r.status_code == 201]
    conflicts = [r for r in results if r.status_code == 409]
    assert len(successes) == 1
    assert len(conflicts) == 1
```

### State machine
```python
def test_invalid_transition_rejected():
    order = Order(status="NEW")
    with pytest.raises(InvalidTransitionError):
        order.transition_to("DISPATCHED")  # NEW → DISPATCHED yox

def test_valid_transition_emits_event():
    order = Order(status="NEW")
    order.transition_to("VALIDATED")
    assert order.status == "VALIDATED"
    assert any(e.type == "order.status.changed" for e in order.events)
```

### HMAC validation
```python
def test_hmac_valid_signature():
    body = b'{"event": "order.created"}'
    sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    assert verify_signature(body, f"sha256={sig}", SECRET) is True

def test_hmac_timing_attack_protection():
    # hmac.compare_digest is constant-time
    assert verify_signature(body, "sha256=invalid", SECRET) is False
```

### Decimal money (property-based)
```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=0, max_value=10**9), st.integers(min_value=0, max_value=10**9))
def test_money_addition_associative(a, b):
    money_a = Money(a, "AZN")
    money_b = Money(b, "AZN")
    assert (money_a + money_b).minor == a + b
```

## 30. RİSK REYESTRİ (MASTER-dan)

| Risk | Ehtimal | Təsir | Azaldılma |
|---|---|---|---|
| **Partner-gated kanal giriş gecikir** | **Yüksək** | Yüksək | İz A paralel başla; açıq API-yə odaklan; AI-4 mock ilə MVP təmin |
| **Fiskal/e-faktura mürəkkəbliyi** | Orta | **Yüksək** | Erkən hüquqi danışıqlar; AI-2-də mock; AI-7-də real (insan icazəsi) |
| **Overselling (stok itkisi)** | Orta | **Yüksək** | Real-time + rezerv + reconcile; optimistic locking; test coverage |
| **Kanal API dəyişikliyi** | **Yüksək** | Orta | Contract test; version pin; adapter isolation |
| **Offline data itkisi** | Orta | **Yüksək** | Jurnal + idempotent sinxron; 3x test |
| **Multi-tenant data sızması** | Aşağı | **KRİTİK** | RLS + audit + pen-test; zero trust |
| **Performance bottleneck (Python)** | Aşağı | Orta | Profiling; async/await; kritik servis Go-ya |
| **AI səhv qərarı (ADR-əsaslı)** | Orta | Orta | Hər major qərar ADR + insan təsdiqi |
| **Sirr leak** | Aşağı | **KRİTİK** | detect-secrets pre-commit + CI gate (məcburi) |
| **AI loop (eyni xəta təkrar)** | Orta | Aşağı | 3-cəhd limit + STOP → insan |

## 31. TƏHLÜKƏSİZLİK MASTER CHECKLİST

(Hər faza üçün §20.5, 21.5, 22.5-də spesifik olanlar; bu master)

- [ ] Bütün API endpoint-də auth məcburi (test: 401 əgər token yoxdur)
- [ ] Bütün API endpoint-də `@require_permission` decorator
- [ ] Bütün mutation → audit log (actor, action, before/after)
- [ ] HTTPS only (Caddy + mkcert lokal; TLS prod)
- [ ] Security headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- [ ] CORS strict origins (env-config)
- [ ] Rate limit: per-tenant + per-channel (webhook)
- [ ] HMAC: `compare_digest` (timing-safe), 90-gün rotation
- [ ] JWT signature verify, expiry check, JWKS cache
- [ ] Sirr-lər Vault-da, kodda yox (detect-secrets məcburi)
- [ ] PII: GDPR/KVKK export + delete + redaction
- [ ] Webhook: 1 MB limit, JSON Schema strict
- [ ] Dependency vulnerability: pip-audit + npm-audit CI gate
- [ ] Pen-test (AI-7.20)
- [ ] Incident response runbook

---

# PART VI — DEPLOYMENT VƏ ƏMƏLİYYAT

## 32. LOKAL DEV — CLI CHEATSHEET

```bash
# Setup
make bootstrap          # İlk dəfə (up + verify)
make up                 # docker-compose up
make down               # docker-compose down

# Develop
make migrate            # Alembic migrate head
make seed               # Seed test data
make backup             # pg_dump → MinIO

# Quality
make verify             # lint + type + test + security
make test               # yalnız pytest
make test PATTERN=foo   # selektiv
make lint               # ruff + mypy
make format             # ruff format
make smoke              # faza-spesifik smoke
make load               # k6 (AI-4+)

# Git/CI
git commit -m "feat(scope): description"
gh pr create
gh run watch

# Vault (lokal dev)
vault kv put secret/posnet/db user=posnet password=...
vault kv get secret/posnet/db

# Caddy URL-lər (lokal)
https://posnet.local         # core API
https://admin.posnet.local   # admin web
https://keycloak.posnet.local
https://mail.posnet.local    # Mailpit
https://s3.posnet.local      # MinIO
http://localhost:16686       # Jaeger
http://localhost:9090        # Prometheus
http://localhost:3000        # Grafana
```

## 33. CLOUD DEPLOYMENT (G7 sonra)

### Deployment ardıcıllığı
1. `terraform plan` — insan oxuyur
2. Infracost — aylıq xərc tahmini
3. **G7 icazəsi**
4. `terraform apply` (staging)
5. Smoke + load test staging
6. **G8 icazəsi**
7. `terraform apply -var env=prod`
8. ArgoCD sync prod

### Rollback
- Hər deploy versioned (git tag)
- ArgoCD rollback: `docs/runbooks/rollback.md`
- DB migration: hər forward `--reversible` (Alembic downgrade)
- Adapter: previous version eyni anda live (parallel run option)

## 34. ÇATIŞMAZLIQ HALLARI (RECOVERY)

### 34.1 AI ilişdikdə (loop detection)
- Eyni xəta 3 dəfə → STOP → STATUS.md `STUCK: <issue>` → HUMAN-GATES.md sual
- İnsan diaqnoz: cari prompt, fərqli yanaşma təklif

### 34.2 Context dolduqda
- AI `HANDOFF.md` yazır (§50 format)
- Yeni sessiya: CLAUDE.md → STATUS.md → HANDOFF.md → davam

### 34.3 Test fail (deterministik)
- AI 3 cəhd; hələ də fail → STATUS.md `FAIL: <test>` → insan

### 34.4 Test flaky
- pytest-rerunfailures (max 2)
- Hələ də flaky → issue + `@pytest.mark.flaky` + task "investigate flake"

### 34.5 Git konflikt
- AI heç vaxt `--force` push
- Konflikt → `git stash` → STATUS.md → insan

### 34.6 Dependency vulnerability
- pip-audit CI fail → alternativ paket axtar və ya minor version → ADR

## 35. OBSERVABILITY MASTER PLAN

### Tracelər (OTel)
- `webhook.ingress.received` (AI-3)
- `event.publish` (AI-1)
- `event.consume` (AI-1)
- `order.transition` (AI-3)
- `adapter.<channel>.<op>` (AI-3+)
- `sale.create` (AI-2)
- `inventory.move` (AI-2)
- `fiskal.print` (AI-2)
- `shift.close` (AI-2)
- Trace correlation: webhook → order → status update (eyni `trace_id`)

### Metriklər (Prometheus)
- `http_requests_total{method, route, status, tenant_id}`
- `db_query_duration_seconds{op, table}`
- `event_publish_latency_seconds`
- `event_consume_lag_seconds`
- `dlq_depth{queue}`
- `order_state_transition_total{from, to}`
- `webhook_received_total{channel, status}`
- `sales_total{store_id, method}`
- `inventory_movements_total{type}`
- `fiskal_failures_total`
- `shift_open_duration_seconds`
- `channel_api_calls_total{channel, op, status}`
- `channel_api_latency_seconds`
- `sync_lag_seconds{channel}`
- `reconciliation_drift_total{channel}`

### Dashboardlar (Grafana)
- API Overview (AI-1)
- Order Flow (AI-3)
- POS Operations (AI-2)
- Channel Health (AI-3+)
- Pilot Customer (AI-4)

### Alertlər (Prometheus AlertManager)
- DLQ depth > 100
- Event consume lag > 30s
- Webhook 5xx rate > 1%
- Channel adapter circuit-open
- Fiskal queue depth > 50
- Shift > 14 saat açıq
- Stok < min_qty
- Sync lag > 60s
- Reconciliation drift > 5 sifariş
- Cloud (AI-7): CPU > 80% 5dəq, memory > 90% 2dəq, disk > 85%

---

# PART VII — AI-OPERASYON KONVENSİYALARI

## 36. STATUS.md FORMATI (live state)

```markdown
# STATUS — Posnet

**Cari faza:** AI-1 (FOUNDATION)
**Cari task:** AI-1.14 (pgmq publisher/consumer)
**Son commit:** abc1234 — "feat(eventbus): add publisher with outbox"
**Son uğurlu verify:** 2026-06-01 14:23 UTC+4
**Vəziyyət:** IN_PROGRESS  (IN_PROGRESS | BLOCKED | STUCK | GATE_WAIT | DONE)

## Tamamlanmış
- [x] AI-0.1 — Monorepo skeleton (commit: 1111aaa) — 2026-06-01 09:00
- ...

## İcrada
- [ ] AI-1.14 — pgmq setup
  - Başlanma: 2026-06-01 14:00
  - Progress: publisher hazır, consumer yarımçıq

## Növbəti
- [ ] AI-1.15 — Tenant onboarding
- [ ] AI-1.16 — User CRUD

## Açıq Suallar (İnsan üçün)
(None)

## Bloklar
(None)

## Gate vəziyyəti
- G0: ✅ 2026-06-01 11:00
- G1: ⏳ gözləyir
- G2-G8: planlandı
```

## 37. HUMAN-GATES.md FORMATI

```markdown
# HUMAN GATES — Posnet

## Gate Statusu (cədvəl)
[G0-G8 cədvəli]

## Açıq Suallar
### Q-001 — [başlıq]
**Soruşan:** AI sessiya (Faza AI-1.7)
**Tarix:** 2026-06-01 10:30
**Kontekst:** ...
**Variantlar:**
- A) ...
- B) ...
**Tövsiyə:** A
**Cavab:** (insan)
**Cavab tarixi:** (insan)

## Gate Keçidləri (jurnal)
### G-0 — Bootstrap done
**Tarix:** 2026-06-01 11:00
**Yoxlama nəticələri:** [...]
**Status:** ✅ APPROVED
**İmza:** PC, 2026-06-01

## Sirr Tələbləri
### Secret-001 — [ad]
**Tələb edən:** AI sessiya (AI-X.Y)
**Vault path:** secret/posnet/...
**İcra status:** ⏳ Gözləyir | ✅ Yazıldı | ❌ Ləğv
```

## 38. HANDOFF.md FORMATI (kontekst dolduqda)

```markdown
# HANDOFF — Posnet

**Tarix:** 2026-06-01 17:30
**Səbəb:** Kontekst 80%, task tamamlanmadan estafet

## Cari vəziyyət
**Faza:** AI-1 (FOUNDATION)
**Task:** AI-1.14 (pgmq publisher/consumer)
**Progress:** 40% — publisher hazır, consumer yarımçıq

## Son commit
- Hash: `abc1234`
- Mesaj: "feat(eventbus): add publisher with outbox"
- Working tree clean: no — `libs/eventbus/consumer.py` partial

## Açıq fayllar / üzərində işlədiyim
- libs/eventbus/consumer.py — partial
- tests/integration/test_eventbus.py — DLQ test missing

## Növbəti addım (yeni sessiya nə etməlidir)
1. `git diff HEAD` oxu — uncommitted
2. `tests/integration/test_eventbus.py`-də `test_dlq_on_max_retry` yaz
3. Consumer DLQ branch implement
4. `make test PATTERN=eventbus` keçəndə commit
5. STATUS.md yenilə → AI-1.15-ə keç

## Açıq suallar (insan üçün)
(None)

## Diqqət edilməli pitfall-lar
- pgmq consumer long-poll timeout 30s
- testcontainers Postgres-də pgmq extension manual (init.sql)

## Kontekst-də vacib fayllar (yeni sessiya əvvəl oxusun)
- CLAUDE.md
- STATUS.md
- AI-ROADMAP.md §20 (Faza AI-1)
- libs/eventbus/publisher.py (hazır, referans)
```

## 39. ADR TEMPLATE

`docs/adr/_template.md`:
```markdown
# ADR-NNNN — [Qərar başlığı]

**Status:** PROPOSED | ACCEPTED | DEPRECATED | SUPERSEDED by ADR-NNNN
**Tarix:** YYYY-MM-DD
**Qəbul edən:** AI sessiya (Faza AI-X.Y) — insan təsdiqi: [tarix]

## Kontekst
[Niyə bu qərar lazımdır? Hansı problem həll olunur?]

## Variantlar
1. **Variant A:** ... (üstünlüklər / mənfilər)
2. **Variant B:** ...
3. **Variant C:** ...

## Qərar
[Hansı variant seçildi və niyə]

## Nəticələr
- **Müsbət:** ...
- **Mənfi:** ...
- **Risk:** ...

## Əlaqəli
- ADR-NNNN
- GitHub issue #...
```

## 40. RUNBOOK TEMPLATE

`docs/runbooks/_template.md`:
```markdown
# Runbook — [Incident adı]

**Severity:** P0 | P1 | P2
**Müddət hədəfi:** RTO < X dəq

## Detection
- Alert: [Prometheus alert adı]
- Symptom: [İstifadəçi nə görür]

## Mitigation (sürətli)
1. ...
2. ...

## Root cause analysis
[Necə diaqnoz qoymaq]

## Resolution
[Necə həll etmək]

## Post-mortem template
- Timeline
- Impact
- Root cause
- Action items
```

## 41. SUBAGENT İSTİFADƏ QAYDALARI

Claude Code subagent-ləri kontekst qoruyur:

| Subagent | Nə vaxt | Misal |
|---|---|---|
| **Explore** | 3+ Glob/Grep tələb edən araşdırma | "Bütün API endpoint-lər hansılardır?" |
| **Plan** | Çox-addımlı implementasiya planı | "Order State Machine necə qurulmalıdır?" |
| **general-purpose** | Açıq sual + multi-step | "OAuth flow Posnet-ə uyğun" |
| **simplify** (skill) | Task sonu kod review | Commit-dən əvvəl çağır |
| **verify** (skill) | Faza sonu — feature gerçəkdən işləyir? | Gate öncəsi |
| **security-review** (skill) | AI-1, AI-3, AI-6, AI-7 sonu | Auth, webhook, ledger, deploy |
| **fewer-permission-prompts** (skill) | Hər faza ortasında | Permission tweaks |

**Qayda:** Subagent-i öz işini etmək üçün delegate etmə — nəticəni AI özü qiymətləndirir.

## 42. MEMORY HYGIENE

### Yazılır:
- ✅ Layihə-spesifik qərarlar
- ✅ İnsan operatorun preferences
- ✅ Tez-tez istifadə olunan komandalar
- ✅ Surprising findings (bug kökü, performans)

### Yazılmır:
- ❌ Git history məlumatı
- ❌ ADR-da yer olan qərar
- ❌ Ephemeral state (STATUS.md-də)
- ❌ CLAUDE.md-də olan qaydalar

### Sessiya başında:
- AI MEMORY.md oxuyur (avtomatik)
- Relevant memory-ləri açır

### Sessiya sonunda:
- Yeni layihə-spesifik öyrəndim — qeyd
- Köhnəlmiş — sil və ya yenilə

---

# PART VIII — APPENDİX

## 43. CONVENTIONAL COMMITS

```
feat(scope): add new feature
fix(scope): fix bug
chore(scope): tooling, build
docs(scope): documentation
refactor(scope): code restructure (no behavior change)
test(scope): tests only
perf(scope): performance
ci(scope): CI/CD
```

**Trailer:** `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

## 44. PYTHON STİL QAYDALARI

- Pydantic v2 (BaseModel + ConfigDict)
- FastAPI dependency injection (`Depends`)
- async/await default
- SQLAlchemy 2 (`Mapped[T]` syntax)
- Domain layer pure Python (infrastructure-free)
- Type-hint hər funksiyada (mypy --strict keçməli)
- f-string > `.format()` > `%`
- pathlib > os.path
- `dict | None` > `Optional[dict]`
- Comment-lər: yalnız "niyə" (default heç bir comment)

## 45. NÖVBƏTİ ADDIM (İndi)

### İnsan operator (sən) — TODAY:
1. ✅ Bu sənədi oxudun (v3.0)
2. [ ] §13 PREFLIGHT-i tamamla
3. [ ] STATUS.md, HUMAN-GATES.md, CLAUDE.md artıq mövcuddur
4. [ ] Yeni Claude Opus sessiya başlat və əmr ver:
   > "STATUS.md və AI-ROADMAP.md oxu. Faza AI-0 Task AI-0.1-dən başla."

### Claude (gələcək sessiyalar) — hər dəfə:
1. CLAUDE.md → STATUS.md → AI-ROADMAP.md (cari faza) → HUMAN-GATES.md
2. Cari task götür, §-ni oxu
3. TDD → implement → verify → commit
4. STATUS.md yenilə
5. Gate-də DAYAN → HUMAN-GATES.md sual

---

## 46. SƏNƏD VƏZİYYƏTİ

**Status:** ACTIVE
**Versiya:** 3.0 (vahid istinad — bütün referans sənədlər inteqra)
**Son yenilənmə:** 1 İyun 2026
**Növbəti review:** Hər Gate keçidində

**Dəyişiklik qaydası:**
1. AI dəyişiklik təklif edir → ADR (`docs/adr/`)
2. İnsan operator təsdiqləyir
3. Dəyişiklik commit, version bumps

**Sənəd ownership:** Single source of truth. Konflikt halında bu sənəd qalib.

---

**Hazırdır. İcraya başla.**
