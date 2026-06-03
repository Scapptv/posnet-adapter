"""AI-1.18 — backup helpers: pg_dump command, filename, retention (unit, no IO)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from services.core.app.backup import backup_filename, pg_dump_command, select_expired


@pytest.mark.unit
def test_backup_filename_is_timestamped_utc() -> None:
    when = datetime(2026, 6, 3, 15, 23, 44, tzinfo=UTC)
    assert backup_filename(when) == "posnet_20260603T152344Z.dump"


@pytest.mark.unit
def test_pg_dump_command_full_dsn() -> None:
    output = Path("/b/out.dump")
    args, env = pg_dump_command("postgresql+psycopg://posnet:s3cret@db:5432/posnet_core", output)
    assert args[0] == "pg_dump"
    assert "--format=custom" in args
    assert args[args.index("--host") + 1] == "db"
    assert args[args.index("--port") + 1] == "5432"
    assert args[args.index("--username") + 1] == "posnet"
    assert args[args.index("--dbname") + 1] == "posnet_core"
    assert args[args.index("--file") + 1] == str(output)  # OS-native separators
    assert env == {"PGPASSWORD": "s3cret"}  # pragma: allowlist secret


@pytest.mark.unit
def test_pg_dump_command_minimal_dsn_omits_absent_parts() -> None:
    # No host/port/user/password/dbname — every optional flag is skipped and the
    # env carries no password.
    args, env = pg_dump_command("postgresql+psycopg://", Path("out.dump"))
    assert "--host" not in args
    assert "--port" not in args
    assert "--username" not in args
    assert "--dbname" not in args
    assert env == {}


@pytest.mark.unit
def test_select_expired_returns_only_old_files() -> None:
    now = datetime(2026, 6, 10, tzinfo=UTC)
    fresh = (Path("fresh.dump"), now - timedelta(days=2))
    old = (Path("old.dump"), now - timedelta(days=30))
    assert select_expired([fresh, old], now=now, max_age_days=7) == [Path("old.dump")]


@pytest.mark.unit
def test_select_expired_disabled_when_non_positive() -> None:
    now = datetime(2026, 6, 10, tzinfo=UTC)
    old = (Path("old.dump"), now - timedelta(days=365))
    assert select_expired([old], now=now, max_age_days=0) == []
