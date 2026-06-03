"""Backup helpers (AI-1.18) — pure logic behind ``scripts/db_backup.py``.

The orchestration (running ``pg_dump``, uploading, deleting files) lives in the
script; the parts worth testing — turning the DSN into a ``pg_dump`` invocation,
naming the artifact, and picking expired files — live here as pure functions.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.engine import make_url


def backup_filename(when: datetime, *, prefix: str = "posnet", suffix: str = ".dump") -> str:
    """A sortable, UTC, timestamped artifact name, e.g. ``posnet_20260603T152344Z.dump``."""
    return f"{prefix}_{when.strftime('%Y%m%dT%H%M%SZ')}{suffix}"


def pg_dump_command(
    database_url: str, output: Path, *, pg_dump: str = "pg_dump"
) -> tuple[list[str], dict[str, str]]:
    """Build the ``pg_dump`` argv + extra env (PGPASSWORD) for ``database_url``.

    Custom format (compressed, restorable with ``pg_restore``); owner/privilege
    statements are dropped so a dump restores cleanly into any role. The password
    is passed via the environment, never on the command line.
    """
    url = make_url(database_url)
    args = [pg_dump, "--format=custom", "--no-owner", "--no-privileges", "--file", str(output)]
    if url.host:
        args += ["--host", url.host]
    if url.port:
        args += ["--port", str(url.port)]
    if url.username:
        args += ["--username", url.username]
    if url.database:
        args += ["--dbname", url.database]

    env: dict[str, str] = {}
    if url.password:
        env["PGPASSWORD"] = url.password
    return args, env


def select_expired(
    entries: Iterable[tuple[Path, datetime]], *, now: datetime, max_age_days: int
) -> list[Path]:
    """The paths whose modified time is older than ``max_age_days`` before ``now``.

    ``max_age_days <= 0`` disables retention (keep everything).
    """
    if max_age_days <= 0:
        return []
    cutoff = now - timedelta(days=max_age_days)
    return [path for path, modified in entries if modified < cutoff]
