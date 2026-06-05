# ADR-0021 — POS-tərəfi inteqrasiya: Posnet connector (bu layihə POS yazmır)

**Status:** ACCEPTED
**Tarix:** 2026-06-05
**Qəbul edən:** İnsan operator (Scapptv) + AI sessiya
**Əlaqəli:** ADR-0012 (hub reframe), ADR-0020 §41 (geri götürülən bayraq), AI-ROADMAP.md §17.7

## Kontekst

ADR-0012 hub-ı "POS-anchored" adlandırır və "mövcud Posnet ERP məhsul/stok/qiymətin sahibidir"
deyir. Lakin sənədlərdə bu layihənin **öz POS app-ını** yazacağı çərçivəsi qalmışdı:
`apps/pos-flutter`, AI-2.8 "Flutter kassir minimal", arxitektura cədvəllərində "Kassir = Flutter
(offline-first)". İkinci audit (ADR-0020 §41) bunu "strateji boşluq — mobil POS yoxdur" kimi
bayraqladı.

Operator düzəlişi: **POS = mövcud Posnet** — ayrı, real layihə (POS nüvəsi). Bu layihə (`adapter`)
yalnız **inteqrasiya hub-ıdır**; Posnet-ə qoşulur, **POS yazmır**.

## Qərar

1. **Bu layihə POS UI / kassir app YAZMIR.** `apps/pos-flutter` silinir; AI-2.8 "Flutter kassir" →
   **AI-2.8 Posnet connector**. Arxitektura/stack cədvəllərində "Kassir = Flutter" → "POS = Posnet".
2. **POS-tərəfi bağlantı = Posnet connector** (source-POS adapter) — kanal adapterləri ilə **eyni
   nümunə** (canonical model + `ChannelAdapter`-ə bənzər Protocol + contract test + mock-first),
   sadəcə mənbə kanal yox POS-dur:
   - **Pull (Posnet → hub):** məhsul/variant/stok/qiymət → canonical → hub-ın online catalog/inventory
     (online-a çıxan curated alt-çoxluq).
   - **Push (hub → Posnet):** kanal sifarişi/çek/stok-azalma → canonical → Posnet-ə yaz (inbound
     axının davamı; webhook→reserve→`acknowledge` artıq var, son addım Posnet-ə yazmaq).
3. **Mock-first → real:** real Posnet API/credential gələnə qədər hub-ın catalog/inventory-si
   admin-web/API ilə doldurulur (G-V demo üçün yetərli). Connector Posnet interfeysi (API/DB/format +
   auth) müəyyən olunanda yazılır.
4. **admin-web bir POS DEYİL** — hub-ın online merchant panelidir (curated subset idarəsi + publish +
   kanal sync görünüşü).

## Nəticələr

### Müsbət
- Scope dəqiqləşdi: hub yalnız inteqrasiya qatıdır; POS funksiyaları (kassir, in-store satış, çek
  cihazı) Posnet-də qalır → işin ikiqatlanması yoxdur.
- Posnet connector kanal-adapter təcrübəsindən faydalanır (canonical + contract test + mock-first → real).
- ADR-0020 §41 "POS app boşluğu" bayrağı **geri götürüldü** (səhv fərziyyə idi).

### Mənfi / qalıq risk
- Posnet connector hələ yazılmayıb → production-da real Posnet datası axmır (admin-web/API stand-in).
  Posnet interfeysi (API/DB/format + auth) operator tərəfindən müəyyən olunmalıdır → sonra AI-2.8.

## Əlaqəli
- ADR-0012 (hub reframe — POS = tək həqiqət mənbəyi), ADR-0020 §41 (retraction)
- AI-ROADMAP.md §17.7 (Posnet connector modeli), §16 (AI-2.8)
