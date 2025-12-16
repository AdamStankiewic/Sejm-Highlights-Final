from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from .models import UploadJob, UploadTarget


class UploadStore:
    def __init__(self, db_path: Path | str = Path("data/uploader.db")):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.init_db()

    def init_db(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS upload_jobs (
                    job_id TEXT PRIMARY KEY,
                    file_path TEXT,
                    title TEXT,
                    description TEXT,
                    created_at TEXT,
                    kind TEXT,
                    copyright_status TEXT,
                    original_path TEXT,
                    tags TEXT,
                    thumbnail_path TEXT
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS upload_targets (
                    target_id TEXT PRIMARY KEY,
                    job_id TEXT,
                    platform TEXT,
                    account_id TEXT,
                    scheduled_at TEXT,
                    mode TEXT,
                    state TEXT,
                    result_id TEXT,
                    fingerprint TEXT UNIQUE,
                    retry_count INTEGER,
                    next_retry_at TEXT,
                    last_error TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(job_id) REFERENCES upload_jobs(job_id)
                )
                """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_upload_targets_job_id ON upload_targets(job_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_upload_targets_state ON upload_targets(state)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_upload_targets_scheduled_at ON upload_targets(scheduled_at)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_upload_targets_next_retry_at ON upload_targets(next_retry_at)")
            self._ensure_column("upload_jobs", "tags", "TEXT")
            self._ensure_column("upload_jobs", "thumbnail_path", "TEXT")

    def _ensure_column(self, table: str, column: str, col_type: str):
        try:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            return

    def upsert_job(self, job: UploadJob):
        job_id = job.job_id or str(uuid.uuid4())
        job.job_id = job_id
        created_at = self._serialize_dt(job.created_at)
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO upload_jobs (job_id, file_path, title, description, created_at, kind, copyright_status, original_path, tags, thumbnail_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    file_path=excluded.file_path,
                    title=excluded.title,
                    description=excluded.description,
                    created_at=excluded.created_at,
                    kind=excluded.kind,
                    copyright_status=excluded.copyright_status,
                    original_path=excluded.original_path,
                    tags=excluded.tags,
                    thumbnail_path=excluded.thumbnail_path
                """,
                (
                    job_id,
                    job.file_path.as_posix(),
                    job.title,
                    job.description,
                    created_at,
                    job.kind,
                    job.copyright_status,
                    job.original_path.as_posix() if job.original_path else None,
                    json.dumps(job.tags or []),
                    job.thumbnail_path.as_posix() if job.thumbnail_path else None,
                ),
            )
        return job_id

    def upsert_target(self, job_id: str, target: UploadTarget):
        target_id = target.target_id or target.fingerprint or str(uuid.uuid4())
        target.target_id = target_id
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO upload_targets (
                    target_id, job_id, platform, account_id, scheduled_at, mode, state, result_id, fingerprint,
                    retry_count, next_retry_at, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_id) DO UPDATE SET
                    platform=excluded.platform,
                    account_id=excluded.account_id,
                    scheduled_at=excluded.scheduled_at,
                    mode=excluded.mode,
                    state=excluded.state,
                    result_id=excluded.result_id,
                    fingerprint=excluded.fingerprint,
                    retry_count=excluded.retry_count,
                    next_retry_at=excluded.next_retry_at,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (
                    target_id,
                    job_id,
                    target.platform,
                    target.account_id,
                    self._serialize_dt(target.scheduled_at),
                    target.mode,
                    target.state,
                    target.result_id,
                    target.fingerprint,
                    target.retry_count,
                    self._serialize_dt(target.next_retry_at),
                    target.last_error,
                    self._serialize_dt(datetime.now(tz=ZoneInfo("UTC"))),
                ),
            )
        return target_id

    def update_target_details(
        self,
        target_id: str,
        *,
        account_id: Optional[str] = None,
        scheduled_at: datetime | None = None,
        mode: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ):
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE upload_targets
                SET account_id=COALESCE(?, account_id),
                    scheduled_at=COALESCE(?, scheduled_at),
                    mode=COALESCE(?, mode),
                    fingerprint=COALESCE(?, fingerprint),
                    updated_at=?
                WHERE target_id=?
                """,
                (
                    account_id,
                    self._serialize_dt(scheduled_at),
                    mode,
                    fingerprint,
                    self._serialize_dt(datetime.now(tz=ZoneInfo("UTC"))),
                    target_id,
                ),
            )

    def update_target_state(
        self,
        target_id: str,
        state: str,
        *,
        result_id: Optional[str] = None,
        last_error: Optional[str] = None,
        retry_count: Optional[int] = None,
        next_retry_at: Optional[datetime] = None,
    ):
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE upload_targets
                SET state=?, result_id=COALESCE(?, result_id), last_error=?, retry_count=COALESCE(?, retry_count),
                    next_retry_at=?, updated_at=?
                WHERE target_id=?
                """,
                (
                    state,
                    result_id,
                    last_error,
                    retry_count,
                    self._serialize_dt(next_retry_at),
                    self._serialize_dt(datetime.now(tz=ZoneInfo("UTC"))),
                    target_id,
                ),
            )

    def load_jobs_with_targets(self) -> List[UploadJob]:
        jobs: dict[str, UploadJob] = {}
        with self._lock, self.conn:
            job_rows = self.conn.execute(
                "SELECT job_id, file_path, title, description, created_at, kind, copyright_status, original_path, tags, thumbnail_path FROM upload_jobs"
            ).fetchall()
            for row in job_rows:
                job = UploadJob(
                    job_id=row["job_id"],
                    file_path=Path(row["file_path"]),
                    title=row["title"],
                    description=row["description"],
                    targets=[],
                    created_at=self._parse_dt(row["created_at"]),
                    kind=row["kind"],
                    copyright_status=row["copyright_status"] or "pending",
                    original_path=Path(row["original_path"]) if row["original_path"] else None,
                    tags=json.loads(row["tags"]) if "tags" in row.keys() and row["tags"] else [],
                    thumbnail_path=(
                        Path(row["thumbnail_path"])
                        if "thumbnail_path" in row.keys() and row["thumbnail_path"]
                        else None
                    ),
                )
                jobs[job.job_id] = job

            target_rows = self.conn.execute(
                """
                SELECT target_id, job_id, platform, account_id, scheduled_at, mode, state, result_id, fingerprint,
                       retry_count, next_retry_at, last_error
                FROM upload_targets
                """
            ).fetchall()
            for row in target_rows:
                target = UploadTarget(
                    platform=row["platform"],
                    account_id=row["account_id"],
                    scheduled_at=self._parse_dt(row["scheduled_at"]),
                    mode=row["mode"],
                    state=row["state"],
                    result_id=row["result_id"],
                    retry_count=row["retry_count"] or 0,
                    next_retry_at=self._parse_dt(row["next_retry_at"]),
                    last_error=row["last_error"],
                    fingerprint=row["fingerprint"] or "",
                    target_id=row["target_id"],
                )
                job = jobs.get(row["job_id"])
                if job:
                    job.targets.append(target)
        return list(jobs.values())

    def _serialize_dt(self, value: datetime | None) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        return value.astimezone(ZoneInfo("UTC")).isoformat()

    def _parse_dt(self, value: str | None) -> Optional[datetime]:
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed

    def get_due_targets(self, now: datetime):
        with self._lock, self.conn:
            rows = self.conn.execute(
                """
                SELECT * FROM upload_targets
                WHERE (state='PENDING' AND scheduled_at <= ?) OR (state='FAILED' AND next_retry_at <= ?)
                """,
                (self._serialize_dt(now), self._serialize_dt(now)),
            ).fetchall()
        return rows
