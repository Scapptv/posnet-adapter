# Real Posnet connector spesifikasiyası (UltimatePOS Connector API)

**Mənbə:** real Posnet layihəsi — `C:\Users\PC\OneDrive\Desktop\Posnet A` (Laravel modular POS, **UltimatePOS-törəməsi**; "API keys" sessiyası). Bu sənəd `PosnetConnector`-un **real** implementasiyası üçün interfeysi (Q-003 / ADR-0022) müəyyən edir. **Sirr DƏYƏRLƏRİ burada YOXDUR** (CLAUDE.md) — yalnız sxema + sahə şəkilləri + Vault planı.

> **TL;DR:** Real Posnet = UltimatePOS **Connector** modulu API. Auth = **Laravel Passport OAuth2 (password grant)** → `Authorization: Bearer`. Pull = `GET /connector/api/variation` (və ya `/product`). Push = `POST /connector/api/sell`. İnterfeys artıq **MƏLUMDUR** → Q-003 gate yalnız **credential → Vault** + connector build-ə daraldı.

---

## 1. Auth — OAuth2 password grant (Laravel Passport)

Bütün API route-ları `auth:api` (Passport) middleware altındadır (`Modules/Connector/Routes/api.php`). Token alma:

```
POST {base_url}/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=password
client_id={oauth_client_id}
client_secret={oauth_client_secret}
username={api_user_email}
password={api_user_password}
scope=*
```
Cavab: `{ "token_type":"Bearer", "expires_in":31536000, "access_token":"...", "refresh_token":"..." }` (token ~1 il).
Sonra hər sorğu: `Authorization: Bearer {access_token}`.

**Connector implikasiyası:** hazırkı `PosnetConfig.auth_headers` (statik header) **kifayət deyil** — real connector **OAuth token manager** tələb edir: ilk çağırışda `/oauth/token` ilə token al, cache et, 401-də/expiry-də refresh et (refresh_token və ya yenidən password grant). Sonra `auth_headers = {"Authorization": "Bearer <token>"}`. OAuth client (id+secret) superadmin UI-da yaradılır (`/connector/clients`).

---

## 2. Pull catalog — `GET /connector/api/variation`

Ən təmiz katalog mənbəyi flat **variation** siyahısıdır (`ProductController@listVariations`, `Transformers/VariationResource.php`). Alternativ: `GET /connector/api/product` (nested) + `GET /connector/api/product-stock-report` (stok).

`GET /connector/api/variation?per_page=-1&location_id={loc}` → `{ "data": [ ...variations ], ... }`. Hər variation (əsas sahələr):

| Posnet (variation) sahəsi | Tip | Canonical mapping |
|---|---|---|
| `sub_sku` | str | `CanonicalProduct.sku` (scan kodu) |
| `product_name` | str | `name` |
| `sub_sku` (barkod ayrıca yoxdur) | str | `barcode` = `sub_sku` (və ya null; UltimatePOS sku=scan) |
| `category` / `sub_category` | str | `category_path = [category, sub_category]` (boşları at) |
| `sell_price_inc_tax` (və ya `default_sell_price`) | dec-string "130.0000" | `price_minor = round(float × 100)` |
| (business currency, §5 business-details) | str | `currency` |
| `variation_location_details[].qty_available` | dec-string | `stock_qty = round(float)` — config location üçün (və ya cəm) |
| `variation_id`, `product_id` | int | **push üçün** SKU→(product_id, variation_id) map-də saxla |

**Qeydlər:** qiymət tax-daxil/xaric seçimi config olmalı (`sell_price_inc_tax` vs `default_sell_price`). Stok per-location — connector bir **online location_id** seçir (config). `enable_stock=0` məhsullar (xidmət) stok-suz.

---

## 3. Push order — `POST /connector/api/sell`

`SellController@store`. Body `sells[]` massivi:

```json
{ "sells": [ {
  "location_id": 1,                // CONFIG (online location)
  "contact_id": 1,                 // CONFIG (walk-in) ya da customer map
  "transaction_date": "2026-06-05 15:48:29",
  "status": "final",
  "source": "api",
  "invoice_no": "{channel_order_id}",   // idempotency/izləmə üçün
  "discount_amount": 0, "discount_type": "fixed",
  "products": [ {
    "product_id": 17,              // SKU→id map (§2)
    "variation_id": 58,            // SKU→variation_id map (§2)
    "quantity": 1,
    "unit_price": 437.50           // unit_price_minor / 100
  } ],
  "payments": [ {
    "amount": 453.13,              // grand_total_minor / 100
    "method": "other"              // marketplace pre-paid → 1 payment line
  } ]
} ] }
```

**CanonicalOrder → sell mapping:**

| Canonical | Posnet sell | Qeyd |
|---|---|---|
| `channel_order_id` | `invoice_no` | izləmə + idempotency açarı |
| `lines[].sku` | `products[].product_id` + `variation_id` | §2 map ilə həll olunur |
| `lines[].qty` | `products[].quantity` | |
| `lines[].unit_price_minor` | `products[].unit_price` | `/100` (decimal) |
| `totals.grand_total_minor` | `payments[].amount` | `/100`; pre-paid → method `"other"` |
| `customer.name` | `contact_id` | default walk-in (config); ya da contact create/lookup (`POST /connector/api/contactapi`) |
| — | `location_id` | CONFIG |
| — | `status="final"`, `source="api"` | sabit |

**Shipping status (opsional):** `POST /connector/api/update-shipping-status` `{transaction_id, shipping_status: ordered|packed|shipped|delivered|cancelled}` — kanal kargo statusu → Posnet.

**Idempotency:** Connector API native idempotency açarı vermir. `invoice_no = channel_order_id` qoy + push-dan əvvəl `GET /connector/api/sell?...` ilə yoxla (və ya hub-tərəfi `channel_orders` artıq dedup edir — webhook idempotent, AI-2.5.4). Retry-də ikiqat sell riski → hub-tərəfi guard + invoice_no yoxlaması.

---

## 4. Köməkçi endpoint-lər (config/seed üçün)

| Məqsəd | Endpoint |
|---|---|
| Business config + currency + walk-in customer | `GET /connector/api/business-details` |
| Location-lar (online location_id seç) | `GET /connector/api/business-location` |
| Payment method-lar | `GET /connector/api/payment-methods?location_id={loc}` |
| Stok report (alternativ pull) | `GET /connector/api/product-stock-report?location_id={loc}` |
| Customer create/lookup | `GET/POST /connector/api/contactapi` |

Base URL: `{APP_URL}` (Posnet deployment domeni) + `/connector/api/...` (versiya prefix yox).

---

## 5. `PosnetConnector` üçün lazımi dəyişikliklər (real swap, V1.4/Q-003)

Hazırkı connector (`services/core/app/adapters/posnet/connector.py`) mock-shaped (`GET /catalog`, `POST /orders`). Real üçün:

1. **OAuth token manager** (§1) — `auth_headers` statik header əvəzinə token al/cache/refresh.
2. **`pull_catalog`** → `GET /connector/api/variation?per_page=-1` + `_to_canonical` real variation shape-ə (§2) + SKU→(product_id, variation_id) map qur+cache.
3. **`push_order`** → `POST /connector/api/sell` `{sells:[...]}` (§3) + SKU resolution + config (location_id, contact_id, payment method).
4. **Config genişlənmə:** `PosnetConfig`-ə `oauth_client_id`, `oauth_client_secret`, `api_user`, `api_password` (hamısı **Vault ref**-dən), `location_id`, `walk_in_contact_id`, `price_includes_tax: bool`. Per-tenant (`channels.config`/`pos_connections`).
5. **Contract test:** real cavab nümunələri (variation + sell) `tests/contract`-da capture → mapping testi (real API-yə dəymədən).

---

## 6. Operatordan tələb (Q-003 — yalnız credential qalır)

İnterfeys **məlumdur** (bu sənəd). Qalan = **credential → Vault** (AI ref istifadə edir, dəyər yazmır):

| Vault path (təklif) | Dəyər | Mənbə |
|---|---|---|
| `vault://secret/posnet/<tenant>/base_url` | Posnet deployment URL | operator (deployment) |
| `vault://secret/posnet/<tenant>/oauth_client_id` | Passport client id | superadmin UI `/connector/clients` |
| `vault://secret/posnet/<tenant>/oauth_client_secret` | Passport client secret | həmin yer |
| `vault://secret/posnet/<tenant>/api_user` | API user email | operator |
| `vault://secret/posnet/<tenant>/api_password` | API user password | operator |
| (config, sirr deyil) `location_id`, `walk_in_contact_id`, `price_includes_tax` | int/int/bool | `business-details` + `business-location`-dan seçilir |

> **"API keys" sessiyasında** operator OAuth client + token yaratdı (Posnet A, superadmin). Həmin **dəyərlər Vault-a yazılmalıdır** (operator) — bu repo-ya YAZILMIR (detect-secrets bloklayar, ADR-0014). AI yalnız `vault://...` ref işlədir.

---

## 7. Açıq suallar / qabıqlar

- **Qiymət tax:** `sell_price_inc_tax` (tax-daxil) vs `default_sell_price` (tax-xaric) — config (`price_includes_tax`). Kanal hansını istəyir? (marketplace adətən tax-daxil).
- **Stok location:** tək online location vs cəm. Hazırda V1.1 hub tək online-sellable anbara mirror edir (`sync_tenant_catalog_from_pos`) — Posnet location_id ona uyğunlaşır.
- **Idempotency:** §3 — `invoice_no=channel_order_id` + hub-tərəfi guard; retry-də ikiqat sell qarşısı təsdiqlənməli.
- **Webhook (Posnet→hub real-time):** Connector API **pull-only** görünür (push webhook native yox) → katalog/stok sync **dövri** (`make pos-sync`) qalır; real-time lazımsa Posnet-də webhook/event əlavəsi (ayrı iş).
- **Currency minor:** AZN minor = ×100; UltimatePOS decimal-string → `round(float×100)`. Yarım-qəpik yoxlanmalı.

## Əlaqəli
- ADR-0021 (mock-first connector), ADR-0022 (swap planı), HUMAN-GATES Q-003
- Mənbə kod: `Posnet A/Modules/Connector/{Routes/api.php, Http/Controllers/Api/*, Transformers/*}`
