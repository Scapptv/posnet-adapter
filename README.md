# Posnet

**Qlobal Multi-POS və Çoxkanallı İnteqrasiya Platforması**

Multi-tenant SaaS, modular monolit, event-driven. Azərbaycan → Türkiyə → Qlobal.

---

## Status

**Mərhələ:** Faza AI-0 (Bootstrap) — icrada
**Versiya:** 0.1.0a0
**İcra modeli:** AI-autonomous (Claude Opus)

Tam plan üçün [AI-ROADMAP.md](AI-ROADMAP.md) (vahid 46-bölməli istinad).

---

## Sənəd hierarxiyası

| Fayl | Rolu |
|---|---|
| [AI-ROADMAP.md](AI-ROADMAP.md) | Vahid texniki istinad — bütün faza task-ları, SQL DDL, API kontraktları, NFR, risk, KPI |
| [CLAUDE.md](CLAUDE.md) | Claude sessiya qaydaları (auto-load) |
| [STATUS.md](STATUS.md) | Cari vəziyyət (hər task AI yeniləyir) |
| [HUMAN-GATES.md](HUMAN-GATES.md) | İnsan ↔ AI dialoq jurnalı + gate keçidləri |

**Heç bir başqa `.md` referans sənəd yoxdur** — bütün məzmun yuxarıdakı 4 faylda.

---

## Quickstart (Faza AI-0 tamamlandıqdan sonra)

```bash
make bootstrap          # docker stack qaldır + verify
make verify             # lint + type + test + security + coverage 80%+
make test               # yalnız pytest
make smoke              # cari faza üçün smoke test
make load               # k6 (Faza AI-4+)
```

Tam komanda siyahısı: [AI-ROADMAP.md §32](AI-ROADMAP.md).

---

## Stack (LOCKED)

Python 3.12 + FastAPI · PostgreSQL 16 (RLS + pgmq) · Redis 7 · Keycloak 25 · Vault · Flutter 3.24 · Next.js 15 · Docker / K8s · OTel + Prometheus + Grafana + Jaeger + Loki.

Tam stack: [AI-ROADMAP.md §7](AI-ROADMAP.md).

---

## Lisenziya

Apache 2.0 (sonra dəqiqləşdiriləcək).
