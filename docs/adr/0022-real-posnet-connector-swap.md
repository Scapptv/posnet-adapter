# ADR-0022 — Real Posnet connector swap planı (mock → real, gated)

**Status:** ACCEPTED
**Tarix:** 2026-06-05
**Qəbul edən:** İnsan operator (Scapptv) + AI sessiya
**Əlaqəli:** ADR-0021 (POS-tərəfi connector), ADR-0014 (sirr gate sərhədi), ADR-0003 (Vault), AI-ROADMAP.md §17.7, HUMAN-GATES.md Q-003

## Kontekst

AI-2.8 (8.1–8.4) **mock-first Posnet connector**-i tam çatdırdı: `PosSourceAdapter` Protocol + in-memory `MockPosnetSource` + HTTP mock + `PosnetConnector` (httpx) + `push_order` write-back + `make pos-sync` dövri sync cron + uçtan-uca E2E (`test_e2e_full_loop.py`). Connector **swap-ready**-dir: bütün upstream (sync engine, webhook, cron) yalnız `PosSourceAdapter` kontraktına bağlıdır; mock→real keçid prinsipcə base-URL dəyişikliyidir.

Lakin **real swap** üç şey tələb edir, hər üçü **gated** (operator/insan verməlidir, AI əldə edə bilməz — CLAUDE.md "NƏ EDƏ BİLMƏRƏM"):
1. **Real Posnet interfeysi** — API/DB/format (catalog pull + order push endpoint-ləri, sahə şəkilləri).
2. **Auth sxemi + credential** — Bearer token / API key / HMAC / başqa; real sirr.
3. **Per-tenant bağlantı konfiqi** — hər tenant-ın Posnet base URL + credential ref-i.

Real Posnet interfeysi məlum olmadan **real connector kodu yazmaq spekulyasiyadır** (API formatını təxmin etmək). Bu ADR swap-ı **spekulyativ olmayan** şəkildə hazırlayır: seam-lər qoyulur, addımlar sənədləşir; interfeys+credential gələndə dəyişiklik minimal+təhlükəsiz olur.

## Qərar

1. **Auth seam (qoyuldu):** `PosnetConfig.auth_headers: Mapping[str, str] | None` — **scheme-agnostik** header map, hər request-ə tətbiq olunur (Bearer / API-key / custom). Wiring tərəfindən **Vault ref-dən resolve olunur, heç vaxt hardcode olunmur** (ADR-0014/0003 sirr qaydası). Mock onu `None` saxlayır. Test: `test_auth_headers_ride_on_the_client` (Docker-siz).

2. **Per-tenant config seam:** real Posnet bağlantısı (base_url + credential ref + format hint-ləri) per-tenant konfiqdə yaşayır — ya `channels.config`-tipli JSONB, ya yeni `pos_connections` cədvəli — `build_pos_source_factory` hər tenant üçün resolve edir. Hazırda tək `POSNET_BASE_URL` (boş→no-op); real swap bunu per-tenant resolve-a genişləndirir.

3. **Mapping seam:** Posnet wire şəklini bilən **yeganə iki yer** — `_to_canonical` (pull) və `push_order` body (push). Real format yalnız bu iki metodu dəyişir; upstream toxunulmur. Format çox fərqlənərsə → config-driven mapping və ya subclass.

4. **Swap addımları (operator interfeys+credential verəndə):**
   1. Operator Posnet base_url + credential-i **Vault-a yazır** (`vault://secret/posnet/<tenant>/...`); AI ref istifadə edir.
   2. AI `build_pos_source_factory`-ni per-tenant Vault ref → `auth_headers` resolve edəcək şəkildə wire edir.
   3. AI `_to_canonical`/`push_order`-u real wire şəklinə uyğunlaşdırır + **contract test** (real cavab nümunələrinə qarşı).
   4. Per-tenant config real endpoint-ə keçirilir.
   5. Connector eyni `PosSourceAdapter` kontraktında swap olunur — **sıfır upstream dəyişiklik**.

5. **Spekulyativ real connector yox:** interfeys məlum olana qədər real connector kodu yazılmır. Auth + config seam-ləri spekulyativ-olmayan təməl işidir.

## Operatordan tələb (HUMAN-GATES Q-003)

- Posnet **API/DB/format spec**-i: catalog pull (məhsul/variant/stok/qiymət sahələri) + order push (sifariş/çek şəkli) endpoint-ləri.
- **Auth sxemi** (Bearer/API-key/HMAC/...) + **credential** (→ Vault, AI ref istifadə edir).
- Per-tenant **base URL**(lar).

## Nəticələr

### Müsbət
- Swap **turnkey + minimal**: seam-lər hazırdır, addımlar sənədlidir; gate konkretdir (operator nə verəcəyini dəqiq bilir).
- Sirr qaydası pozulmur: credential Vault-da, kod yalnız ref + resolved header (transient) görür.
- Upstream toxunulmaz: yalnız mapping (2 metod) + wiring real formata uyğunlaşır.

### Mənfi / qalıq risk
- Real Posnet interfeysi hələ məlum deyil → real dataflow production-da yoxdur (mock/admin-web stand-in). Operator gate-i açana qədər (Q-003) bloklu.
- `auth_headers` Bearer/header-əsaslı auth fərz edir; Posnet **query-param key** və ya **mTLS** istifadə edərsə, seam genişləndirilməlidir (kiçik dəyişiklik).

## Əlaqəli
- ADR-0021 (mock-first connector), ADR-0014 (dev vs prod sirr gate), ADR-0003 (Vault ref)
- HUMAN-GATES.md Q-003 (real Posnet interfeys + credential gate)
- AI-ROADMAP.md §17.7
