"""Back up the core Postgres DB with ``pg_dump`` (custom format). Run via ``make backup``.

Writes a timestamped dump under ``BACKUP_DIR`` (default ``backups/``), then — only
when ``S3_BUCKET_BACKUPS`` is set and the ``aws`` CLI is available — uploads it to
S3/MinIO (MinIO is S3-compatible via ``S3_ENDPOINT``). Local dumps older than
``BACKUP_RETENTION_DAYS`` (default 7) are pruned. The DB DSN is ``DATABASE_URL``
(same as the app); the password is passed to ``pg_dump`` via the environment.

The testable logic (DSN -> argv, filename, retention) lives in
``services.core.app.backup``; this is the IO orchestration around it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from services.core.app.backup import backup_filename, pg_dump_command, select_expired
from services.core.app.config import get_settings


def _run() -> None:
    settings = get_settings()
    backup_dir = Path(os.getenv("BACKUP_DIR", "backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    output = backup_dir / backup_filename(now)

    args, env_overrides = pg_dump_command(settings.database_url, output)
    print(f"pg_dump -> {output}")
    subprocess.run(args, env={**os.environ, **env_overrides}, check=True)  # noqa: S603

    _maybe_upload(output)
    _prune(backup_dir, now)
    print("backup done")


def _maybe_upload(output: Path) -> None:
    bucket = os.getenv("S3_BUCKET_BACKUPS")
    if not bucket:
        print("S3_BUCKET_BACKUPS unset -> keeping local backup only")
        return
    aws = shutil.which("aws")
    if aws is None:
        print("aws CLI not found -> skipping S3 upload")
        return
    cmd = [aws, "s3", "cp", str(output), f"s3://{bucket}/{output.name}"]
    endpoint = os.getenv("S3_ENDPOINT")
    if endpoint:
        cmd += ["--endpoint-url", endpoint]
    subprocess.run(cmd, check=True)  # noqa: S603
    print(f"uploaded -> s3://{bucket}/{output.name}")


def _prune(backup_dir: Path, now: datetime) -> None:
    retention = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
    entries = [
        (path, datetime.fromtimestamp(path.stat().st_mtime, UTC))
        for path in backup_dir.glob("posnet_*.dump")
    ]
    for path in select_expired(entries, now=now, max_age_days=retention):
        path.unlink()
        print(f"pruned old backup {path.name}")


if __name__ == "__main__":
    _run()
