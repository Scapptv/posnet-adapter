# Posnet

**POS-anchored omnichannel İnteqrasiya Hub**

Sahibkar fiziki mağazasını Posnet POS-da idarə edir və **bir paneldən** məhsullarını
marketplace (Birmarket/Trendyol), delivery (Wolt/Bolt) və booking portallarına çıxarır —
stok/qiymət hər kanalda avtomatik sinxron, bütün sifarişlər vahid panelə düşür.

Multi-tenant SaaS · modular monolit · event-driven · adapter-first. Azərbaycan → Türkiyə → Qlobal.

> **Model:** TSoft / Entegra / ChannelEngine tipli inteqrasiya hub-ı + POS lövbər.
> Adapterlər periferik deyil — məhsulun nüvəsi.

---

## Status

**Mərhələ:** Faza AI-0 (Bootstrap) — icrada (2/11)
**Versiya:** 0.1.0a0
**İcra modeli:** AI-autonomous (Claude Opus)
**Strateji:** ADR-0012 (hub reframe). Beachhead: **AZ · pərakəndə × Birmarket marketplace**.
**Aktiv yol:** AI-0 → AI-1 → AI-2 → **AI-2.5 (adapter framework)** → **G-V validasiya**.

Tam plan üçün [AI-ROADMAP.md](AI-ROADMAP.md) (v4.0, hub modeli).

---

## MVP dilimi (sübut hədəfi)

```
POS-da məhsul → Birmarket-ə listing → stok/qiymət sync → sifariş POS-a → stok hər yerdə azalır
```

Bu uçtan-uca dilim bütün məhsul tezisini sübut edir → sonra retail satıcılara demo (G-V validasiya).

---

## Sənəd hierarxiyası

| Fayl | Rolu |
|---|---|
| [AI-ROADMAP.md](AI-ROADMAP.md) | Vahid texniki istinad (v4.0) — hub modeli, aktiv faza task-ları, schema, adapter dizaynı, NFR, risk |
| [CLAUDE.md](CLAUDE.md) | Claude sessiya qaydaları (auto-load) |
| [STATUS.md](STATUS.md) | Cari vəziyyət (hər task AI yeniləyir) |
| [HUMAN-GATES.md](HUMAN-GATES.md) | İnsan ↔ AI dialoq jurnalı + gate keçidləri |
| [docs/adr/](docs/adr/) | Architecture Decision Records (0010–0012) |

---

## Quickstart (Faza AI-0 tamamlandıqdan sonra)

```bash
make bootstrap          # docker stack qaldır + verify
make verify             # lint + type + test + security
make test               # yalnız pytest
make help               # bütün əmrlər
```

---

## Stack (LOCKED)

Python 3.12 + FastAPI · PostgreSQL 16 (RLS + pgmq) · Redis 7 · Keycloak 25 (OIDC) · Vault ·
Pydantic v2 · SQLAlchemy 2 · httpx / tenacity / pybreaker (adapter) · Flutter 3.24 (kassir) ·
React (admin) · Docker · OTel + Prometheus + Grafana + Jaeger + Loki.

Tam stack: [AI-ROADMAP.md](AI-ROADMAP.md) — PART II.

---

## Lisenziya

TBD — kommersiya SaaS olduğu üçün proprietary / source-available nəzərdən keçirilir (ADR ilə dəqiqləşəcək).
