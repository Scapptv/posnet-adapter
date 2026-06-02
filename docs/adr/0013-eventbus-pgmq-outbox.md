# ADR-0013 — EventBus: pgmq üzərində transactional outbox (hub onurğası)

**Status:** ACCEPTED
**Tarix:** 2026-06-02
**Qəbul edən:** AI sessiya (Faza AI-1.14)
**Əlaqəli:** ADR-0012 (`libs/eventbus` = hub onurğası), ADR-0001 (Stack: pgmq LOCKED),
AI-ROADMAP.md §15 (AI-1.14), STACK LOCKED #5/#12

## Kontekst

Hub-ın etibarlılığı 1-ci gündən tələb olunur (ADR-0012 crown jewel: idempotency +
reconciliation, anti-oversell). `libs/eventbus` domain hadisələrini POS ↔ kanal
adapterləri arasında daşıyan onurğadır. Lazımdır: (1) biznes yazısı ilə **atomik**
hadisə emissiyası (dual-write problemi olmadan), (2) at-least-once çatdırılma,
(3) retry/backoff, (4) zəhərli mesaj üçün DLQ, (5) broker-swap sərhədi (LOCKED #12:
Kafka yalnız sübut olunmuş darboğazda).

`outbox_events` cədvəli artıq var (migration 0001); pgmq extension dev stack-də
(init.sql) və testcontainers image-də mövcuddur. `tembo-pgmq-python` LOCKED dep-dir.

## Variantlar

1. **tembo async client (öz asyncpg pool-u)** — hazır API; amma pgmq əməliyyatları
   SQLAlchemy tranzaksiyasından AYRI pool-da gedir → relay "pgmq.send + outbox mark
   published" addımını atomik edə bilmir (publish-sonra-crash → dublikat). mypy --strict
   üçün də 3rd-party typing problemi.
2. **pgmq-ni SQLAlchemy üzərindən çağırmaq (ümumi pool)** — pgmq queue cədvəlləri
   eyni Postgres-dədir; relay bir lokal tranzaksiyada həm `pgmq.send`, həm də
   `UPDATE outbox SET published` edir → **genuine atomik, dual-write pəncərəsi yox.**
   Nazik öz SQL wrapper-i (`pgmq.py`) yazılır; mypy-clean.

## Qərar

**Variant 2.** pgmq SQLAlchemy `text()` (bound param) ilə çağırılır; bütün pgmq SQL
`libs/eventbus/pgmq.py`-də izolyasiyalıdır (broker-swap sərhədi). Komponentlər:

- **`enqueue(session, event)`** — transactional outbox: çağıranın öz tranzaksiyasında
  `outbox_events`-ə yazır (commit etmir). Hadisə biznes yazısı ilə atomik.
- **`OutboxRelay`** — bir tranzaksiyada `SELECT ... FOR UPDATE SKIP LOCKED` (paralel
  relay-lər üçün) → hər sətir `pgmq.send` → `UPDATE published=true`. Atomik publish.
- **`Consumer`** — 3 tranzaksiya: (A) `read` (vt + read_ct commit olunur, ona görə
  poison mesaj read_ct=1-də ilişmir), (B) handler + `archive` **bir tranzaksiyada**
  (uğur atomikdir), (C) uğursuzluqda ayrıca tranzaksiya: `read_ct >= max_retries`
  isə DLQ-ya (`send` + `archive`), əks halda eksponensial backoff (`set_vt`).
  Handler-dən əvvəl `SET LOCAL app.current_tenant` (RLS handler yazılarını event
  tenant-inə bağlayır).

**`tembo-pgmq-python` saxlanılır** (LOCKED dep), amma eventbus istifadə etmir —
gələcək CLI/admin tooling üçün qala bilər; pgmq broker qərarı dəyişmir.

## Nəticələr

### Müsbət

- **Atomik relay** — pgmq eyni DB-də olduğundan publish + mark bir lokal tranzaksiyadır
  (exactly-once relay; dual-write problemi tamamilə yox). pgmq seçiminin əsl faydası.
- Outbox = broker-agnostik, davamlı hadisə jurnalı (audit/replay/reconciliation üçün);
  Kafka swap yalnız relay/consumer-ə toxunur, domain kod `enqueue`-da qalır.
- `enqueue` RLS `WITH CHECK` altında işləyir → tenant başqa tenant üçün enqueue edə
  bilməz (defense-in-depth).
- `FOR UPDATE SKIP LOCKED` → relay horizontal miqyaslanır.

### Mənfi / qalıq risk

- **Relay/consumer cross-tenant background prosesdir** → DB rolu `outbox_events`
  üzərindəki per-tenant RLS-i bypass etməlidir (cədvəl sahibi və ya `BYPASSRLS` rol).
  Per-request `enqueue` isə tenant-scoped `posnet_app` rolunda qalır. **Rol wiring
  AI-1.9/AI-1.11-də** (app DB rol konfiqi); testlərdə container superuser (sahib,
  RLS FORCE deyil) bunu təmin edir.
- **At-least-once çatdırılma** — handler commit ilə növbəti read arasında crash →
  redelivery. Handler-lər `event.event_id`-ə görə idempotent olmalıdır (external
  effektli adapterlər üçün `idempotency_keys`).
- **`visibility_timeout` handler müddətini aşmalıdır**, yoxsa eyni mesaj paralel
  oxunar (default 30s).
- Hələlik tək queue + tək DLQ (`posnet_events`). Per-kanal routing AI-2.5-də.
- `tembo-pgmq-python` istifadəolunmayan dep kimi qalır (kiçik borc; LOCKED, ona görə
  ADR olmadan çıxarılmır).

## Əlaqəli

- `libs/eventbus/` (event, outbox, relay, consumer, pgmq, config)
- `docs/asyncapi/posnet-events.yaml` (hadisə envelope + kanal kontraktı)
- AI-ROADMAP.md §15 AI-1.14; G1 acceptance: pgmq publish→consume→DLQ
