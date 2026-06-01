# ADR-0011 — Beachhead Re-scope (Faza Dondurma + Validasiya Gate)

**Status:** ACCEPTED
**Tarix:** 2026-06-01
**Qəbul edən:** İnsan operator (strateji qərar) + AI sessiya (sənədləşdirmə)
**Əlaqəli:** Tam audit (2026-06-01), ADR-0001 (Stack), AI-ROADMAP.md §10 (faza diaqramı)

## Kontekst

2026-06-01 tarixli tam audit göstərdi ki, AI-ROADMAP.md v3.0 (111 task, 8 faza,
~280–410 saat təxmin) cari icra modelinə (1 AI + 1 insan operator) və validasiya
səviyyəsinə (0 müştəri sübutu) görə **kritik dərəcədə həddən artıq genişdir**.

Aşkar edilən əsas risklər:

| # | Risk | Səviyyə |
|---|---|---|
| M1 | Validasiyasız qurma (0 müştəri sübutu, müsahibə, LOI) | KRİTİK |
| M2 | Scope ≫ tutum (qlobal hər-kanal platforma, 1 builder) | KRİTİK |
| M3 | Ən çətin/dəyərli inteqrasiya (fiskal) sona qalır | KRİTİK |
| M4 | Horizontal "hər şey platforması", beachhead yoxdur | YÜKSƏK |

## Variantlar (audit forku, 2026-06-01)

1. **Nazik dilim əvvəl** — bir real uçtan-uca dilim (real fiskal daxil) qur, onunla
   validasiya et. Risk-sırasını tam düzəldir, amma mövcud roadmap sırasını pozur.
2. **Validasiya əvvəl** — bütün kodu dayandır, əvvəl bazar validasiyası. Bazar riski
   üçün ən təhlükəsiz, amma kod irəliləməsi dayanır.
3. **Yalnız yenidən scope** — faza sırası saxlanılır, uzaq fazalar dondurulur,
   AI-2-dən sonra validasiya gate-i əlavə olunur.

## Qərar

**Variant 3 ("Yalnız yenidən scope")** seçildi (operator qərarı).

### Beachhead (hədəf seqment)
- **Coğrafiya:** Azərbaycan (artıq kilidli — dəyişməz)
- **Seqment:** Kafe/restoran **+** kiçik pərakəndə/market
- **Fokus qaydası:** v1 yalnız **ortaq nüvəni** qurur (kataloq, inventar, satış, çek,
  ödəniş — ~80% paylaşılır). Ayrışan funksiya (food service: masa/sifariş;
  pərakəndə: barkod-ağır inventar) **ilk imzalayan satıcıya görə** seçilir.

### DAVAM EDƏN (in-scope — sıra dəyişməz)
- **Faza AI-0** (Bootstrap) — task 0.3 … 0.11 tamamla
- **Faza AI-1** (Foundation) — auth, multi-tenant, RLS, DB, pgmq, observability
- **Faza AI-2** (POS Core) — kataloq, inventar, qiymət, vardiya, satış, Flutter
  kassir, admin panel = **fiziki POS MVP** (mock fiskal ilə)

### YENİ GATE — G-V (Validasiya)
AI-2 MVP-dən sonra, AI-3-ə **keçməzdən əvvəl** məcburi:
- MVP operator-un tanıdığı 5–10 satıcıya (kafe + pərakəndə) demo edilir
- Strukturlaşmış geri-bildirim toplanır (validation toolkit — AI hazırlayır)
- Aşağıdakı kill/continue kriteriyası yoxlanılır
- ✅ keçərsə → AI-3+ açılır; ❌ keçməzsə → narrow (1 seqment) və ya pivot

### DONDURULAN (G-V keçənə qədər BAŞLANMIR)
- Faza AI-3 (Order Management + Adapter)
- Faza AI-4 (Mock Marketplace Pilot)
- Faza AI-5 (Online + Category + Storefront + Delivery)
- Faza AI-6 (Accounting + Multi-country)
- Faza AI-7 (Booking + Cloud Scale + DR)

### PULLED FORWARD (M3 de-risk)
- **Real AZ fiskal (OPK / e-Kassa) inteqrasiyası** — köhnə planda Faza AI-7 idi.
  İndi: **G-V keçdikdən sonra, real pilotdan ƏVVƏL**. (Mock fiskal yalnız
  demo/validasiya üçün; real satışda real OPK çeki hüquqi məcburidir.)

## Kill / Continue kriteriyası (G-V gate)

Continue (AI-3+ açılır) yalnız əgər:

- [ ] ≥ 5 satıcı MVP-ni canlı gördü
- [ ] ≥ 3 satıcı konkret ağrı + ödəmə istəyi ifadə etdi ("bunu istifadə edərdim")
- [ ] ≥ 1 satıcı pilot üçün şifahi razılıq verdi
- [ ] Qiymət hipotezi (aylıq / terminal başına) ≥ 3 satıcı tərəfindən rədd edilmədi

Əks halda: **narrow** (yalnız 1 seqmentə fokuslan) və ya **pivot**.

## Nəticələr

### Müsbət
- Scope AI-3…AI-7 dondurulur → tutum AI-0…AI-2-yə fokuslanır
- Validasiya artıq məcburi gate-dir (M1, M4 qismən həll)
- Operator-un satıcı çıxışı paralel discovery-ə imkan verir (momentum itmir)

### Mənfi / qalıq risk
- **Risk-sırası tam düzəlmir:** fiskal hələ AI-2-dən sonraya qalır (audit
  thin-slice-first tövsiyə etmişdi). *Azaltma:* mock fiskal demo/validasiya üçün
  kifayət; real fiskal G-V-dən sonra, pilotdan əvvəl.
- **İki seqment fokusu seyreldir.** *Azaltma:* yalnız ortaq nüvə v1-də; ayrışan
  funksiya ilk satıcıya görə.

## Geri dönmə

Bu ADR scope-u **daraldır**, kod silmir. G-V nəticəsinə görə yenilənə bilər
(narrow → 1 seqment, və ya pivot). Faza dondurmanın ləğvi **yeni ADR** tələb edir.

## Əlaqəli
- Audit hesabatı (2026-06-01 sessiya)
- AI-ROADMAP.md §10 (faza diaqramı), §19–21 (AI-0/1/2 task-ları)
- STATUS.md (strategiya banner), HUMAN-GATES.md (G-V gate + D-001 qərar jurnalı)
