# ADR-0015 — Tenant həlli strategiyası: Keycloak subject → DB lookup

**Status:** ACCEPTED
**Tarix:** 2026-06-03
**Qəbul edən:** AI sessiya (Faza AI-1.9.3 / AI-1.11)
**Əlaqəli:** ADR-0014 (təxir etdiyi qərar), ADR-0013 (per-request `posnet_app` rolu),
AI-ROADMAP.md §15 (AI-1.11), libs/auth `Principal`

## Kontekst

ADR-0014 foundation Keycloak realm-ını **secret-siz** (public+PKCE / bearer-only) qurdu,
amma bir qərarı açıq saxladı (ADR-0014 qalıq risk): *token-da `tenant_id` necə daşınır?*
Foundation realm-ı yalnız AuthN-fokuslu idi → token-da tenant claim yoxdur, ona görə
`Principal`-də (libs/auth) qəsdən `tenant_id` sahəsi yoxdur.

İndi (AI-1.11) per-request RLS injection lazımdır: hər sorğu üçün
`SET LOCAL app.current_tenant = <tenant_id>` qoyulmalıdır ki, `posnet_app` rolu altında
RLS tenant-i izolyasiya etsin (ADR-0013). Beləliklə `Principal` → `tenant_id` xəritələnməsi
qərarı tələb olunur.

İdentifikatorlar:
- Token `sub` = Keycloak user UUID (issuer daxilində qlobal, dəyişməz).
- `users` cədvəlində: öz `id` (UUID PK), `tenant_id`, `email` var; Keycloak ilə bağ **yox idi**.
- `email` yalnız **tenant daxilində** unikaldır (`uq_users_tenant_email`) → qlobal deyil.

## Variantlar

1. **JWT tenant_id claim** (Keycloak user attribute + protocol mapper).
   Token özündə `tenant_id` daşıyır → DB lookup lazım deyil.
   - Mənfi: tenant üzvlüyünü Keycloak-a köçürür (iki həqiqət mənbəyi); attribute-u
     dəyişmək/ləğv etmək token-ın exp-inə qədər gecikir; foundation realm secret-siz/AuthN-fokuslu
     qalmalıdır (ADR-0014). Tenant provisioning DB-də (AI-1.15) olacaq.
2. **Email ilə lookup** (`users.email = principal.email`).
   - Mənfi: email yalnız tenant daxilində unikaldır → eyni email iki tenant-də ola bilər →
     **qeyri-müəyyən həll** (cross-tenant səhv riski). Foundation-da işləsə də, multi-tenant-də
     gizli təhlükəsizlik qüsuru.
3. **Keycloak subject ilə DB lookup** (`users.external_subject = principal.subject`).
   `external_subject` qlobal **UNIQUE** → Keycloak user ↔ DB user 1:1, deterministik.
   - Mənfi: yeni sütun (migration 0003) + onboarding zamanı doldurulmalı (AI-1.15).

## Qərar

**Variant 3.** Tenant həlli = `users.external_subject` (Keycloak `sub`) üzrə DB lookup.

- **DB = tenant üzvlüyünün tək həqiqət mənbəyi** (Keycloak yalnız AuthN). Üzvlük dəyişikliyi
  dərhal qüvvəyə minir (token re-issue gözləmir).
- `external_subject` qlobal `UNIQUE`, `NULL` icazəli (provisioning-dən əvvəlki / xidmət hesabları);
  amma **autentifikasiya olunmuş principal üçün uyğun sətir tapılmalıdır** — tapılmasa
  `ForbiddenError` (403): token etibarlıdır (AuthN keçdi), lakin DB-də aktiv tenant üzvlüyü yoxdur.
- Lookup **`status = 'active'`** filtri ilə (deaktiv user tenant konteksti almır).
- Lookup sorğusu request tranzaksiyasında **owner rolunda** (RLS-exempt) `SET LOCAL ROLE posnet_app`-dən
  ƏVVƏL işləyir → bütün tenant-ləri görüb subject-ə görə uyğunu tapa bilir. Sonra rol `posnet_app`-ə
  keçir + GUC qoyulur → handler sorğuları RLS-scoped olur (ADR-0013 "per-request `posnet_app` rolu").
- **super_admin** (sistem rolu): tenant həlli atlanır → owner rolunda (RLS-exempt) cross-tenant işləyir.

`tenant_id` `Principal`-ə **əlavə edilmir**: o, AuthN claim-i deyil, request-scoped DB faktıdır.
Tenant `request.state.tenant_id`-də və scoped session-da yaşayır.

## Nəticələr

### Müsbət
- Deterministik, qlobal-unikal subject→tenant xəritəsi (email qeyri-müəyyənliyi yox).
- Keycloak AuthN-fokuslu qalır (ADR-0014 pozulmur); tenant üzvlüyü DB-də (provisioning AI-1.15).
- Fail-safe: subject DB-də yoxdursa 403 (token-da uydurma tenant claim-ə etibar yox).

### Mənfi / qalıq risk
- AI-1.15 (tenant onboarding) hər user yaradılanda `external_subject`-i Keycloak `sub` ilə
  doldurmalıdır; əks halda həmin user login edə bilməz (403). Onboarding flow bunu təmin etməlidir.
- App owner rolunda login edib per-request `SET LOCAL ROLE posnet_app`-ə keçir (ADR-0013). Bu o deməkdir
  ki, scoping unudulsa owner RLS-exempt qalar (fail-open riski). Azaldılma: scoping vahid
  `get_tenant_session` dependency-də mərkəzləşib (tək kod yolu, test edilib). **Sərtləşdirmə**
  (login rolunu birbaşa `posnet_app` etmək = fail-closed) sonrakı infra task-ında (DB rol/secret
  wiring) nəzərdən keçirilir.
- Resolve lookup hər request-də 1 əlavə sorğudur (subject üzrə indeksli, ucuz).

## Əlaqəli
- migration `0003_user_external_subject` (sütun + unique index)
- `services/core/app/infrastructure/db/tenant.py` (resolve + scope), `app/api/deps.py` (`get_tenant_session`)
- ADR-0013 (per-request `posnet_app` rolu / relay cross-tenant rolu AI-1.9.5), ADR-0014 (təxir mənbəyi)
- AI-ROADMAP.md §15 (AI-1.11); G1 acceptance: RLS izolasiya
