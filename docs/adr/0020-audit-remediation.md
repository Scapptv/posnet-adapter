# ADR-0020 — Dərin audit (2026-06-04) tapıntıları + remediation

**Status:** ACCEPTED
**Tarix:** 2026-06-04
**Qəbul edən:** AI sessiya (dərin audit) + İnsan operator (Scapptv)
**Əlaqəli:** ADR-0012 (hub reframe), ADR-0017 (DB security posture), ADR-0018 (sync model), ADR-0016 (audit hardening), ADR-0019 (fetch_listing)

## Kontekst

AI-2.5 (adapter framework + sync engine) üzərində ikinci dərin audit aparıldı (3 paralel adversarial agent — security / loyalty-correctness / core-correctness — + manual verifikasiya + canlı DB sorğuları + tam test suite). Audit zamanı iki proses müşahidəsi:

1. **Loyalty/adapter qarışıqlığı:** `feat/loyalty-client` (Paylo loyalty client, 3183 sətir) və `main` (marketplace hub) eyni working tree-də paralel işləndiyi üçün qarışıqlıq yarandı. Qərar: adapter (main) **yalnız əsas roadmap-a** (marketplace hub) uyğun qalır; loyalty `feat/loyalty-client` branch-ində izolyasiyada saxlanılır (silinmir). Loyalty-only deps (`tenacity`, `pybreaker`) main-dən çıxarıldı (commit `6e66e47`).
2. **Test-gigiyena:** audit zamanı working tree branch dəyişdi (test suite-i korladı) — gələcəkdə test/audit ayrıca `git worktree`-də aparılmalıdır.

Bu ADR audit tapıntılarını (loyalty xaricindəki) və onların remediation qərarlarını sənədləşdirir.

## Tapıntılar + remediation xəritəsi

| # | Risk | Tapıntı | Remediation qərarı | Status |
|---|---|---|---|---|
| **C1** | 🔴 | Consumer `system_sessionmaker` (superuser `posnet`, `bypassrls=true` — canlı təsdiq) üzərində işləyir, yalnız `app.current_tenant` GUC qoyur, `SET ROLE posnet_app` yox; dispatcher sorğuları tenant-filtrsiz → wire olunan kimi cross-tenant push. | **Dispatcher hər sorğusunu `tenant_id == event.tenant_id` ilə açıq filtrlə** (order_ingest pattern); defense-in-depth kimi consumer-i `SET LOCAL ROLE posnet_app` ilə tenant-scope-a sal (follow-up). | ✅ FIXED (bu branch) |
| **C2** | 🔴 | Dispatcher Auth/Permanent xətanı udur (`return None`) + `idempotent` key-i eyni tx-də commit edir → push baş vermədən key+arxiv commit → daimi səssiz drift (reconciliation hələ yoxdur). | **Non-retryable adapter xətası → DLQ-ya yönəlt** (raise et, udma); idempotency key uğursuz push-da commit olunmasın. | ✅ FIXED (bu branch) |
| **C3/C4** | 🔴 | (loyalty) breaker default-da açılmır + açıq breaker slow-retry. | feat/loyalty-client-də həll olunur (adapter scope-undan kənar). | ⏸️ DEFER (loyalty branch) |
| **H1** | 🟠 | Kanal webhook HMAC-ı yalnız `body`-ni imzalayır — timestamp/replay qoruması yox. | **Timestamp-bound imza + ±skew window** (loyalty verifier-in pattern-i); capability-də timestamp header; webhook endpoint enforce. | ✅ FIXED (bu branch) |
| **H4** | 🟠 | Outbox `ORDER BY created_at` tiebreak-siz; bir tx-dəki event-lər eyni `now()` → reorder. | **`outbox_events.seq BIGSERIAL`** monotonic; relay `ORDER BY seq`. | ✅ FIXED (bu branch) |
| **H5** | 🟠 | Pricing override eyni-scope + eyni `created_at` → qeyri-deterministik tiebreak. | **`ORDER BY ... created_at DESC, id DESC`** deterministik tiebreak; `set_override` `valid_from < valid_to` validasiya (M7). | ✅ FIXED (bu branch) |
| **H6** | 🟠 | Sync engine (dispatcher + webhook factory) yalnız testlərdə wire olunub — işlək deploy edilə bilən servis yoxdur. | **`create_app`/lifespan-da registry-driven wiring** (config-gated, `SYNC_DISPATCH_ENABLED`). | ✅ FIXED (bu branch) |
| **M1** | 🟡 | `DATABASE_APP_URL` boşsa tək-pool fallback (RLS 2-ci qatı itir). | Prod-da boş app URL / superuser app rolu start-da rədd edilsin. | 📋 DOC (follow-up) |
| **M2** | 🟡 | Rate limiter proxy arxasında peer IP-yə key verir; per-channel webhook limit wire olunmayıb. | Trusted `X-Forwarded-For` parse; per-channel webhook limit. | 📋 DOC (follow-up) |
| **M3** | 🟡 | `cashier` başqa kassirin vardiyasını aça/bağlaya bilir (`cashier_id` body-dən). | `cashier` rolu üçün `cashier_id` = authenticated principal; başqası üçün yalnız manager/admin. | 📋 DOC (follow-up) |
| **M4** | 🟡 | Half-open breaker konkurent probe buraxır. | One-shot flag + lock; cari tək-consumer istifadəsində latent. | 📋 DOC (follow-up) |
| **M5** | 🟡 | `record_cash`/`close_shift` lock-suz → bağlanan vardiyaya nağd yazıla bilir. | Shift sətrini `with_for_update`; və ya trigger. | 📋 DOC (follow-up) |
| **L1-L8** | 🟢 | (loyalty token snapshot, idempotency tenant-scope, X-Request-ID sanitization, JWT aud[0], canonical schema_version marker, webhook event_id min_length və s.) | Aşağı təsir; follow-up backlog. | 📋 DOC (follow-up) |

(Tam sübutlar + exploit ssenariləri audit sessiya transkriptindədir; hər tapıntı file:line ilə təsdiqlənib.)

## Qərar

**Critical + High tapıntıları bu branch-də (`fix/audit-remediation`) TDD ilə düzəldilir** (C1, C2, H1, H4, H5, H6), hər biri öz atomik commit-i ilə. Medium/Low tapıntılar burada **sənədləşdirilir** (follow-up backlog) — axını düzgün/səhvsiz edən nüvə Critical+High-dır; M/L əlavə möhkəmləndirmədir.

Strateji müşahidə (kod deyil): **mobil POS app mövcud deyil** (`apps/pos-flutter` boş). Məhsul "POS lövbərli"dir, amma POS girişi yazılmayıb — G-V validasiyasından əvvəl roadmap-da yenidən qiymətləndirilməlidir (AI-ROADMAP.md follow-up).

## Nəticələr

### Müsbət
- Outbound sync (dispatcher) artıq tenant-safe (C1) və uğursuz push-u itirmir/DLQ-ya verir (C2) — marketplace hub multi-tenant-da düzgün axır.
- Inbound webhook replay-ə davamlı (H1); event/qiymət ardıcıllığı deterministik (H4/H5); sync engine deploy edilə bilən (H6).
- Adapter loyalty-dən təmiz — yalnız əsas roadmap.

### Mənfi / qalıq risk
- M/L tapıntıları açıq qalır (sənədləşib) — prod-dan əvvəl (G7) həll edilməli, xüsusən M1 (single-pool) + M3 (shift authz).
- C1 üçün defense-in-depth (consumer SET ROLE) hələ tətbiq olunmayıb — dispatcher açıq filtri əsas qorumadır; consumer-pool hardening follow-up.

## Əlaqəli
- ADR-0017 (RLS/dual-pool), ADR-0018 (sync model), ADR-0019 (fetch_listing)
- AI-ROADMAP.md §17.3 (sync), §17.4 (reconciliation); HUMAN-GATES.md (audit qeydi)
