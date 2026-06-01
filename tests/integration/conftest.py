"""Integration fixtures — real Postgres + Redis via testcontainers.

Postgres uses the same pgmq image as the dev stack (pgmq + pg_trgm).
These fixtures are consumed by AI-1.5+ tests (DB models, RLS, eventbus).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

PGMQ_IMAGE = "ghcr.io/pgmq/pg16-pgmq:latest"


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        PGMQ_IMAGE,
        username="posnet",
        password="posnet_test",  # pragma: allowlist secret
        dbname="posnet_test",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as rc:
        yield rc


@pytest.fixture(scope="session")
def pg_dsn(postgres_container: PostgresContainer) -> str:
    """libpq DSN (without the sqlalchemy driver prefix)."""
    url = postgres_container.get_connection_url()
    return url.replace("+psycopg2", "").replace("+psycopg", "")


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"
