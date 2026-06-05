# G-V Validasiya Kit — retail satıcı demo + strukturlaşmış geri-bildirim

**Məqsəd:** AI-2.5 MVP-ni (POS-anchored inteqrasiya hub crown jewel) 5–10 retail satıcıya demo
etmək və **kill/continue** qərarı üçün strukturlaşmış siqnal toplamaq (ADR-0011 G-V gate,
AI-ROADMAP §18). Bu kit operatorun (Scapptv) sahə alətidir — AI demo edə bilmir, amma turnkey edir.

**Status:** AI-2.5 ✅ APPROVED (2026-06-05). G-V AKTİV. Hər satıcı üçün §3 forması doldur → §4 cədvəlinə
yaz → §5 qərar qaydası ilə kill/continue → nəticəni HUMAN-GATES.md G-V girişinə köçür.

---

## 1. Hazırlıq (demo-dan əvvəl, bir dəfə)

**İdeal canlı demo (admin-web):**
1. Dev stack qaldır: `make up` (Docker stabil olmalı — bax memory `docker-desktop-flaky`).
2. Migration + seed: `make migrate` → test tenant + admin user (`make seed`).
3. Mock Posnet kataloqu çək (məhsul mənbəyi): `POSNET_BASE_URL=<mock> make pos-sync` **və ya** admin-web-də
   2-3 məhsul əl ilə yarat (demo üçün yetərli — "Posnet-dən gələn məhsul" kimi danış).
4. Mock kanal + mock-marketplace qalxsın (kanal görünüşü üçün).
5. admin-web aç (`apps/admin-web`), Keycloak login (test satıcı).

**Fallback (stack yoxdursa / Docker qeyri-stabil):** uçtan-uca loop-u testlə göstər —
`uv run pytest tests/integration/test_e2e_full_loop.py -s` — və §2 6-addımını çıxış üzərində danış.
(Test = eyni dövrənin icra-edilə-bilən sübutu: Posnet→kanal→Posnet, 0 oversell.)

**Vaxt:** demo ~5 dəqiqə + ~10 dəqiqə geri-bildirim.

---

## 2. Demo skripti (~5 dəqiqə) — "məhsulunu Birmarket-ə 5 dəqiqəyə çıxar"

| # | Addım | Nə göstərilir | Nə deyilir (satıcıya) |
|---|---|---|---|
| 1 | **Posnet-dən çək** | admin-web məhsul siyahısı (Posnet kataloqu mirror) | "Bu sənin Posnet məhsulların — qiymət, stok onsuz da burada." |
| 2 | **Publish** | "Kanala çıxar" toggle → online_published | "Bir düymə — məhsulu online çıxarırsan." |
| 3 | **Kanala push** | Kanallar tabı → listing göründü (sku/qiymət/stok) | "Avtomatik Birmarket/Trendyol-da listing oldu — Posnet qiymət+stok ilə." |
| 4 | **Sifariş gəlir** | (mock kanal sifariş → webhook) order `reserved` | "Müştəri Birmarket-dən aldı — sifariş avtomatik sənə düşür." |
| 5 | **Stok hər yerdə düşür** | inventar + kanal listing stoku azaldı | "Stok həm sistemdə, həm kanalda düşdü — **oversell yox**." |
| 6 | **Posnet-ə yazılır** | (write-back) satış Posnet-ə qeyd | "Satış geri Posnet-ə yazıldı — tək həqiqət mənbəyi sənin POS-undur." |

**Əsas mesaj:** *"Posnet məhsulun 1 addımda marketplace-də, sifariş Posnet-ə düşür, stok hər yerdə dürüst."*

---

## 3. Geri-bildirim forması (HƏR satıcı üçün doldur)

```
Satıcı #: ___   Tarix: ____-__-__   Şəhər/segment: ________   Profil: market / butik / kafe / digər

Hazırkı vəziyyət:
- Neçə kanalda satır? (yox / 1 / 2+): ____
- İndi necə idarə edir? (əl ilə / Excel / başqa integrator / heç): ____________
- Ən böyük ağrı? (oversell / əl-iş / stok uyğunsuzluğu / vaxt / digər): ____________

Demo reaksiyası (kill/continue siqnalları — §5):
[ ] S1. MVP-ni gördü (demo tam izlədi)
[ ] S2. Konkret ağrı + ödəmə istəyi ("bunu istifadə edərdim / ödəyərdim") — sitat: "________________"
[ ] S3. Pilot razılığı ("sınamağa hazıram") 
[ ] S4. Qiymət hipotezi rədd OLUNMADI (təxmini qiymət deyildi → "baha" demədi)

Qiymət reaksiyası (deyilən təxmini qiymət: ______ / ay):
( ) ucuz  ( ) münasib  ( ) baha  ( ) rədd

Sərbəst qeydlər (öz sözləri, ən dəyərli sitat):
__________________________________________________________________
İstədiyi #1 əlavə özəllik: __________________________________________
```

---

## 4. Aggregate tracking (bütün satıcılar)

| Satıcı | Profil | S1 gördü | S2 ağrı+ödəmə | S3 pilot | S4 qiymət-OK | Qiymət reaksiya | Açar sitat |
|---|---|---|---|---|---|---|---|
| 1 | | ☐ | ☐ | ☐ | ☐ | | |
| 2 | | ☐ | ☐ | ☐ | ☐ | | |
| 3 | | ☐ | ☐ | ☐ | ☐ | | |
| 4 | | ☐ | ☐ | ☐ | ☐ | | |
| 5 | | ☐ | ☐ | ☐ | ☐ | | |
| 6 | | ☐ | ☐ | ☐ | ☐ | | |
| 7 | | ☐ | ☐ | ☐ | ☐ | | |
| 8 | | ☐ | ☐ | ☐ | ☐ | | |
| 9 | | ☐ | ☐ | ☐ | ☐ | | |
| 10 | | ☐ | ☐ | ☐ | ☐ | | |
| **CƏM** | | **__/10** | **__/10** | **__/10** | **__/10** | | |

---

## 5. Kill / Continue qərar qaydası (AI-ROADMAP §18)

**✅ CONTINUE** (genişlənmə açılır) — HAMISI ödənməlidir:
- [ ] **≥ 5** satıcı MVP gördü (S1)
- [ ] **≥ 3** satıcı konkret ağrı + ödəmə istəyi (S2)
- [ ] **≥ 1** satıcı pilot razılığı (S3)
- [ ] Qiymət hipotezi **≥ 3** satıcıda rədd olunmadı (S4)

**❌ KILL / narrow / pivot** — yuxarıdakılar ödənmirsə: hansı siqnal zəifdir analiz et →
narrow (daha dar segment) və ya pivot (fərqli ağrı/dəyər).

---

## 6. Demo-dan sonra (operator → AI)

1. Nəticəni (CONTINUE / KILL+səbəb + aggregate cədvəl) **HUMAN-GATES.md G-V girişinə** köçür + imzala.
2. **CONTINUE** isə: Part V açılır (real Birmarket/Trendyol swap → Q-003 + D-002 partner gate;
   2-ci kanal; delivery/booking). AI davam edir.
3. **KILL/pivot** isə: öyrənilən siqnal + yeni istiqamət → AI ona uyğun re-scope (yeni ADR).

> Real Posnet swap (Q-003) və partner API (D-002) **paralel** açıla bilər — G-V continue qərarından
> asılı, amma demo mock-first ilə keçirilir (real credential demo üçün lazım deyil).
