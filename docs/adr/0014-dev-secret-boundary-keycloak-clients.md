# ADR-0014 — Dev/prod sirr sərhədi + Keycloak foundation client topologiyası

**Status:** ACCEPTED
**Tarix:** 2026-06-02
**Qəbul edən:** AI sessiya (Faza AI-1.7) + İnsan operator (gate çərçivələməsini düzəltdi)
**Əlaqəli:** ADR-0003 (Sirr idarəsi), CLAUDE.md (Sirr-lər / Human gate), AI-ROADMAP.md §15

## Kontekst

AI-1.7 (Keycloak realm) ilk baxışda **sirr human-gate**-inə dəyirmiş kimi çərçivələndi
(confidential client secret → Vault → yalnız insan yazır). Operator peşəkar yenidən-baxış
istədi. Gərginlik: CLAUDE.md "HEÇ VAXT sirr commit-də" + "Vault-a sirr yaza bilmərəm" —
AMMA dev mühitini onsuz da AI qurub və dev credential-lar (`dev-root-token`, `posnet_dev_pw`,
Keycloak `admin/admin`) `docker-compose.yml`-də `# pragma: allowlist secret` ilə commit olunub.

Yəni "hər sirr gate-dir" çərçivələməsi səhv idi: dev-mode credential ≠ prod secret.

## Variantlar

1. **AI-1.7-ni gate kimi blokla** — insan Keycloak secret-i Vault-a yazana qədər gözlə.
   Mənfi: dev AuthN qurulması süni şəkildə bloklanır; dev stack onsuz da AI-nin qurduğu
   dev credential-larla işləyir (ziddiyyət).
2. **Foundation realm-ı secret-siz qur** — modern OIDC: SPA/mobil = public+PKCE, API =
   bearer-only (yalnız JWKS ilə doğrulayır). Heç bir client secret yox → gate yox.

## Qərar

**Variant 2.**

### Sirr sərhədi (human-gate nə vaxt tətbiq olunur)
- **Gate VAR:** (a) AI-nin əldə edə bilmədiyi REAL external credential (Birmarket/Trendyol
  API key); (b) **PROD** secret-lər (real Vault, G7).
- **Gate YOX:** DEV-mode infrastructure credential = məlum dev dəyəri. Mövcud konvensiya ilə
  commit olunur: kod/YAML-da `# pragma: allowlist secret`; JSON kimi şərh dəstəkləməyən
  fayllarda detect-secrets baseline audit.

### Keycloak foundation client topologiyası (secret-siz)
- `posnet-web` (admin/storefront SPA) — **public client + PKCE (S256)**
- `posnet-pos` (Flutter) — **public client + PKCE**, dev üçün direct access grants
- `api-gateway` (backend) — **bearer-only**: yalnız JWKS public açarı ilə token doğrulayır,
  secret saxlamır
- 5 realm rolu (§15 RBAC): super_admin, tenant_admin, store_manager, cashier, clerk
- Realm-as-code: `infra/keycloak/realm-posnet.json`, dev stack-ə `--import-realm` ilə yüklənir

Confidential client secret yalnız REAL confidential flow (BFF / token-exchange /
client-credentials) lazım olanda yaranır; onun **prod** dəyəri G7-də insan tərəfindən Vault-a
yazılır (`vault://secret/posnet/keycloak/...`). Foundation bunu tələb etmir.

## Nəticələr

### Müsbət
- AI foundation AuthN-i bloksuz qurur (insan asılılığı yalnız əsl prod/external secret-lərdə)
- Sıfır client secret = sıfır secret-leak səthi; modern OIDC nümunəsi (public+PKCE)
- Əsl gate düzgün yerə (G7 prod) düşür; dev sürəti saxlanılır

### Mənfi / qalıq risk
- `tenant_id` claim strategiyası (Keycloak user attribute vs DB lookup) **AI-1.11-ə təxir** —
  foundation realm AuthN-fokuslu qalır (token-da tenant_id mapper yox)
- Confidential flow gələndə client secret + Vault wiring əlavə olunmalı (prod-gated, G7)
- Dev test-user parolu (`owner-dev-2026`) realm JSON-da məlum dev dəyəridir — prod realm
  ayrı qurulur (insan / IaC, G7)

## Əlaqəli
- ADR-0003 (Sirr idarəsi — Vault-only), CLAUDE.md (Human gate davranışı)
- `infra/keycloak/realm-posnet.json`, `docker-compose.yml` (keycloak `--import-realm`)
- AI-ROADMAP.md §15 (RBAC), HUMAN-GATES.md (gate jurnalı)
