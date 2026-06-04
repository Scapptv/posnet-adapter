# ADR-0019 — Adapter `fetch_listing`: kanal-tərəf oxu səthi (reconciliation üçün)

**Status:** ACCEPTED
**Tarix:** 2026-06-04
**Qəbul edən:** AI sessiya (Faza AI-2.5.6.1)
**Əlaqəli:** ADR-0012 (§17.2 adapter kontraktı, §17.4 reconciliation), ADR-0018 (sync model), AI-ROADMAP.md §17.4

## Kontekst

Roadmap §17.4 reconciliation-ı tələb edir: "kanal stoku vs POS stoku drift yoxla → təmir + alert". AI-2.5 gate isə açıq deyir: "reconciliation injected drift-i tapıb təmir edir". Bunun üçün reconciliation **kanal-tərəf cari stoku oxumalıdır** ki, onu POS canonical stoku (`build_canonical_product().stock_qty`) ilə müqayisə etsin.

Mövcud `ChannelAdapter` Protocol-u **yalnız push + ingest**-dir (`push_listing/stock/price`, `pull_orders`, `acknowledge_order`, `normalize_webhook`, `map_category`). Heç bir metod kanaldan bir listing-in cari vəziyyətini (stok/qiymət) **oxumur**. Adapter kontraktı məhsulun CORE-udur (ADR-0012) — ona metod əlavə etmək texniki qərardır.

## Variantlar

1. **Protocol-a `fetch_listing(sku) -> ChannelListingSnapshot | None` əlavə et** — adapter kanaldan real cari stoku oxuyur. Reconciliation həqiqi drift-i (kanal-tərəf dəyişiklik, itmiş push, manual redaktə) tutur. Capability flag (`supports_fetch_listing`) ilə qorunur; push-only kanallar `NotImplementedError` qaldıra bilər (mövcud `normalize_webhook` pattern-i).
2. **`channel_listings.last_synced_at` + son push dəyərinə güvən** (kanal oxumadan) — yalnız "biz heç vaxt push etməmişik" driftini tutur, kanal-tərəf divergensiyanı YOX. Roadmap "kanal stoku vs POS stoku" tələbini ödəmir; injected-drift testini keçə bilməz.
3. **Ayrıca "reconciliation adapter" interfeysi** — `ChannelAdapter`-i təmiz saxlamaq üçün ikinci protocol. Artıq parçalanma; bir kanal = bir adapter prinsipini pozur.

## Qərar

**Variant 1.** `ChannelAdapter` Protocol-una `async def fetch_listing(self, *, sku) -> ChannelListingSnapshot | None` əlavə edildi + `AdapterCapabilities.supports_fetch_listing` flag (default `False`). `ChannelListingSnapshot` frozen dataclass (sku, stock, price_minor, currency, external_listing_id, status) kanal-tərəf görünüşü daşıyır. 404 → `None` ("burada listed deyil", xəta yox); digər non-2xx → mövcud `AdapterError` klassifikasiyası.

Səbəb: roadmap birmənalı **kanal stokunun oxunmasını** tələb edir (Variant 2 bunu ödəmir). Capability-gated tək metod `normalize_webhook`-un artıq qurduğu pattern-i izləyir (push-only kanal `NotImplementedError` qaldırır) — ikinci protocol-a (Variant 3) ehtiyac yoxdur.

## Nəticələr

### Müsbət
- Reconciliation (2.5.6.2) həqiqi kanal↔POS drift-i tuta + təmir edə bilər (push_stock ilə).
- Tək kontrakt: "yeni kanal = 1 adapter + contract test" prinsipi qorunur; contract suite `fetch_listing` happy + 404→None yoxlayır (capability-gated `pytest.skip`).
- Read-only: heç bir mövcud davranışı dəyişmir; `_request` → `_send` + `_raise_for_status` refactor-u eyni klassifikasiyanı saxlayır (mövcud error testləri sübut edir).

### Mənfi / qalıq risk
- Protocol genişləndi → hər adapter (real Birmarket/Trendyol daxil) `fetch_listing` implement etməlidir VƏ ya `NotImplementedError` + `supports_fetch_listing=False`. (Azaltma: capability flag + skip; push-only kanallar üçün məcburi deyil.)
- `fetch_listing` rate-limit/breaker altında deyil (hələ) — reconciliation onu öz throttle-i ilə çağırmalıdır (2.5.6.2-də həll olunur).

## Əlaqəli
- AI-ROADMAP.md §17.4 (reconciliation), §17.2 (adapter kontraktı)
- ADR-0012 (hub reframe, adapter = CORE), ADR-0018 (sync model enabler)
