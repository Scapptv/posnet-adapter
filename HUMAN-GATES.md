# HUMAN GATES — Posnet

Bu fayl AI ↔ insan operator arasında gate keçidləri və açıq sualların jurnalıdır.

**Qayda:** AI gate-ə çatdıqda burada giriş yaradır. İnsan operator cavab/icazə verir. Bu fayl audit trail-dir.

---

## Gate Statusu

| Gate | Faza | Status | İcazə tarixi | İcazə verən |
|---|---|---|---|---|
| G0 — Bootstrap done | AI-0 | ✅ **APPROVED** | 2026-06-01 | Scapptv |
| G1 — Foundation done | AI-1 | ✅ **APPROVED (şərti)** | 2026-06-03 | Scapptv |
| **AI-2.H — Audit hardening** (ADR-0016) | AI-2 | ✅ **TAM** (avtonom, AI) | 2026-06-04 | — |
| **AI-2.5 — Adapter framework + 1 kanal** (ADR-0012, crown jewel) | AI-2 | ✅ **APPROVED** | 2026-06-05 | Scapptv |
| G2 — POS Core done (**MVP**) | AI-2 | ⏳ Planlandı | — | — |
| **G-V — Validasiya** (ADR-0011) | AI-2→3 | ▶ **CONTINUE** (operator qərarı; build+validate **paralel** — pivot hələ mümkün) | 2026-06-05 | Scapptv |
| G3 — Order Mgmt done | AI-3 | ❄️ Dondurulub | — | — |
| G4 — Mock Pilot done | AI-4 | ❄️ Dondurulub | — | — |
| G5 — Online + Category done | AI-5 | ❄️ Dondurulub | — | — |
| G6 — Accounting done (**hüquqi**) | AI-6 | ❄️ Dondurulub | — | — |
| G7 — Staging deploy (**$ ilk dəfə**) | AI-7 | ❄️ Dondurulub | — | — |
| G8 — Production go-live (**reputasiya**) | AI-7 | ❄️ Dondurulub | — | — |

> ❄️ = ADR-0011 ilə dondurulub; G-V (Validasiya) gate-i keçənə qədər başlanmır.

---

## Strateji Qərarlar (İnsan → AI)

### D-001 — Beachhead re-scope (audit forku)
**Tarix:** 2026-06-01
**Kontekst:** Tam audit həddən-artıq scope + validasiyasız qurma riskini göstərdi (M1–M4).
**Operator qərarları (3 fork):**
- **Yanaşma:** "Yalnız yenidən scope" — faza sırası saxlanılır, AI-3…AI-7 dondurulur,
  AI-2-dən sonra **G-V validasiya gate**.
- **Beachhead:** Kafe/restoran + kiçik pərakəndə (Azərbaycan); v1 = ortaq nüvə.
- **Satıcı çıxışı:** Var (operator tanışları) → validasiya paraleldir.
**Nəticə:** ADR-0011 yaradıldı. Növbəti: validasiya toolkit + AI-0…AI-2 icrası.

### D-002 — Məhsul reframe: POS-anchored İnteqrasiya Hub
**Tarix:** 2026-06-01
**Kontekst:** Operator dəqiqləşdirdi — məhsul TSoft/Entegra/ChannelEngine tipli inteqrasiya
hub-ıdır (POS lövbər; merchant öz mağazasını portallara çıxarır). Adapterlər periferik deyil, CORE.
Audit + ADR-0011 bunu az qiymətləndirmişdi. AI dünya referanslarını araşdırdı (bax ADR-0012).
**Operator qərarları (2 fork):**
- **Bazar:** Azərbaycan əvvəl (konsolidasiya kanallar Birmarket+Trendyol; integrator rəqabəti az).
- **İlk dilim:** Pərakəndə × Marketplace (ilk kanal Birmarket/Trendyol; SKU/barkod canonical model).
**Nəticə:** ADR-0012 yaradıldı (ADR-0011-i incələşdirir — adapter framework + 1 kanal CORE/MVP).

**Partner gate (D-002 nəticəsi) — İNSAN:** Birmarket (ex-Umico) və/və ya Trendyol **seller/marketplace
API access** (sandbox + credential). AI bunu edə bilməz (partner müraciəti). **Bloklamır:** AI mock
Birmarket adapteri ilə framework-i qurur, real credential gələndə swap. Texniki qeyd: Trendyol-un
public Marketplace API-si sənədlidir → ilk REAL adapter texniki olaraq Trendyol daha asan ola bilər.
**Status:** ⏳ İnsan müraciət edəcək (paralel).

### D-003 — Sirr human-gate sərhədi dəqiqləşdirildi (dev vs prod)
**Tarix:** 2026-06-02
**Kontekst:** AI-1.7 (Keycloak realm) əvvəlcə "sirr gate-i" kimi çərçivələndi (client secret → Vault).
Operator peşəkar yenidən-baxış istədi. Aydınlaşdı: dev-mode credential (Keycloak, DB, Vault dev
token) AI-nin qurduğu dev mühitinin hissəsidir və onsuz da `# pragma: allowlist secret` ilə commit
olunub — bu **prod secret deyil**.
**Qərar:** Human-gate yalnız (a) AI-nin əldə edə bilmədiyi REAL external credential (kanal API key,
D-002) və (b) PROD secret-lər (real Vault, G7) üçündür. Foundation Keycloak **secret-siz** qurulur
(public+PKCE + bearer-only) → AI-1.7 dev-də **gate-li deyil**.
**Nəticə:** ADR-0014 yaradıldı. AI-1.7 icra olundu (gate olmadan).

---

## Açıq Suallar (AI → İnsan)

### Q-001 — AI-2.H1 canlı yoxlama (operator smoke) ✅ **PASSED** (2026-06-04, AI sessiya)
**Soruşan:** AI sessiya (Faza AI-2.H1)
**Tarix:** 2026-06-04
**Kontekst:** AI-2.H1 (Security posture, ADR-0017) kod tərəfi tam — 14 yeni avtomatik test (RLS FORCE, posnet_app non-owner LOGIN, dual-pool izolasiya, posnet_resolve_tenant) lokal-da yaşıl. İki dilim **canlı təsdiq** istəyirdi: (a) Keycloak realm parol substitusiyası + OIDC round-trip; (b) Dev app DATABASE_APP_URL pool smoke.

**Nəticə (canlı icra, dev stack — `adapter_keycloak` + `adapter_postgres` containers):**

**Smoke (a) Keycloak parol substitusiyası — ✅ PASSED:**
- `POSNET_OWNER_PASSWORD=owner-dev-2026` env var docker-compose-dan keycloak container-ə ötürüldü
- `--import-realm` substitution `${env.POSNET_OWNER_PASSWORD}` → `realm-posnet.json` import-da
- OIDC password grant: `curl http://localhost:8080/realms/posnet/protocol/openid-connect/token` `client_id=posnet-pos`, `username=owner`, `password=owner-dev-2026` → 200 OK access_token
- Token decode (claims): `sub`, `iss=http://localhost:8080/realms/posnet`, `azp=posnet-pos`, `exp`, `iat`, `realm_access.roles=[tenant_admin]` — AI-2.H1 enforce edən `require_exp/iat/sub` JWT validasiyası bu token-i qəbul edir

**Smoke (b) DATABASE_APP_URL pool — ✅ PASSED (alembic upgrade head 0001→0011 sonra):**
- Role attrs (`SELECT FROM pg_roles WHERE rolname='posnet_app'`): `rolcanlogin=t`, `rolsuper=f`, `rolbypassrls=f` — non-owner LOGIN, NOSUPERUSER, NOBYPASSRLS
- **Layer-2 izolasiya:** `posnet_app` ilə `SELECT count(*) FROM users` (tenant scope-suz) → **0 sətir** (RLS blokladı, sızma yox)
- **Tenant-scope sorğu:** `SET app.current_tenant + SELECT FROM users` → yalnız öz tenant-ının 1 sətri
- **Cross-tenant resolver:** `posnet_resolve_tenant('smoke-sub')` → tenant uuid; `posnet_resolve_tenant('ghost-subject')` → NULL (SECURITY DEFINER işləyir, kilidli pool üçün tək cross-tenant yol)
- **Journal lockdown (H2):** posnet_app-dan `UPDATE/DELETE` cəhdi `stock_movements`/`cash_movements`/`audit_logs` üçün → 3-3 ERROR `permission denied for table ...`
- **Schema invariant (H2):** `INSERT variants (sku, sku)` təkrar → ERROR `duplicate key value violates unique constraint "uq_variants_tenant_sku"` (tenant-scoped UNIQUE)
- **CHECK constraints (H2):** `INSERT inventory (qty=-5)` → ERROR `ck_inventory_qty_nonneg`; `(qty=3, reserved=5)` → ERROR `ck_inventory_reserved_le_qty`; `(reserved=-1)` → ERROR `ck_inventory_reserved_nonneg`

**Yekun:** H1 + H2 invariant-ları lokal canlı stack-də sübuta yetir. `DATABASE_APP_URL` (posnet_app pool) prod-da məcburi qoyulmalıdır (boş qaldıqda system pool-a düşür, işləyir amma kilidli deyil).

**Cavab:** ✅ Hər ikisi keçdi (avtonom smoke icrası). Operator təsdiqi optional; istənərsə yuxarıdakı əmrlər təkrar oluna bilər.
**Cavab tarixi:** 2026-06-04 (AI smoke icrası — adapter_keycloak + adapter_postgres canlı stack)

### Q-002 — GitHub CI billing bloku (HUMAN-ONLY)
**Soruşan:** AI sessiya
**Tarix:** 2026-06-04
**Kontekst:** GitHub `Scapptv/posnet-adapter` (public) repo-sunda Actions workflows hazırdır, amma job-lar runner götürmür (0 step, log yox). Səbəb hesabda "recent payments failed" vəziyyəti — Actions icrası dayandırılıb. Public etmək "spending limit" hissəsini həll etdi (startup işləyir), amma "failed payment" hissəsi qalır. Bu **kod tərəfli problem deyil** — lokal `make verify` + 443 test yaşıl.

**Mənim icra sahəm xaricindədir** (CLAUDE.md "NƏ EDƏ BİLMƏRƏM"):
- Cloud account / billing edə bilmərəm (kart lazımdır)
- GitHub Support ticket aça bilmərəm (hesab sahibliyi yoxdur)

**Operator addımları (insan):**
1. GitHub → `Scapptv` hesabı → **Settings → Billing and licensed features** → ödəniş üsulunu yoxla
2. Köhnə kart expired-dirsə → yeni kart əlavə et / billing address yenilə
3. **Pending invoice** varsa → "Pay now" düyməsi ilə həll et
4. Bu işləmirsə → GitHub Support ticket (`https://support.github.com/contact`) → kateqoriya "Billing" → "Payment failed prevents Actions from running"
5. Billing düzələn kimi → Actions səhifəsində son workflow run-a `Re-run all jobs` bas → CI yaşıl olduqda buradakı status yenilənsin

**AI nə edir bu bitənə qədər:** Lokal verify (`make verify` + 443 test @ 99.88%) hər commit-də saxlanılır. Push olunan kod CI yaşıl olmasa belə kod-keyfiyyəti baxımından gate-i ödəyir. `v0.1.0-alpha` tag CI yaşıl olduqda çəkilə bilər.

**Variantlar:**
- A) Operator billing-i dərhal düzəldir, CI yaşıl olur, `v0.1.0-alpha` tag çəkilir
- B) Billing daha sonra düzəlir; AI-2.5 lokal-da davam edir, push pauzada
- C) Billing tamamilə bloklayır → GitHub Support ticket lazımdır

**Tövsiyə:** **B** — AI-2.5 kod tərəfdən billing-dən asılı deyil. Lokal stack tam işləyir; CI yaşıl yalnız tag çəkmək üçün lazımdır. Operator billing-i parallel həll edə bilər.
**Cavab:** (insan dolduracaq — billing düzəldildikdə "fixed: YYYY-MM-DD, CI run #N green")
**Cavab tarixi:** (insan dolduracaq)

### Q-003 — Real Posnet interfeysi + credential (POS-tərəfi connector swap)
**Soruşan:** AI sessiya (Faza AI-2.8)
**Tarix:** 2026-06-05
**Kontekst:** AI-2.8 (8.1–8.4) **mock-first Posnet connector**-i tam çatdırdı və **swap-ready**-dir (auth seam + config seam qoyuldu; bax **ADR-0022**). Uçtan-uca loop mock Posnet ilə sübut olundu (`test_e2e_full_loop.py`). **Real** swap üçün AI-nin əldə edə bilmədiyi üç şey lazımdır (CLAUDE.md "NƏ EDƏ BİLMƏRƏM" — external interfeys + real credential):
1. **Posnet API/DB/format spec** — catalog pull (məhsul/variant/stok/qiymət sahələri) + order push (sifariş/çek şəkli) endpoint-ləri.
2. **Auth sxemi + credential** — Bearer / API-key / HMAC / başqa; real sirr → **Vault**-a yazılmalı (AI yalnız `vault://...` ref istifadə edir).
3. **Per-tenant base URL**(lar).

**✅ UPDATE (2026-06-05) — İnterfeys MƏLUM oldu (1+3 həll):** Operator real Posnet layihəsini göstərdi (`C:\Users\PC\OneDrive\Desktop\Posnet A`, "API keys" sessiyası). AI araşdırdı + sənədləşdirdi → [docs/integrations/posnet-connector-spec.md](docs/integrations/posnet-connector-spec.md). Real Posnet = **UltimatePOS Connector API**: auth **Laravel Passport OAuth2 (password grant)** → Bearer; pull `GET /connector/api/variation`; push `POST /connector/api/sell`; base `{APP_URL}/connector/api`. Tam endpoint/shape/mapping spec-dədir.
**Beləliklə gate DARALDI → yalnız #2 (credential → Vault):** `base_url`, `oauth_client_id`, `oauth_client_secret`, `api_user`, `api_password` (Vault path-ları spec §6). OAuth client superadmin UI `/connector/clients`-də yaradılır. Operator bunları **Vault-a yazır** (repo-ya YOX). + config (sirr deyil): `location_id`, `walk_in_contact_id`, `price_includes_tax`.

**Connector build (credential gələndə, V1.4):** OAuth token manager + real `_to_canonical` (variation shape) + `push_order` (`/sell` + SKU→product_id/variation_id map) + per-tenant config. Spec §5. Upstream toxunulmur (`PosSourceAdapter` eyni).

**Variantlar:**
- A) Operator **indi** credential-ləri Vault-a yazır → AI real connector-i yazır (OAuth + mapping + contract test) və swap edir. (İnterfeys hazırdır → A artıq mümkündür.)
- B) **Sonra** → mock-first davam; real swap credential Vault-a yazılanda.

**Tövsiyə:** İnterfeys həll olundu. Növbəti = operator OAuth client yaradıb credential-ləri **Vault-a yazsın** (spec §6 path-ları) → AI dərhal real connector-i yazar. Vault dev-mode-dadır (ADR-0003); prod Vault G7. Test üçün operator bir Posnet instansiyası (staging/lokal) + API user verə bilər.
**Cavab:** (insan dolduracaq)
**Cavab tarixi:** (insan dolduracaq)

### Şablon
```markdown
### Q-NNN — [Qısa başlıq]
**Soruşan:** AI sessiya (Faza AI-X.Y)
**Tarix:** YYYY-MM-DD HH:MM
**Kontekst:** [Niyə sual yarandı]
**Variantlar:**
- A) ...
- B) ...
- C) ...
**Tövsiyə:** [AI-nın tövsiyəsi]
**Cavab:** (insan dolduracaq)
**Cavab tarixi:** (insan dolduracaq)
```

---

## Gate Keçidləri (xronoloji jurnal)

### G-V — Validasiya gate (CONTINUE — operator qərarı)
**Faza:** AI-2 → Part V keçidi
**Tarix:** 2026-06-05
**Qərar:** ▶ **CONTINUE** — operator (Scapptv) Part V build-ə keçməyi seçdi ("CONTINUE de → Part V-ə girərəm").
**Kontekst:** AI-2.5 APPROVED + AI-2.8 Posnet connector + uçtan-uca tam-loop E2E hazır; validasiya kit ([docs/validation/g-v-validation-kit.md](docs/validation/g-v-validation-kit.md)) hazır.
**⚠️ Dürüstlük qeydi:** Bu qərar **formal satıcı demo datası OLMADAN** verildi — ADR-0011 G-V-nin "validasiyadan əvvəl genişlənmə" intizamını operator avtoritetilə override etdi. Build + validate **PARALEL** gedir: kit hazırdır, satıcı demoları davam edə bilər, **pivot hələ mümkündür**. AI strateji qeydi verdi (bir dəfə, non-blocking), operator qərarı ilə davam edildi. Risk-azaltma: ilk Part V dilimi **ən aşağı-riskli, geri-qaytarıla-bilən** (2-ci marketplace mock-first adapteri) — böyük spekulyativ build (delivery/booking/fiscal) validasiya/direktiv olmadan başlamır.
**Növbəti:** Part V Faza-1 (AI-ROADMAP Part V) — 2-ci marketplace adapteri (mock-first) → multi-channel fan-out → real-adapter readiness. Real Birmarket/Trendyol swap = D-002 + Q-003 (gated, paralel).
**İmza:** Scapptv (operator), 2026-06-05.

---

### AI-2.5 — Adapter framework + 1 kanal (CROWN JEWEL — ✅ APPROVED)
**Faza:** AI-2.5 (6 dilim: 5.1-5.6 + reconciliation + OTel observability)
**Tarix:** 2026-06-04 → 2026-06-05
**Son commit:** `38150fd` — chore: merge fix/audit-remediation (ADR-0020 audit) into main
**ADR:** 0012 (hub reframe), 0018 (sync model), 0019 (fetch_listing), 0020 (audit remediation)

**Məhsul tezisi sübut olundu (ADR-0012):** "Merchant məhsulunu kanala çıxarır, online satılır,
sifariş POS-a düşür, stok hər yerdə azalır" — uçtan-uca işləyir, idempotent, **0 oversell**,
drift təpib+təmir, müşahidə olunan. Bu, hub-ın crown jewel-i.

**Gate kriteriyaları (roadmap §17.6) — yoxlama nəticələri (AI lokal, testcontainers + dev stack):**

| Kriteriya | Status | Sübut |
|---|---|---|
| Adapter kontraktı + mock contract test 100% | ✅ | `tests/contract/adapter_contract.py` + `MockMarketplaceAdapter` subclass (fetch/push/normalize) |
| E2E dilim idempotent, **0 oversell** | ✅ | `test_e2e_mvp.py`: POS→push_listing→mock→stock/price sync→webhook reserve→stok hər yerdə azalır→ack; ikinci sifariş > availability = rejected (0 oversell) |
| Reconciliation injected drift-i tapıb təmir edir | ✅ | `test_reconcile.py`: real mock injected stok/qiymət drift → `push_stock`/`push_price` təmir |
| Rate-limit + retry + DLQ test | ✅ | `ChannelGuard` (token-bucket + breaker); retry re-raise (consumer backoff); DLQ depth metrik (`pgmq.queue_length`) |
| OTel trace + sync metriklər | ✅ | `channel.push`/`channel.ingest` span; `posnet_sync_push_total` (success rate), `_dlq_depth`, `_lag_seconds` |
| Swap-ready (real adapter = eyni kontrakt) | ✅ | `ChannelAdapter` Protocol + registry; "yeni kanal = 1 adapter + contract test" |

**Dilim icmalı:**
- **5.1** Adapter contract (Protocol + Capabilities + Registry + error hierarchy)
- **5.2** Sync dispatcher (outbox → adapter; rate-limit + breaker)
- **5.3** Mock marketplace + ilk konkret adapter + contract test
- **5.4** Webhook ingress (HMAC + normalize + idempotent)
- **5.5** E2E MVP inbound order ingest (anti-oversell, 0 oversell)
- **5.6** Reconciliation (drift detect+təmir + `make reconcile`) + OTel observability

**Audit remediation (ADR-0020) merge olundu:** dərin audit `fix/audit-remediation` branch-ində (TDD)
həll olundu və `main`-ə merge edildi — **C1** (dispatcher cross-tenant explicit scope), **C2**
(swallowed push "synced" damğalanmasın — `_SKIPPED` sentinel; mənim observability outcome-metriki ilə
birləşdi), **H1** (webhook HMAC timestamp + replay window), **H4** (outbox monotonic ordering, migration
0013), **H5/M7** (pricing tiebreak + validity validasiya). Loyalty-only deps təmizləndi.

**Verify:** `make verify` (ruff + format + mypy --strict + bandit + detect-secrets) keçir; **587 test @ 98.22%**
(merge sonrası birləşmiş suite — roadmap + audit). Lokal-only (CI Q-002 billing bloku, push pauza).

**İnsandan tələb olunan (AI-2.5 gate keçidi üçün):**
1. AI-2.5-i **APPROVE** et (yuxarıdakı kriteriyalar + lokal yaşıl).
2. **G-V validasiya** açılır: MVP-ni 5-10 retail satıcıya demo ("məhsulunu Birmarket-ə 5 dəqiqəyə çıxar");
   strukturlaşmış geri-bildirim (kill/continue kriteriyaları — bax AI-ROADMAP.md §18).
3. **Partner gate** (paralel, D-002): Birmarket/Trendyol seller API sandbox + credential → mock→real adapter swap.

**Status:** ✅ **APPROVED** — kod tərəfi tam + audit merge + AI-2.8 Posnet connector (8.1-8.4) + uçtan-uca tam-loop E2E (`test_e2e_full_loop.py`). G-V validasiya açıldı (toolkit: [docs/validation/g-v-validation-kit.md](docs/validation/g-v-validation-kit.md)).
**İmza:** Scapptv (operator), 2026-06-05 — bu sessiyada APPROVE ("AI-2.5-i APPROVE et → MVP-ni 5-10 retail satıcıya demo et").

---

### AI-2.H — Audit Hardening TAM (avtonom, ADR-0016)
**Faza:** AI-2.H (5/5 task H1-H5)
**Tarix:** 2026-06-03 → 2026-06-04
**Son commit:** `85f6eb6` — chore: STATUS — Faza AI-2.H TAM (H1-H5); növbəti AI-2.5

**$100M audit (6 agent, 2026-06-03) tapıntıları (A1-A7 + B1-B6) həllinin yekun jurnalı:**

| Audit | Risk | H-task | ADR | Migration | Sübut |
|---|---|---|---|---|---|
| A1 RLS not FORCE + owner app | 🔴 | H1 | 0017 | 0009 | `test_rls_forced_on_every_policy_table`, `test_app_role_without_tenant_sees_zero_rows` |
| A2 SKU/barcode not tenant-unique | 🔴 | H2 | — | 0010 | `test_same_sku_across_products_in_tenant_conflicts`, `test_same_barcode_within_tenant_conflicts` |
| A3 First-create race → 500 | 🔴 | H2 | — | 0010 | `test_apply_movement_first_create_race_maps_to_conflict` (unit, IntegrityError → ConflictError) |
| A4 DB CHECK + no concurrency test | 🔴 | H2 + H3 | — | 0010 | `test_inventory_check_*_at_db_level`, `test_concurrent_reservations_for_last_unit_serialise` |
| A5 Coverage paint (fake-session) | 🔴 | H3 | — | — | Property tests 10 invariant + 9 Money; fake-session unitlər silindi; honest 99.88% |
| A6 Hardcoded realm parol | 🔴 | H1 | 0017 | — | `${env.POSNET_OWNER_PASSWORD}` substitusiyası |
| A7 JWT exp/iat/sub free | 🔴 | H1 | 0017 | — | `test_jwt_*_required`, audience local/test xaricində enforce |
| B1 Catalog/inventory/pricing 0 outbox | 🔴 | H4 | — | — | `test_create_product_emits_catalog_event`, `_inventory_movement_emits_event_with_post_state`, etc. |
| B2 store↔warehouse online-sellable yox | 🟡 | H5 | 0018 | 0011 | `test_build_canonical_product_aggregates_only_online_warehouses` |
| B3 online-published flag yox | 🟡 | H5 | 0018 | 0011 | `test_product_default_online_published_false`, `_unpublished_returns_none` |
| B4 channel schema yox | 🟡 | H5 | 0018 | 0011 | `test_channel_code_unique_per_tenant`, `_external_listing_id_unique_per_channel` |
| B5 Consume idempotency yox | 🔴 | H4 | — | — | `test_idempotent_runs_handler_once_per_event_id`, `_rolls_back_key_on_handler_failure` |
| B6 Canonical mapper yox | 🟡 | H5 | 0018 | — | `tests/unit/app/test_canonical_mapper.py` (13 unit) + `_uses_resolved_price_with_override` |

**Suite progressi:** 351 (H0 start) → 365 (H1) → 385 (H2) → 406 (H3) → 414 (H4) → 443 (H5). Coverage 99.88% honest (pytest-cov async-greenlet məhdudiyyəti, kod yolu tam icra olunur).

**Açıq qalan (Q-001):** operator canlı smoke (Keycloak realm parol substitusiyası + dev DATABASE_APP_URL pool). Kod tərəfdən bloklamır; AI-2.5 ərzində smoke edilə bilər.

**Növbəti:** AI-2.5 adapter framework + 1 kanal (mock-marketplace → real Birmarket/Trendyol) hardened təməl üstündə.

### G1 — Foundation done (TƏSDİQ GÖZLƏYİR)
**Faza:** AI-1 (18/18 task TAM)
**Tarix:** 2026-06-03
**Son commit:** `a8b5402` — feat(core): AI-1.18 health/shutdown + DB pool + backup
**Yoxlama nəticələri (AI lokal — testcontainers + dev stack):**
- [x] `make verify` (ruff lint+format · mypy --strict · bandit · pip-audit · detect-secrets) keçir
- [x] pytest **269 test, ümumi coverage 100%** (gate ≥80%)
- [x] RLS cross-tenant izolasiya (tenants/users/roles/permissions/user_roles/feature_flags) — select-izolasiya + insert-reject (WITH CHECK)
- [x] OIDC round-trip — Keycloak `posnet` realm + JWKS RS256 verify → Principal (real token testi)
- [x] migration up/down/up (0001–0004) testcontainers-də
- [x] pgmq publish→consume→DLQ (transactional outbox + relay FOR UPDATE SKIP LOCKED + retry/backoff)
- [x] OpenAPI + RFC 7807 problem+json (DomainError→problem · 422/429/500 leak-siz)
- [x] OTel trace (FastAPI + SQLAlchemy span → OTLP) + Prometheus `/metrics` + trace_id korelyasiya
- [x] Vault `get_secret()` (KV-v2 ref) + testcontainers
- [x] rate limit 101→429 (slowapi + Redis; health exempt)
- [x] health `/healthz`+`/readyz` (DB+Redis) + readiness drain · graceful shutdown · DB pool `pre_ping` · backup (`make backup`)
- [ ] **CI yaşıl (GitHub Actions)** — ⏳ workflows hazır; insan GitHub repo + remote qurub push etməlidir
- [ ] **`v0.1.0-alpha` tag** — AI hazırdır; G1 təsdiqindən sonra yaradılır

**İnsandan tələb olunan (G1 keçidi üçün):**
1. GitHub repo + remote qur, push et → CI workflow-larının yaşıl olduğunu təsdiqlə (`CODEOWNERS @OWNER` doldur).
2. G1-i **APPROVE** et (yuxarıdakı lokal yoxlamalar + CI yaşıl).
3. `v0.1.0-alpha` tag yaradılmasına icazə ver (AI tag-ı çəkə bilər, və ya insan).

**Operator qərarı (2026-06-03 — Scapptv): ŞƏRTİ APPROVE.**
Əsaslandırma: (a) **G0 presedenti** — GitHub Actions yaşılı G0-da da açıq qaldı, paralel insan
işi kimi; eyni məntiq G1-ə. (b) **Validasiya-sürəti prioriteti** (ADR-0011/0012) — əsl hədəf
G-V; AI-2 (POS Core) ora gedən kritik yoldur, onu infrastruktur elementi üçün bloklamaq səhvdir.
Kod tərəfi tam + lokal yaşıl (269 test, 100%) olduğu üçün G1 **kod baxımından keçir**.
**Şərt:** `v0.1.0-alpha` tag yalnız **CI real runner-də yaşıl olandan SONRA** çəkilir (release
artefaktı təsdiqlənməmiş vəziyyətdən çəkilməsin). GitHub CI = paralel insan işi; AI-2 açıqdır.
**Status:** ✅ APPROVED (şərti — kod ✓ lokal; CI yaşıl + `v0.1.0-alpha` tag paralel follow-up)
**İmza:** Scapptv (operator), 2026-06-03

### G0 — Bootstrap done (TƏSDİQ GÖZLƏYİR)
**Faza:** AI-0 (10/11 task; AI-0.7 Flutter təxirə salındı — gec OK)
**Tarix:** 2026-06-01
**Yoxlama nəticələri:**
- [x] Bootstrap smoke (up + verify) keçir — 12 servis up (postgres/redis/vault/mailpit healthy), lint+type+security ✅
- [x] Docker stack: backend + observability + dev infra (13 servis); funksional smoke (pgmq e2e, vault kv, OIDC token, OTLP→Jaeger) keçdi
- [x] Frontend tooling: pnpm workspace + admin-web Vite build ✅
- [x] CI workflow-ları (lint/test/security/build) yazıldı; lokal CI-equivalent yaşıl
- [x] ADR-lər: 0001-0003 (stack/monorepo/secrets) + 0010/0011/0012; ADR + runbook şablonları
- [x] STATUS.md "Faza AI-0 done"
- [ ] **GitHub Actions yaşıl** — ⏳ insan GitHub repo + remote qurub push etməlidir (workflows hazır); `CODEOWNERS @OWNER` doldur
- [ ] **Caddy posnet.local domenləri** — hosts faylı (opsional); daxili-TLS 8443-də onsuz da işləyir
**İnsan qeydi:** Bootstrap dev mühiti tam quruldu; AI-1 Foundation-a icazə verilir.
**Status:** ✅ APPROVED
**İmza:** Scapptv (operator), 2026-06-01

### Şablon — hər gate üçün
```markdown
### G-N — [Gate adı]
**Faza:** AI-X tamamlandı
**Tarix:** YYYY-MM-DD
**Yoxlama nəticələri:**
- [ ] make verify keçdi (coverage X%)
- [ ] (faza-spesifik yoxlama 1)
- [ ] (faza-spesifik yoxlama 2)
**İnsan qeydi:** [İnsan operator istənilən qeydi]
**Status:** ✅ APPROVED | ❌ REJECTED (return to AI with feedback)
**İmza:** [İnsan operator adı] [tarix]
```

---

## Sirr Tələbləri (AI → İnsan)

Bu siyahıda AI hansı sirr-lərin Vault-a yazılmasını xahiş etdiyini qeyd edir.

(yox)

### Şablon
```markdown
### Secret-NNN — [Sirr adı]
**Tələb edən:** AI sessiya (Faza AI-X.Y)
**Tarix:** YYYY-MM-DD
**Vault path:** secret/posnet/<path>
**Növü:** API key | Password | Certificate | Token | Other
**Mənbə:** [Sirr haradan gələcək — məsələn "Keycloak admin UI-dan client secret-i kopyala"]
**İcra status:** ⏳ Gözləyir | ✅ Vault-a yazıldı | ❌ Ləğv olundu
**İnsan tərəfindən təsdiq:** [İnsan operator adı] [tarix]
```
