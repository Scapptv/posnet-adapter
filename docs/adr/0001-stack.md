# ADR-0001 — Texnoloji Stack

**Status:** ACCEPTED
**Tarix:** 2026-06-01 (retroaktiv sənədləşdirmə — qərar layihə başında verilib)
**Qəbul edən:** İnsan operator + AI
**Əlaqəli:** ADR-0002 (monorepo), ADR-0003 (secrets), AI-ROADMAP.md §7

## Kontekst

Multi-tenant POS-anchored inteqrasiya hub üçün stack. Tələblər: pulun dəqiqliyi,
multi-tenant izolasiya, event-driven inteqrasiya (sync engine), güclü tip təhlükəsizliyi,
lokal-first dev.

## Qərar

- **Backend:** Python 3.12 + FastAPI — async, OpenAPI auto, Pydantic v2
- **DB:** PostgreSQL 16 + RLS (tenant izolasiya) + pgmq (event queue) + JSONB
- **Cache:** Redis 7 (JWKS cache, rate limit)
- **Auth:** Keycloak 25 (OIDC + RBAC + MFA)
- **Secrets:** HashiCorp Vault (ADR-0003)
- **Adapter resilience:** httpx + tenacity + pybreaker
- **Frontend:** TypeScript + React (admin-web); Flutter (kassir, sonra)
- **Observability:** OpenTelemetry + Prometheus + Grafana + Jaeger + Loki

LOCKED — dəyişiklik yeni ADR tələb edir (AI-ROADMAP.md §4).

## Nəticələr

### Müsbət
- Vahid Python backend ekosistemi; güclü tooling (mypy --strict, ruff)
- pgmq = Postgres-native queue → erkən Kafka mürəkkəbliyindən qaçınma (darboğazda keç)

### Mənfi / qalıq risk
- Python performansı Go/Rust-dan aşağı — qəbul edilir; darboğazda profil + optimallaşdırma

## Əlaqəli
- ADR-0002, ADR-0003, ADR-0012 (hub reframe), AI-ROADMAP.md §7
