-- Posnet core DB init (AI-0.3)
-- POSTGRES_DB (posnet_core) initdb tərəfindən yaradılır; bu skript ona qarşı işləyir.
-- pgmq image (ghcr.io/pgmq/pg16-pgmq) pgmq extension-ını təmin edir.

CREATE EXTENSION IF NOT EXISTS pgmq;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
