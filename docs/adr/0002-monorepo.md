# ADR-0002 — Monorepo Strukturu

**Status:** ACCEPTED
**Tarix:** 2026-06-01 (retroaktiv)
**Qəbul edən:** İnsan operator + AI
**Əlaqəli:** ADR-0001, ADR-0012, AI-ROADMAP.md §8

## Kontekst

Hub-da çoxlu komponent var: core POS, adapter servisləri, ortaq kitabxanalar, frontend-lər,
mock-lar, infra. Tək repo vs çox repo seçimi.

## Variantlar

1. **Monorepo** — hamısı bir repo
2. **Poly-repo** — hər servis/lib ayrı repo

## Qərar

**Monorepo (Variant 1).** Struktur: `services/` (core + adapter svc), `libs/`
(canonical_model, adapter, eventbus, auth, common...), `apps/` (admin-web, storefront,
pos-flutter), `mocks/`, `infra/`, `docs/`, `tests/`. Python paket adları snake_case;
servis qovluqları hyphen.

**Why:** atomik dəyişiklik (adapter kontraktı + canonical model birlikdə dəyişir),
ortaq tooling/CI, "yeni kanal = 1 adapter" axını üçün ideal. `libs/` = hub crown jewel (ADR-0012).

## Nəticələr

### Müsbət
- Vahid `make verify` / CI; ortaq versiya; asan cross-cutting refactor

### Mənfi / qalıq risk
- Repo böyüyür — qəbul edilir; lazım olsa gələcəkdə servis ayrıla bilər

## Əlaqəli
- ADR-0001, ADR-0012 (libs = hub nüvəsi), AI-ROADMAP.md §8
