"""Integration fixtures — real Postgres + Redis via testcontainers.

Postgres uses the same pgmq image as the dev stack (pgmq + pg_trgm).
These fixtures are consumed by AI-1.5+ tests (DB models, RLS, eventbus).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from testcontainers.vault import VaultContainer

from libs.vault import VaultConfig

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
def vault_container() -> Iterator[VaultContainer]:
    # Dev mode: KV-v2 is mounted at ``secret/`` out of the box.
    with VaultContainer("hashicorp/vault:1.15") as vc:
        yield vc


@pytest.fixture
def vault_config(vault_container: VaultContainer) -> VaultConfig:
    return VaultConfig(addr=vault_container.get_connection_url(), token=vault_container.root_token)


@pytest.fixture(scope="session")
def pg_dsn(postgres_container: PostgresContainer) -> str:
    """libpq DSN (without the sqlalchemy driver prefix)."""
    url = postgres_container.get_connection_url()
    return url.replace("+psycopg2", "").replace("+psycopg", "")


@pytest.fixture(scope="session")
def pg_sqlalchemy_url(postgres_container: PostgresContainer) -> str:
    """SQLAlchemy / psycopg3 URL (postgresql+psycopg://...) for engine and alembic."""
    return postgres_container.get_connection_url().replace("+psycopg2", "+psycopg")


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def migrated_db(pg_sqlalchemy_url: str) -> None:
    """Bring the shared container to ``head`` once (identity + RLS schema)."""
    cfg = Config()
    cfg.set_main_option("script_location", "services/core/alembic")
    cfg.set_main_option("sqlalchemy.url", pg_sqlalchemy_url)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def async_engine(pg_sqlalchemy_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(pg_sqlalchemy_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def async_session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False)
