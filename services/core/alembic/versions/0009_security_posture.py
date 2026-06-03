"""security posture: RLS FORCE + non-owner app login + tenant resolver (AI-2.H1)

Audit A1 fix (ADR-0017):
- ``posnet_app`` becomes a non-owner LOGIN role (NOSUPERUSER NOBYPASSRLS) so the
  app's per-request pool connects locked-down: a forgotten tenant scope yields
  zero rows (RLS), never a cross-tenant leak.
- FORCE row-level security on every RLS-enabled table (defence in depth — even a
  table owner is then subject to policies).
- ``posnet_resolve_tenant`` (SECURITY DEFINER, fixed search_path) performs the one
  inherently cross-tenant lookup (subject -> tenant) on behalf of the locked-down
  role, so the per-request flow needs no superuser connection.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-03
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "posnet_app"

# FORCE / un-FORCE every table that has RLS enabled (no hard-coded list, so new
# RLS tables are covered automatically).
_FORCE_ALL = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
      AND c.relrowsecurity AND NOT c.relforcerowsecurity
  LOOP
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', r.relname);
  END LOOP;
END $$;
"""

_UNFORCE_ALL = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relforcerowsecurity
  LOOP
    EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', r.relname);
  END LOOP;
END $$;
"""

_CREATE_RESOLVER = """
CREATE OR REPLACE FUNCTION posnet_resolve_tenant(p_subject text)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $func$
    SELECT tenant_id FROM public.users
    WHERE external_subject = p_subject AND status = 'active'
    LIMIT 1
$func$;
"""


def upgrade() -> None:
    # Non-owner login role; password from env, dev default for local/test (ADR-0014).
    password = os.environ.get("DATABASE_APP_PASSWORD", "posnet_app_dev_pw")  # pragma: allowlist secret
    op.execute(
        f"ALTER ROLE {APP_ROLE} WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB "
        f"NOCREATEROLE PASSWORD '{password.replace(chr(39), chr(39) * 2)}'"
    )
    op.execute(_FORCE_ALL)
    op.execute(_CREATE_RESOLVER)
    op.execute("REVOKE ALL ON FUNCTION posnet_resolve_tenant(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION posnet_resolve_tenant(text) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS posnet_resolve_tenant(text)")
    op.execute(_UNFORCE_ALL)
    op.execute(f"ALTER ROLE {APP_ROLE} WITH NOLOGIN PASSWORD NULL")
