# CLAUDE.md — Posnet Project Instructions

Bu fayl Claude Code tərəfindən hər sessiya başında avtomatik yüklənir. Layihə kontekstini, qaydaları və ardıcıllığı təsvir edir.

---

## Layihə

**Ad:** Posnet — POS-anchored omnichannel İnteqrasiya Hub
**Model:** POS = tək həqiqət mənbəyi; hub məhsul/stok/qiyməti marketplace/delivery/booking portallarına çıxarır (TSoft/Entegra/ChannelEngine tipli). **Adapterlər = məhsulun CORE-u**, periferik deyil.
**Beachhead:** Azərbaycan · pərakəndə (market/butik) · ilk kanal = Birmarket/Trendyol (marketplace)
**Strateji:** ADR-0011 (re-scope) + ADR-0012 (hub reframe). Aktiv yol: AI-0→1→2→**2.5 (adapter framework)**→**G-V validasiya**. AI-3…AI-7 dondurulub.
**Tip:** Multi-tenant SaaS, modular monolit, event-driven, adapter-first
**Hədəf bazarlar:** Azərbaycan (1-ci) → Türkiyə (2-ci) → Qlobal
**İcra modeli:** AI-autonomous (1 Claude Opus + 1 insan operator)
**Dil:** Sənədlər və commit mesajları Azərbaycanca; kod İngilis; istisna: bəzi domain termin-lər (Azərbaycanca: vardiya, çek)

---

## SƏNƏD ARDICILLIĞI (hər sessiya başında oxu)

Layihədə yalnız **4 fayl** mövcuddur (bütün referans məzmun vahid sənəddə birləşdirildi):

1. **Bu fayl (CLAUDE.md)** — qaydalar
2. **STATUS.md** — cari vəziyyət, cari task, son commit, açıq suallar
3. **AI-ROADMAP.md** — vahid istinad (v4.0, hub modeli; yalnız cari faza bölməsini oxu)
4. **HUMAN-GATES.md** — gate vəziyyəti, açıq suallar

**Heç bir başqa top-level `.md` sənəd yoxdur** (istisna: `docs/adr/NNNN-*.md` — ADR-lər) — köhnə referans sənədlərin texniki dəyəri AI-ROADMAP.md v4.0-a inteqra olundu. Əgər başqa top-level `*.md` görsən, soruşmadan yaratma.

---

## STACK (LOCKED — dəyişmə ADR olmadan)

- Python 3.12 + FastAPI 0.110+
- PostgreSQL 16+ (RLS + pgmq + JSONB)
- Redis 7+
- Keycloak 25.x (OIDC)
- HashiCorp Vault 1.15+ (lokal dev mode; prod: real)
- Pydantic v2.6+
- SQLAlchemy 2.0+ + Alembic
- pytest + pytest-asyncio + testcontainers
- mypy --strict
- ruff + black
- bandit + detect-secrets + pip-audit
- Docker + docker-compose (lokal); K8s + Helm (cloud, Faza AI-7)
- OpenTelemetry + Prometheus + Grafana + Jaeger + Loki
- Flutter 3.24+ (POS app, Faza AI-2)
- Next.js 15 (admin + storefront, Faza AI-2/AI-5)

---

## QAYDALAR (məcburi)

### Sirr-lər
- **HEÇ VAXT** sirr kodda, log-da, commit-də yazma
- `.env.example` boş placeholder-lərlə commit, `.env` `.gitignore`-da
- Hər sirr Vault-da. Kod yalnız ref istifadə edir: `vault://secret/posnet/db/password`
- Yeni sirr lazımdır → STATUS.md-də qeyd → HUMAN-GATES.md sual → insan Vault-a yazır → AI ref istifadə edir
- `detect-secrets` pre-commit hook məcburi — keçməyən commit qadağan

### Commit qaydası
- Conventional Commits: `feat(scope): description`, `fix(scope): description`, `chore`, `docs`, `refactor`, `test`
- Hər task üçün 1+ commit (atomik)
- Commit mesajı Azərbaycanca, qısa (50 char baş, sonra blank line, sonra detal)
- Co-author trailer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

### Test qaydası
- **TDD:** Acceptance test ƏVVƏL yaz, implementasiya sonra
- Coverage gate: 80% minimum (CI fail əgər aşağı); kritik path-lər (auth, RLS, payment, fiscal): 95%
- Yeni endpoint → integration test məcburi (real DB ilə testcontainers)
- Mock-ları yalnız unit test-də; integration-da real bağımlılıq

### Kod qaydası
- `make verify` hər commit-dən əvvəl
- Type-hint hər funksiyada (mypy --strict)
- Pydantic v2 (BaseModel + ConfigDict)
- FastAPI: dependency injection, async, OpenAPI auto-generate
- SQLAlchemy 2 (declarative; `Mapped[T]` syntax)
- Domain layer pure Python (infrastructure-free, asanlıqla test edilə bilən)
- Comment-lər: yalnız "niyə", "nə" deyil. Default: heç bir comment.

### Sənəd qaydası
- ADR yarat hər texniki qərar üçün (`docs/adr/NNNN-decision.md`)
- Yeni endpoint → OpenAPI auto-generate (FastAPI edir)
- Yeni event → AsyncAPI spec-ə əlavə (`docs/asyncapi/`)

---

## TASK İCRA DÖVRÜ

```
1. STATUS.md oxu → cari task-ı tap
2. AI-ROADMAP.md-də cari faza bölməsini oxu (bütün məlumat orada)
3. Mövcud kodu axtar (Glob/Grep) — dublikat yaratma
4. Acceptance test-i ƏVVƏL yaz (TDD)
5. İmplementasiya
6. `make verify` — keçməsə fix, 3 cəhd, sonra STOP
7. Self-review checklist (aşağıda)
8. `git add . && git commit -m "..."`
9. STATUS.md yenilə
10. Növbəti task və ya Gate-də DAYAN
```

### Self-review checklist (commit-dən əvvəl)
- [ ] `make verify` keçdi
- [ ] `detect-secrets scan` keçdi
- [ ] Ölü kod silindi
- [ ] Test mock-u prod-a sızmadı
- [ ] Type-hint hər funksiyada
- [ ] OpenAPI schema yenidir
- [ ] Yeni env var `.env.example`-da
- [ ] Yeni dep `pyproject.toml`-da pin-li
- [ ] Yeni texniki qərar ADR-da

---

## HUMAN GATE DAVRANIŞI

AI bu hallarda **MÜTLƏQ DAYANIR**:

1. **Task `requires_human: true` qeydi** (kart, credential, partner, fiskal)
2. **3 cəhddən sonra test hələ fail-dir** (loop detection)
3. **Yeni external dep seçimi lazım** (məsələn "hansı PSP?")
4. **Faza Gate-inə çatıldı** (G0-G8)
5. **Sirr yaradılması lazım** (Vault-a yazılmalıdır)

Davranış:
1. `STATUS.md`-də `BLOCKED: <səbəb>` yaz
2. `HUMAN-GATES.md`-də Q-NNN giriş yarat (səbəb, variantlar, tövsiyə)
3. Sessiyanı bitir, insan cavabını gözlə

---

## NƏ EDƏ BİLMƏRƏM (insan üçün)

- Cloud account yarada bilmərəm (kart lazımdır)
- Domain ala bilmərəm
- Partner sandbox müraciəti edə bilmərəm
- Fiskal cihaz ala bilmərəm
- Müqavilə imzalaya bilmərəm
- Vault-a sirr yaza bilmərəm (yalnız insan)
- Production-a deploy edə bilmərəm (G8 icazəsi olmadan)
- `git push --force` etmərəm (`--no-verify` istifadə etmərəm)
- Faza Gate-ni keçmərəm öz başıma

---

## NƏ EDİRƏM (mənim icra sahəm)

- Kod yazma + test yazma + refactor
- DB schema + migration
- API endpoint + middleware
- Docker compose + Dockerfile
- Terraform + Helm chart (plan-only, apply yox)
- ADR + OpenAPI/AsyncAPI sənəd
- CI/CD workflow
- Smoke + load test
- Performance optimization
- Security scan + fix

---

## KOMANDA CHEATSHEET

```bash
make bootstrap          # İlk dəfə setup
make up / down          # Docker stack
make verify             # lint + type + test + security + coverage
make test PATTERN=foo   # selektiv test
make migrate            # Alembic
make smoke              # cari faza üçün smoke
```

---

## SESSIYA SONU CHECKLIST

Sessiyanı bitirmədən əvvəl:
- [ ] Bütün dəyişikliklər commit-lənib
- [ ] `STATUS.md` yenidir (cari task, son commit, açıq suallar)
- [ ] `HUMAN-GATES.md` yenidir (əgər yeni sual açıldısa)
- [ ] Memory yenildi (mühüm qərar/öyrəndiyimiz şey varsa)
- [ ] Əgər kontekst doldu və faza bitmədi: `HANDOFF.md` yaz (cari progress, açıq fayllar, açıq suallar)

---

## VERSİYA

**CLAUDE.md versiyası:** 1.2 (POS-anchored inteqrasiya hub modelinə uyğunlaşdırılıb — ADR-0012)
**Tarix:** 1 İyun 2026
**Dəyişiklik:** Yalnız ADR + insan icazəsi ilə
