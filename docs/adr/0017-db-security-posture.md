# ADR-0017 — DB təhlükəsizlik duruşu: RLS FORCE + non-owner app login + dual-pool

**Status:** ACCEPTED
**Tarix:** 2026-06-03
**Qəbul edən:** AI sessiya (Faza AI-2.H1) — ADR-0016 audit A1 icrası
**Əlaqə:** ADR-0013 (eventbus owner-session) və ADR-0015 (tenant resolution) — **icra modelini dəqiqləşdirir**; ADR-0014 (dev secret sərhədi)

## Kontekst

$100M audit tapıntısı **A1** (ADR-0016): RLS `FORCE` deyildi və app `posnet` (owner/superuser)
ilə bağlanırdı. Tenant izolyasiyası **hər request-də opt-in** idi — bir unudulmuş `SET LOCAL ROLE`
= bütün tenant-lar sızar. İkinci müdafiə qatı yox idi.

Əsas gərginlik: `subject → tenant` axtarışı (Keycloak `sub` → `users.external_subject`) **təbiətən
cross-tenant-dir** (tenant hələ məlum deyil), ona görə request-in əvvəlində RLS-exempt giriş tələb edir.
Mövcud həll bunu superuser bağlantısı ilə edirdi, sonra `posnet_app`-ə keçirdi.

## Qərar

### 1. Non-owner app login rolu (ikinci qat)
`posnet_app` artıq **LOGIN** rolu (əvvəl NOLOGIN), `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`.
App-ın **per-request pool-u bu rolla bağlanır**. Unudulmuş tenant scope = **0 sətir** (RLS), sızma yox.

### 2. Dual-pool bağlantı modeli
- **App pool** (`DATABASE_APP_URL` → `posnet_app`): per-request tenant-scoped yol. Boşdursa `DATABASE_URL`-ə düşür (dev/test rahatlığı).
- **System pool** (`DATABASE_URL` → superuser/owner): **migration**, **super_admin** (cross-tenant), **eventbus relay/consumer** (bütün tenant-ların outbox-u), **onboarding/seed** (yeni tenant yaradılması — mövcud kontekst yox).

`super_admin` artıq "owner-də qal" deyil — açıq şəkildə system pool-dan istifadə edir. ADR-0013-ün
"owner sessionmaker = cross-tenant" prinsipi qalır, amma indi **iki ayrı pool** ilə açıq ifadə olunur.

### 3. RLS FORCE bütün policy cədvəllərinə
`ALTER TABLE ... FORCE ROW LEVEL SECURITY` RLS aktiv olan hər cədvələ (dinamik: `relrowsecurity`
olan hamısı). FORCE table owner-i də RLS-ə tabe edir — gələcəkdə ownership dəyişərsə müdafiə +
audit tələbini ödəyir. (Superuser onsuz da bypass edir → migration/system pool təsirsiz.)

### 4. SECURITY DEFINER resolver (kontrollu cross-tenant axtarış)
`posnet_resolve_tenant(p_subject text) RETURNS uuid` — `SECURITY DEFINER`, sabit `search_path`,
`PUBLIC`-dən `REVOKE`, yalnız `posnet_app`-ə `GRANT EXECUTE`. Kilidli app pool bu **bir** cross-tenant
axtarışı funksiya vasitəsilə (owner=superuser kimi işləyir) edir, sonra `app.current_tenant` qoyur.
Funksiya yalnız aktiv istifadəçinin `tenant_id`-sini qaytarır — minimal məruzqalma.

### 5. Dev parol (ADR-0014 sərhədi daxilində)
Migration `posnet_app`-ə `DATABASE_APP_PASSWORD` env-dən parol verir; yoxdursa dev default
(`posnet_app_dev_pw`, `# pragma: allowlist secret`). Bu **dev credential**-dir (ADR-0014 → gate yox).
Prod-da deploy env-i Vault-dan doldurur.

## Nəticələr
- (+) A1 bağlandı: app non-owner; unudulmuş scope = 0 sətir, leak yox; FORCE ikinci qat.
- (+) Mövcud testlər dəyişməz keçir (fallback: `DATABASE_APP_URL` boşdursa app pool = system pool).
- (+) Resolver tək, audit-edilə-bilən cross-tenant nöqtə; qalan hər şey kilidli pool-da.
- (−) İki pool/engine (kiçik əlavə yük); resolver `SECURITY DEFINER` (sabit search_path ilə bərkidilib).
- **Risk azaldılması:** adapterlərdən əvvəl təməl təhlükəsizlik bərkidilir (ADR-0016 sırası).
