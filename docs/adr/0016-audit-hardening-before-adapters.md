# ADR-0016 — $100M Audit + adapterlərdən ƏVVƏL hardening fazası (AI-2.H)

**Status:** ACCEPTED
**Tarix:** 2026-06-03
**Qəbul edən:** İnsan operator (strateji qərar) + AI sessiya (6-agent audit + sənədləşdirmə)
**Əlaqə:** ADR-0012 (inteqrasiya hub) — **icra ardıcıllığını dəqiqləşdirir**; ADR-0013 (eventbus), ADR-0015 (RLS)

## Kontekst

AI-1 Foundation + AI-2.1–2.4 (catalog · inventory · pricing · shift) qurulandan sonra operator
**review-suz sürətli qurmanın gələcəkdə baha başa gələcəyindən** narahatlıq bildirdi. 6 müstəqil
auditor agenti ilə **$100M səviyyəli audit** aparıldı (memarlıq · təhlükəsizlik · korrektlik/
konkurentlik · schema · test ciddiyyəti · etibarlılıq/sync-readiness).

### Audit nəticəsi (qiymətlər)
memarlıq **3/10** · təhlükəsizlik **4.5/10** · korrektlik **6/10** · schema **6.5/10** · test **3/10** ·
sync-readiness **3/10**. Bir cümlə: **möhkəm təməl/plumbing, amma əsl məhsul (sync/inteqrasiya)
qurulmayıb + canlı təhlükəsizlik/korrektlik deşikləri var + "100% coverage" qismən saxtadır.**

### Kritik tapıntılar (konsensus)
- **A1 🔴** RLS `FORCE` deyil + app `posnet` (owner/superuser) ilə bağlanır → izolyasiya hər
  request-də opt-in; bir unudulmuş `SET LOCAL ROLE` = bütün tenant-lar sızır. İkinci qat yox.
- **A2 🔴** SKU/barkod tenant daxilində unikal deyil + `find_variant_*` `limit(1)` `ORDER BY`-sız →
  POS skanı təsadüfi variant → səhv qiymət/səhv stok. Bütün adapter contract SKU-keyed.
- **A3/A4 🔴** inventory first-create race → `IntegrityError` tutulmur → HTTP 500; anti-oversell
  üçün DB `CHECK` backstop yox; **sıfır konkurentlik testi** (`.with_for_update()` silinsə 100% yaşıl).
- **A6 🔴** PUBLIC repo-da hardcoded `tenant_admin` parolu (`realm-posnet.json`).
- **B1 🔴** catalog/inventory/pricing/shift **sıfır outbox event** emit edir → sync engine-in
  change-feed-i yoxdur (ADR-0012 "1-ci gündən" tələbi). Eventbus əla, amma boş.
- **A5 🔴** "100%" qismən manufaktura (fake-session coverage-paint, birbaşa handler çağırışı,
  real middleware/auth bypass); suite Linux/CI-də heç vaxt işləməyib.

### Güclü tərəflər (saxlanılır)
`libs/eventbus` (atomik outbox relay + retry/DLQ) əla; RLS table/policy/grant **əhatəsi tam**
(23/23); FK-bypass awareness (RLS-scoped re-lookup); injection yox; Money integer-minor; təmiz layering.

## Qərar

### 1. Məhsul məntiqi (təsdiq + dəqiqləşdirmə — ADR-0012-yə uyğun)
Bu layihə = **Posnetin inteqrasiya nüvəsi** — necə ki **CLOPOS** POS-u **Wolt/Bolt** (delivery)
inteqratorudur, **TSoft** **Trendyol** (marketplace) inteqratorudur — Posnet eyni nüvə ilə
delivery + marketplace + booking kanallarına bağlanır. Bu servis = satıcının **online/inteqrasiya
qatı**: curated online kataloq (Posnet məhsullarının seçilmiş alt-çoxluğu) + online qiymət/kampaniya
+ online sifariş emalı (operator vardiyası) + online çek.
- **Outbound:** məhsul/stok/qiymət/endirim → (canonical) → kanallar (Trendyol/Birmarket/Wolt/Bolt) push
- **Inbound:** sifariş/ödəniş/kargo → (canonical) → Posnet yaz
- **Crown jewel:** canonical model + adapter SDK + sync engine (idempotent + reconciliation).

### 2. Sıra qərarı: **hardening ADAPTERLƏRDƏN ƏVVƏL**
Audit kritikləri (xüsusən SKU identity, event emission, RLS-force, DB invariant-lar) **indi 1
migration, kanallar yarandıqdan sonra data-migration + artıq-push olunmuş listing-lərin reconcile-i**.
Ona görə AI-2.5 (adapter framework) **gözləyir**; əvvəl **Faza AI-2.H — Audit Hardening** icra olunur,
düzgün məntiqi ardıcıllıqla: **təhlükəsizlik → data identity/invariant → korrektlik/proof → sync
enabler → sonra adapterlər.**

### 3. Audit icra ardıcıllığı (Faza AI-2.H — detal STATUS.md-də)
- **AI-2.H1** Security posture: RLS `FORCE` + app non-owner login rolu + regression test; realm
  parolu sil/rotate + secret baseline; JWT audience enforce + `require [exp,iat,sub]` (A1,A6,A7)
- **AI-2.H2** Data identity & invariant: `UNIQUE(tenant_id, sku)` + `UNIQUE(tenant_id, barcode)
  WHERE NOT NULL` + deterministik lookup; inventory `IntegrityError→409`; DB `CHECK(qty>=0,
  reserved>=0, reserved<=qty)`; journal cədvəllərinə INSERT/SELECT-only grant (A2,A3,A4,schema)
- **AI-2.H3** Anti-oversell proof: real paralel-tx oversell testi; coverage-theater testləri real et;
  `_effect`/Money üçün hypothesis property-test; `make verify`-ə test əlavə (A4,A5)
- **AI-2.H4** Sync change-feed: catalog/inventory/pricing domain outbox event emit + consume
  idempotency (idempotency_keys wiring) (B1,B5)
- **AI-2.H5** Sync model enabler: store↔warehouse / online-sellable-stock modeli + online-published
  flag + channel-mapping schema (channels, channel_listings: sku↔external_listing_id) dizaynı;
  canonical mapper (Product/Inventory/Price → CanonicalProduct) (B2,B3,B4,B6)
- **sonra → AI-2.5** Adapter framework + 1 kanal (mock-marketplace → real) hardened təməl üstündə.

## Nəticələr
- (+) Adapterlər təhlükəsiz, deterministik, sync-hazır təməl üstündə qurulur; kritiklər ucuz mərhələdə həll olunur.
- (+) Anti-oversell vədi DB-də backstop + real test ilə sübuta yetir.
- (−) İlk real adapterə qədər yol uzanır (~5 hardening task).
- **Risk azaldılması:** review-suz yığılan debt (operator narahatlığı) sənədli icra ardıcıllığına çevrilir.
- **CI/billing + repo-private** məsələsi paralel insan işi olaraq qalır (github-scapptv).
