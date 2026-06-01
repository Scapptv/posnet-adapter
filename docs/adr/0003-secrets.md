# ADR-0003 — Sirr İdarəsi (Vault-only)

**Status:** ACCEPTED
**Tarix:** 2026-06-01 (retroaktiv)
**Qəbul edən:** İnsan operator + AI
**Əlaqəli:** ADR-0001, AI-ROADMAP.md §9, HUMAN-GATES.md (Sirr Tələbləri)

## Kontekst

Hub kanal credential-ları (Birmarket/Trendyol API key + HMAC), DB password, Keycloak client
secret saxlayır. Sirlər heç vaxt kodda, log-da və ya commit-də olmamalıdır.

## Qərar

**HashiCorp Vault** tək sirr mənbəyi. Kod yalnız `vault://path` ref istifadə edir.

- `.env.example` placeholder ilə commit; `.env` `.gitignore`-da
- `detect-secrets` pre-commit hook məcburi (baseline ilə)
- Yeni sirr axını: STATUS.md qeyd → HUMAN-GATES.md sual → insan Vault-a yazır → AI ref işlədir
- Kanal sirləri: `secret/posnet/channels/{code}/{api_key,hmac}`
- Lokal dev: Vault dev mode (`adapter_vault`); prod: real Vault + KMS auto-unseal

## Nəticələr

### Müsbət
- Sıfır sirr-leak (məcburi gate); audit trail; kanal onboarding üçün təmiz nümunə

### Mənfi / qalıq risk
- Vault dev→prod miqrasiyası diqqət tələb edir → G7-də prod policy + IaC

## Əlaqəli
- ADR-0001 (stack), AI-ROADMAP.md §9
