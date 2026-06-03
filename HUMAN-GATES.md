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
| G2 — POS Core done (**MVP**) | AI-2 | ⏳ Planlandı | — | — |
| **G-V — Validasiya** (ADR-0011) | AI-2→3 | ⏳ Planlandı | — | — |
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

### Q-001 — AI-2.H1 canlı yoxlama (operator smoke)
**Soruşan:** AI sessiya (Faza AI-2.H1)
**Tarix:** 2026-06-04
**Kontekst:** AI-2.H1 (Security posture, ADR-0017) kod tərəfi tam — 14 yeni avtomatik test (RLS FORCE, posnet_app non-owner LOGIN, dual-pool izolasiya, posnet_resolve_tenant) lokal-da yaşıl. İki dilim **canlı təsdiq** istəyir:
- (a) **Keycloak realm parol substitusiyası** (`${env.POSNET_OWNER_PASSWORD}` → realm-posnet.json import-da): avtomatik realm testi strukturaldır, real OIDC round-trip canlı təsdiq istəyir.
- (b) **Dev app `DATABASE_APP_URL`** (posnet_app pool) ilə `docker compose up` + smoke. Boş `DATABASE_APP_URL` system pool-a düşür (işləyir, amma kilidli deyil) — prod-da məcburi.

**Variantlar:**
- A) Operator hər ikisini lokal-da smoke et, nəticəni Q-001-ə yaz → AI tamamlanmış kimi qeyd edir
- B) Yalnız (b)-ni indi yoxla, (a) G7-də prod Keycloak ilə birgə təsdiq olunur
- C) Hər ikisini AI-2.5 ərzində bir paket halında yoxla (adapter framework də smoke ediləcək)

**Tövsiyə:** **B** — (b) DATABASE_APP_URL təcili (hər lokal dev sessiyasında istifadə olunur, real layer-2 müdafiə qatı), (a) Keycloak substitusiyası prod-relevant amma dev mühitdə test client izolyasiya verir.
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
