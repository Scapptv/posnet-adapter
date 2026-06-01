"""AI-1.1 — testcontainers infra sanity (pgmq + redis, real containers)."""

from __future__ import annotations

import psycopg
import pytest
import redis


@pytest.mark.integration
def test_postgres_pgmq(pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgmq")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'pgmq'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "pgmq"


@pytest.mark.integration
def test_redis_ping(redis_url: str) -> None:
    client = redis.from_url(redis_url)
    assert client.ping() is True
