# ADR-0018 — Sync model enabler: online-sellable stock, online-published flag, channel schema, canonical mapper

**Status:** ACCEPTED
**Tarix:** 2026-06-04
**Qəbul edən:** AI sessiya (Faza AI-2.H5) — ADR-0016 audit B2/B3/B4/B6 icrası
**Əlaqə:** ADR-0012 (inteqrasiya hub) — model qurulur; ADR-0016 (audit hardening) — bu task; ADR-0013/0017 (RLS/dual-pool — yeni cədvəllər policy-yə əlavə)

## Kontekst

$100M audit (ADR-0016) tapdı ki, catalog/inventory/pricing source-of-truth-dur
amma "**sync üçün hazır deyil**":
- **B2** — `Warehouse` cədvəli online-sellable konsepsiyası saxlamır: anbara
  daxil olan stok avtomatik onlayn satışa açıq sayılır. Reallıqda anbarın bir
  hissəsi şou-rum / B2B / wholesale ola bilər; onlayn yalnız bir alt-çoxluq satılır.
- **B3** — `Product`-da **online-published** flag yoxdur: kataloqda mövcud olan
  hər şey adapter-ə "push" üçün hazır görünür. Reallıqda satıcı "**bu məhsul
  mənim onlayn vitrinimdə yoxdur**" demək istəyir (e.g., yalnız mağazada satılan
  fond məhsulu).
- **B4** — **channel schema** yoxdur: hansı kanal-ların qoşulu olduğunu və hər
  variant-ın hansı kanalda hansı external listing-id ilə inteqrasiya olunduğunu
  saxlamağa yer yoxdur. Trendyol-un `productCode`-u, Birmarket-in `sellerCode`-u,
  Wolt-un `external_item_id`-i — hamısı yox.
- **B6** — **canonical mapper** yoxdur: ORM (Product, Variant, Inventory[],
  ResolvedPrice) → `libs.canonical_model.CanonicalProduct` çevirməsi
  inteqrasiya nüvəsinin əsasıdır (ADR-0012 §"crown jewel"), amma boş yerdir.

Hardening fazasında (`AI-2.H5`) bu dörd boşluğu **modeldə + helper-də** doldururuq.
Real adapter framework AI-2.5-də gələcək; bu task təməli sıradır.

## Qərar

### 1. Online-sellable stock — anbar-səviyyə flag + aggregation

Yeni sütun: `warehouses.is_online_sellable: bool DEFAULT true`. Bir variant-ın
**online available** dəyəri:

```
online_available(variant)
  = SUM(qty - reserved_qty)
    over inventory rows
    where warehouse.is_online_sellable = true
```

Şou-rum / B2B / wholesale anbarları üçün operator flag-ı `false`-a çevirir;
həmin anbarların stoku onlayn agreqasiyaya daxil olmur (POS satışı / shop sale
hələ də normal işləyir). Flag-ın **default** dəyəri `true` — mövcud anbarların
davranışı dəyişməz.

**Niyə per-warehouse, per-variant deyil?** Per-variant həm məlumat
duplicate-i həm də UI yükü yaradar. Anbar-səviyyə flag adətən şirkətin bu
məkanı necə istifadə etdiyi haqqında düşünmə şəklini (bir mağaza = bütünlüklə
"online OK", bir başqası = "yalnız B2B") izləyir.

### 2. Online-published flag — məhsul-səviyyə qapı

Yeni sütun: `products.online_published: bool DEFAULT false`. **Default `false`**
çünki müştəri açıq şəkildə "bu məhsulu onlayn vitrinə qoy" demək istəyir;
inadvertent push qarşısını alır. `build_canonical_product` flag `false`
olduqda `None` qaytarır → sync engine kanal-a push etmir.

**Niyə məhsul-səviyyə, variant-səviyyə deyil?** Çoxlu variant-lı məhsulu
toplu publish/unpublish etmək üçün məhsul-səviyyə daha əməli. Variant-spesifik
"bu ölçü onlayn deyil" hələ scope-da deyil; gələcəkdə variant flag əlavə
etmək geriyə uyğundur (default `true` → mövcud `products.online_published =
true` davranışı qoruyur).

### 3. Channel schema — `channels` + `channel_listings`

Yeni iki cədvəl:

```sql
-- Channel = qoşulu marketplace / delivery / booking platforması
channels (
  id uuid pk,
  tenant_id uuid fk tenants,
  code varchar(50),       -- "trendyol", "birmarket", "wolt", "bolt"
  name varchar(200),      -- insan-üçün ad
  status varchar(20) default 'active',  -- active | paused | disabled
  config jsonb default '{}',  -- per-channel credentials/region/etc (yer tutucu)
  created_at, updated_at timestamptz,
  UNIQUE (tenant_id, code)
)

-- Channel listing = variant ↔ external listing mapping per channel
channel_listings (
  id uuid pk,
  tenant_id uuid fk tenants,
  channel_id uuid fk channels,
  variant_id uuid fk variants,
  external_listing_id varchar(200),  -- channel-in id-si (NULL = hələ push olmayıb)
  external_category varchar(500),    -- channel-in kateqoriya path-ı (e.g. "Food > Drinks")
  external_attributes jsonb default '{}',  -- channel-spesifik atribut payload
  status varchar(20) default 'pending',    -- pending | active | rejected | paused
  last_synced_at timestamptz,
  created_at, updated_at timestamptz,
  UNIQUE (channel_id, variant_id),         -- bir variant → bir listing per channel
  UNIQUE (channel_id, external_listing_id) WHERE external_listing_id IS NOT NULL
)
```

Hər iki cədvəl tenant_id daşıyır, RLS policy daxildir (tenant_isolation),
`posnet_app` grant. **Cascade:** tenant silinərsə → channels və listings
silinir; channel silinərsə → listings silinir; variant silinərsə → listing
silinir (məhsul yox isə marketplace listing-i mənasızdır).

**`config` JSONB:** kanal-spesifik konfiqurasiya üçün yer tutucu (e.g.
"region": "AZ", "warehouse_id": "..."). Konkret strukturlar AI-2.5
adapter-lərində gələcək. **HEÇ vaxt secret-lər orada saxlanmır** — credentials
Vault-da (LOCKED #8).

### 4. Canonical mapper — pure helpers + service orchestrator

`services/core/app/sync/canonical.py`:

```python
# Pure helper-lər (DB-siz, asanlıqla test olunan)
def to_canonical_product(*, product, variant, image_urls, stock_qty, effective_price_minor, currency, status) -> CanonicalProduct
def to_canonical_inventory(*, sku, stock_qty, reserved_qty) -> CanonicalInventory
def to_canonical_price(*, sku, price_minor, currency) -> CanonicalPrice
def aggregate_online_stock(inventory_rows, online_sellable_warehouse_ids) -> tuple[int, int]  # (qty, reserved)

# Yüksək-səviyyəli orchestrator (DB-li)
async def build_canonical_product(session, *, variant_id, at) -> CanonicalProduct | None
```

`build_canonical_product` axını:
1. Variant + Product-u RLS-scoped session-dan götür
2. `Product.online_published == False` → return `None` (kanal-a push olunmur)
3. Bütün inventory sətirlərini yığ (online_sellable_warehouse-larla join)
4. `aggregate_online_stock` → `(qty, reserved)`; available = qty - reserved
5. `resolve_price` (mövcud, AI-2.3-də) → effective_price_minor
6. `ProductImage`-ları sıra ilə (sort_order)
7. `to_canonical_product` ilə yığ

Bu funksiya **per-channel deyil** — kanal-agnostik canonical model qaytarır.
Adapter (AI-2.5) onu kanal payload-una proyeksiya edir, `channel_listings`-dən
`external_listing_id` / `external_category` götürür.

**Niyə pure helper-lər ayrıca?** Adapter test-ləri canonical → payload
çevriş üzərində fokuslanmalıdır; helper-ləri DB-siz çağırmaqla test daha sürətli
və daha dəqiq olur (orchestrator + pure split).

### 5. Aggregation ADR — toplu stok hesabı

Default toplu stok formulu yuxarıda göstərilib (SUM across is_online_sellable).
Gələcək nüanslar üçün **default-u açıq saxlayırıq, override mexanizmasını**
artıq qurmuruq:
- per-channel buffer ("Trendyol-a stokun 80%-i") — gələcəkdə `channels.config`-ə
  və ya yeni cədvələ
- safety-stock (uçot dəqiqsizliyi üçün "həmişə 1 saxla") — gələcəkdə
  `warehouses.safety_qty` sütunu
- multi-warehouse priority (e.g., "yaxın anbardan göndər") — order
  fulfilment scope-u, AI-2.5+

Bu MVP-də aggregation **sadə + tam toplu** modelidir. AI-2.5 ərzində ilk adapter
real istifadə-case-i göstərdikdə dəyişdiririk (ADR-amendment ilə).

## Nəticələr

- (+) Adapter framework (AI-2.5) qurulmuş çatın üstündə işləyir: nə publish
  ediləcək, hansı kanal-a, hansı external id ilə, hansı stok aqreqasiya ilə.
- (+) Default-lar geriyə uyğundur: mövcud anbarlar `is_online_sellable=true`,
  mövcud məhsullar `online_published=false` (təhlükəsiz default — inadvertent
  push yoxdur).
- (+) Canonical mapper həm pure helper-lərdə (test-friendly) həm orchestrator-da
  (real istifadə) — adapter dünyasının iki rejimi.
- (−) Channel schema-nın `config` JSONB-i hələ formal validasiyasızdır.
  Adapter-lər lazımsa Pydantic schema əlavə edəcək. Hələlik tenant operator-un
  məsuliyyətindədir (forms tərəfdən validasiya AI-2.5 admin-web-də).
- (−) Aggregation override mexanizmi yoxdur; ilk real adapter göstərdikdə əlavə edirik.

**Risk azaldılması:** schema indi qurulduğu üçün AI-2.5 ərzində channel
listing-lərinin tarixi məlumatı miqrasiya etməyə ehtiyac yox — boş başlanır.
