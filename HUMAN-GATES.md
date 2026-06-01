# HUMAN GATES — Posnet

Bu fayl AI ↔ insan operator arasında gate keçidləri və açıq sualların jurnalıdır.

**Qayda:** AI gate-ə çatdıqda burada giriş yaradır. İnsan operator cavab/icazə verir. Bu fayl audit trail-dir.

---

## Gate Statusu

| Gate | Faza | Status | İcazə tarixi | İcazə verən |
|---|---|---|---|---|
| G0 — Bootstrap done | AI-0 | ⏳ Gözləyir | — | — |
| G1 — Foundation done | AI-1 | ⏳ Planlandı | — | — |
| G2 — POS Core done | AI-2 | ⏳ Planlandı | — | — |
| G3 — Order Mgmt done | AI-3 | ⏳ Planlandı | — | — |
| G4 — Mock Pilot done (MVP) | AI-4 | ⏳ Planlandı | — | — |
| G5 — Online + Category done | AI-5 | ⏳ Planlandı | — | — |
| G6 — Accounting done (**hüquqi**) | AI-6 | ⏳ Planlandı | — | — |
| G7 — Staging deploy (**$ ilk dəfə**) | AI-7 | ⏳ Planlandı | — | — |
| G8 — Production go-live (**reputasiya**) | AI-7 | ⏳ Planlandı | — | — |

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
