# HUMAN GATES — Posnet

Bu fayl AI ↔ insan operator arasında gate keçidləri və açıq sualların jurnalıdır.

**Qayda:** AI gate-ə çatdıqda burada giriş yaradır. İnsan operator cavab/icazə verir. Bu fayl audit trail-dir.

---

## Gate Statusu

| Gate | Faza | Status | İcazə tarixi | İcazə verən |
|---|---|---|---|---|
| G0 — Bootstrap done | AI-0 | ⏳ Gözləyir | — | — |
| G1 — Foundation done | AI-1 | ⏳ Planlandı | — | — |
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

---

## Açıq Suallar (AI → İnsan)

(yox)

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
