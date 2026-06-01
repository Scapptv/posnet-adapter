# ADR-0012 — Məhsul Reframe: POS-anchored İnteqrasiya Hub

**Status:** ACCEPTED
**Tarix:** 2026-06-01
**Qəbul edən:** İnsan operator (strateji qərar) + AI sessiya (araşdırma + sənədləşdirmə)
**Əlaqə:** ADR-0011-i **İNCƏLƏŞDİRİR** (tam ləğv etmir), ADR-0001 (Stack)

## Kontekst

Operator dəqiqləşdirdi: Posnet sadəcə POS deyil — **POS-anchored omnichannel inteqrasiya
hub-ıdır** (TSoft / Entegra / ChannelEngine / Linnworks modeli). POS tək həqiqət mənbəyidir;
hub məhsul/stok/qiyməti marketplace, delivery və booking portallarına çıxarır, sifarişləri
vahid panelə geri gətirir. Audit və ADR-0011 adapterləri "scope şişməsi" kimi az qiymətləndirmişdi
— bu çərçivələmə səhv idi: **adapterlər məhsulun nüvəsidir.**

### Araşdırma (dünya referansları, 2026-06-01)
- **Marketplace integrator:** ChannelEngine (1300+ kanal), Linnworks, ChannelAdvisor/Rithum,
  TSoft, Entegra, Sentos — canonical model + kateqoriya/atribut mapping + stok/qiymət push + sifariş ingest.
- **Delivery:** Wolt / Bolt Food / Yemeksepeti — menyu sync + item availability + sifariş injection + status; OAuth2/JWT.
- **Booking:** SiteMinder (otel channel manager, 350+ bağlantı) — availability/rate push + rezervasiya pull + channel mapping.
- **Vahid nümunə:** canonical model + event-driven + idempotent + orchestration + observability (MACH / iPaaS).
- **AZ bazar:** Birmarket (ex-Umico, İyul 2025 rebrand; Bir ekosistemi 5M+ user; Trendyol partnyor) = #1 marketplace.
- **TR bazar:** $93.5B (2025), amma 14+ pure-play integrator (Entegra/Sentos/Sopyo/Dopigo…) ilə qızğın rəqabət.

## Qərar

### Məhsul positioning
POS-anchored omnichannel inteqrasiya hub-ı (AZ/TR SMB). **Fərqləndirici (wedge):** pure-play
integratorların (Entegra/Sentos/TSoft) POS-u yox — mövcud e-mağaza/ERP-dən başlayırlar; lokal POS
vendorların yaxşı hub-ı yox. Posnet ikisini birləşdirir + fiskal uyğunluq.

### Beachhead (daraldıldı — operator 2 fork, 2026-06-01)
- **Bazar:** **Azərbaycan əvvəl** (konsolidasiya kanallar: Birmarket + Trendyol; integrator rəqabəti az = asan sübut meydanı).
- **Merchant × ilk kanal:** **Pərakəndə (market/butik) × Marketplace** (Birmarket / Trendyol).
- **Canonical model:** SKU/barkod-mərkəzli.

### Arxitektura — crown jewel = adapter framework
- **Canonical model** (məhsul/stok/qiymət/sifariş) — `libs/canonical_model`
- **Adapter kontraktı + SDK:** "yeni kanal = stabil kontrakta qarşı 1 adapter + şablon contract test"
  (ChannelEngine 1300, SiteMinder 350 kanalı belə miqyaslayır)
- **Sync engine:** outbound (stok/qiymət push, near-real-time, idempotent) + inbound (sifariş ingest → canonical → POS)
- **Channel mapping:** kanal kateqoriya/atribut/kargo ↔ canonical
- **Etibarlılıq 1-ci gündən:** idempotency, reconciliation (anti-oversell), rate-limit per kanal, retry/backoff, DLQ, observability
- `libs/eventbus` (outbox + DLQ) = hub-ın onurğası → AI-1-də prioritet

### Re-sequence (ADR-0011 dondurmasını incələşdirir)
- ✅ **Qalır:** fokus (bütün okeanı qaynatma), POS lövbər əvvəl, G-V validasiya gate.
- 🔄 **Dəyişir:** "bütün adapterləri dondur" SƏHV idi. Adapter framework + **1 kanal CORE-dur, MVP-yə daxildir.**
- **Yeni MVP tərifi:** POS-da məhsul → Birmarket-ə listing → stok/qiymət sync → sifariş POS-a düşür → **stok hər yerdə azalır.**
- **Yeni task AI-2.5:** adapter framework + canonical adapter + sync engine + 1 kanal (əvvəl mock, sonra real).

### Mock-first (insan asılılığını bloklamır)
Real Birmarket/Trendyol seller API access = partner müraciəti = **insan gate** (HUMAN-GATES D-002).
AI **mock Birmarket adapteri** ilə framework-i tam qurur (real API kontraktını təqlid edir); credential
gələndə swap edilir. Texniki qeyd: Trendyol-un public Marketplace API-si sənədlidir → ilk REAL
adapter texniki olaraq Trendyol daha asan ola bilər; Birmarket lokal brend uyğunluğu. Hər ikisi AZ hədəfdir.

### Hələ təxirdə (G-V və ya sonra)
2-ci kanal, **delivery domain** (Wolt/Bolt — kafe beachhead-i üçün), **booking domain** (SiteMinder modeli),
fiskal, multi-country accounting, cloud/scale, **Türkiyə**.

## Nəticələr

### Müsbət
- Məhsulun əsl dəyəri (merchant-ın online çıxışı) erkən qurulur və validasiya olunur
- Arxitektura instinkti təsdiqləndi — roadmap-ın canonical/eventbus/adapter/idempotency dizaynı dünya nümunəsinə uyğun
- AZ konsolidasiya kanallar = az adapter = asan başlanğıc

### Risk / azaltma
- **Birmarket API mövcudluğu qeyri-müəyyən** → mock-first + Trendyol fallback (sənədli public API)
- **İnteqrasiya düzgünlüyü kritik səthdir** (oversell / itən sifariş = merchant churn) → idempotency + reconciliation core
- **Partner access insan gate-dir** → paralel; mock MVP-ni bloklamır

## Əlaqəli
- ADR-0011 (incələşdirilir), ADR-0001 (Stack)
- Referanslar: tsoft.com.tr, channelengine.com, linnworks.com, siteminder.com, developer.wolt.com, bir.az
- STATUS.md (strategiya banner), HUMAN-GATES.md (D-002 + partner gate), AI-ROADMAP.md (scope banner)
