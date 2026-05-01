"""In-container scheduler for Hotpot periodic jobs.

This is the Docker-native replacement for host crontab. It runs inside the
backend image, talks to Postgres/Redis/Qdrant by compose service name, and
executes the same ``hotpot`` CLI commands without needing the Docker socket.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


Schedule = Callable[[datetime], bool]


@dataclass(frozen=True)
class Job:
    name: str
    schedule: Schedule
    command: tuple[str, ...] | None = None
    lock_group: str | None = None
    description: str = ""
    backup: bool = False


LOG_DIR = Path(os.getenv("HOTPOT_SCHEDULER_LOG_DIR", "/app/logs"))
BACKUP_DIR = Path(os.getenv("HOTPOT_BACKUP_DIR", "/app/backups"))

WORKERS = os.getenv("WORKERS", "4")
FULL_WORKERS = os.getenv("FULL_WORKERS", "8")
SOURCE_WORKERS = os.getenv("SOURCE_WORKERS", "1")
SECURITY_LIMIT = os.getenv("SECURITY_LIMIT", "5000")
SECURITY_RECENT_DAYS = os.getenv("SECURITY_RECENT_DAYS", "120")

_state_lock = threading.Lock()
_running_locks: set[str] = set()
_last_slots: dict[str, str] = {}


def every_hour_at(minute: int) -> Schedule:
    return lambda dt: dt.minute == minute


def every_n_hours_at(hours: int, minute: int) -> Schedule:
    return lambda dt: dt.minute == minute and dt.hour % hours == 0


def every_30_minutes(dt: datetime) -> bool:
    return dt.minute in (0, 30)


def daily_at(hour: int, minute: int) -> Schedule:
    return lambda dt: dt.hour == hour and dt.minute == minute


JOBS: list[Job] = [
    Job(
        name="ingest-html",
        schedule=every_hour_at(10),
        command=("hotpot", "ingest-kind", "html", "--workers", WORKERS),
        lock_group="ingest",
        description="Poll HTML index/sitemap sources; RSS-like path for sites without feeds.",
    ),
    Job(
        name="ingest-rss",
        schedule=every_n_hours_at(2, 20),
        command=("hotpot", "ingest-kind", "rss", "--workers", WORKERS),
        lock_group="ingest",
        description="Pull RSS/Atom sources.",
    ),
    Job(
        name="ingest-arxiv",
        schedule=every_n_hours_at(6, 0),
        command=("hotpot", "ingest-kind", "arxiv", "--workers", WORKERS),
        lock_group="ingest",
        description="Pull arXiv category sources.",
    ),
    Job(
        name="ingest-now",
        schedule=daily_at(2, 0),
        command=(
            "hotpot",
            "ingest-now",
            "--workers",
            FULL_WORKERS,
            "--source-workers",
            SOURCE_WORKERS,
        ),
        lock_group="ingest",
        description="Daily full active-source backstop.",
    ),
    Job(
        name="ingest-empty",
        schedule=every_30_minutes,
        command=("hotpot", "ingest-empty"),
        lock_group="ingest",
        description="Fast pass over sources that still have zero items.",
    ),
    Job(
        name="health-check-sources",
        schedule=every_hour_at(15),
        command=("hotpot", "health-check-sources"),
        lock_group="health-check-sources",
        description="HEAD active source URLs and update health status.",
    ),
    Job(
        name="score-sources",
        schedule=daily_at(3, 0),
        command=("hotpot", "score-sources"),
        lock_group="score-sources",
        description="Re-score source trust from click data and LLM noise sample.",
    ),
    Job(
        name="score-security",
        schedule=daily_at(3, 10),
        command=(
            "hotpot",
            "score-security",
            "--limit",
            SECURITY_LIMIT,
            "--recent-days",
            SECURITY_RECENT_DAYS,
        ),
        lock_group="score-security",
        description="Refresh the dedicated /security score projection.",
    ),
    Job(
        name="backup-db",
        schedule=daily_at(3, 30),
        lock_group="backup-db",
        description="Write a portable Postgres logical dump to /app/backups.",
        backup=True,
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Hotpot scheduled jobs inside Docker.")
    parser.add_argument("--list", action="store_true", help="Print configured jobs and exit.")
    parser.add_argument("--once", metavar="JOB", help="Run one job immediately and exit.")
    args = parser.parse_args()

    if args.list:
        print(json.dumps([describe_job(job) for job in JOBS], indent=2))
        return

    job_by_name = {job.name: job for job in JOBS}
    if args.once:
        job = job_by_name.get(args.once)
        if job is None:
            raise SystemExit(f"unknown job {args.once!r}; use --list")
        ok = run_job(job)
        raise SystemExit(0 if ok else 1)

    run_loop()


def describe_job(job: Job) -> dict[str, str]:
    return {
        "name": job.name,
        "lock_group": job.lock_group or job.name,
        "command": "backup-db" if job.backup else " ".join(job.command or ()),
        "description": job.description,
    }


def run_loop() -> None:
    tz_name = os.getenv("HOTPOT_SCHEDULER_TZ", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        print(f"unknown HOTPOT_SCHEDULER_TZ={tz_name!r}; falling back to UTC", flush=True)
        tz = UTC

    tick_seconds = int(os.getenv("HOTPOT_SCHEDULER_TICK_SECONDS", "30"))
    print(
        f"Hotpot scheduler started: tz={tz_name}, tick={tick_seconds}s, jobs={len(JOBS)}",
        flush=True,
    )
    for job in JOBS:
        print(f"  - {job.name}: {job.description}", flush=True)

    while True:
        now = datetime.now(tz).replace(second=0, microsecond=0)
        for job in JOBS:
            if not job.schedule(now):
                continue
            slot = now.isoformat()
            with _state_lock:
                if _last_slots.get(job.name) == slot:
                    continue
                _last_slots[job.name] = slot
            start_job_thread(job)
        time.sleep(max(5, tick_seconds))


def start_job_thread(job: Job) -> None:
    lock_name = job.lock_group or job.name
    with _state_lock:
        if lock_name in _running_locks:
            print(
                f"[{utc_now()}] skipped {job.name}: lock {lock_name!r} is already running",
                flush=True,
            )
            return
        _running_locks.add(lock_name)

    thread = threading.Thread(target=_run_and_release, args=(job, lock_name), daemon=True)
    thread.start()


def _run_and_release(job: Job, lock_name: str) -> None:
    try:
        run_job(job)
    finally:
        with _state_lock:
            _running_locks.discard(lock_name)


def run_job(job: Job) -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{job.name}.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        log_line(log_file, f"[{utc_now()}] start {job.name}")
        try:
            if job.backup:
                run_backup(log_file)
            else:
                if not job.command:
                    raise RuntimeError(f"job {job.name} has no command")
                stream_command(job.command, log_file)
        except Exception as exc:  # pragma: no cover - exercised in container
            log_line(log_file, f"[{utc_now()}] failed {job.name}: {exc}")
            return False
        log_line(log_file, f"[{utc_now()}] done {job.name}")
        return True


def run_backup(log_file) -> None:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        raise RuntimeError("pg_dump not found; rebuild the backend image with postgresql-client")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%SZ")
    archive = BACKUP_DIR / f"hotpot-db-{ts}.tar.gz"

    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "hotpot")
    user = os.getenv("POSTGRES_USER", "hotpot")
    password = os.getenv("POSTGRES_PASSWORD", "hotpot")

    with tempfile.TemporaryDirectory(prefix="hotpot-backup-") as tmp:
        tmp_path = Path(tmp)
        dump_path = tmp_path / "postgres.dump"
        env = os.environ.copy()
        env["PGPASSWORD"] = password
        stream_command(
            (
                pg_dump,
                "-h",
                host,
                "-p",
                str(port),
                "-U",
                user,
                "-d",
                db,
                "-Fc",
                "--no-owner",
                "--no-acl",
                "-f",
                str(dump_path),
            ),
            log_file,
            env=env,
        )
        manifest = {
            "created_at": ts,
            "backup_kind": "postgres-logical",
            "postgres_host": host,
            "postgres_port": port,
            "postgres_db": db,
            "postgres_user": user,
            "note": "Qdrant embeddings are not included; rebuild embeddings or use host full-volume backup if needed.",
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(dump_path, arcname="postgres.dump")
            tar.add(tmp_path / "manifest.json", arcname="manifest.json")
    log_line(log_file, f"backup archive: {archive}")


def stream_command(command: tuple[str, ...], log_file, env: dict[str, str] | None = None) -> None:
    log_line(log_file, "$ " + " ".join(command))
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log_line(log_file, line.rstrip("\n"))
    rc = proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, command)


def log_line(log_file, line: str) -> None:
    print(line, flush=True)
    log_file.write(line + "\n")
    log_file.flush()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
