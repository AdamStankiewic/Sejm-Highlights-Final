"""Upload manager with background queue."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Literal, Optional
from zoneinfo import ZoneInfo

from .youtube import upload_video
from .meta import upload_reel
from .tiktok import upload_tiktok

logger = logging.getLogger(__name__)


@dataclass
class UploadTarget:
    platform: str
    account_id: str
    scheduled_at: datetime | None = None
    mode: Literal["LOCAL_SCHEDULE", "NATIVE_SCHEDULE"] = "LOCAL_SCHEDULE"
    state: Literal["PENDING", "UPLOADING", "DONE", "FAILED"] = "PENDING"
    result_id: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[datetime] = None
    last_error: Optional[str] = None
    fingerprint: str = ""


@dataclass
class UploadJob:
    file_path: Path
    title: str
    description: str
    targets: List[UploadTarget]
    copyright_status: str = "pending"
    original_path: Path | None = None
    state: Literal["PENDING", "UPLOADING", "DONE", "FAILED"] = "PENDING"

    @property
    def aggregate_state(self) -> str:
        states = {target.state for target in self.targets}
        if not states:
            return self.state
        if "FAILED" in states and all(t.next_retry_at is None for t in self.targets):
            return "FAILED"
        if states == {"DONE"}:
            return "DONE"
        if "UPLOADING" in states:
            return "UPLOADING"
        return "PENDING"


def parse_scheduled_at(value: str | None, tz: str = "Europe/Warsaw") -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(tz))
    return parsed


class UploadManager:
    RETRY_BACKOFF_SECONDS = [60, 300, 1800]

    def __init__(self, protector=None, tick_seconds: float = 2.0, max_concurrent: int = 2):
        self.jobs: list[UploadJob] = []
        self.worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.callbacks: List[Callable[[str, UploadJob, UploadTarget | None], None]] = []
        self.protector = protector
        self.tick_seconds = tick_seconds
        self._semaphore = threading.Semaphore(max_concurrent)

    def add_callback(self, cb: Callable[[str, UploadJob, UploadTarget | None], None]):
        self.callbacks.append(cb)

    def enqueue(self, job: UploadJob):
        logger.info("Enqueue upload: %s", job.file_path)
        self._validate_job(job)
        self._compute_fingerprints(job)
        self.jobs.append(job)
        self._ensure_worker()

    def _ensure_worker(self):
        if self.worker and self.worker.is_alive():
            return
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def stop(self):
        self._stop_event.set()
        if self.worker:
            self.worker.join(timeout=1)

    def _worker_loop(self):
        while not self._stop_event.is_set():
            now = datetime.now(tz=ZoneInfo("UTC"))
            self._process_due_targets(now)
            self._stop_event.wait(self.tick_seconds)

    def _process_due_targets(self, now: datetime):
        for job in list(self.jobs):
            if job.original_path is None:
                job.original_path = job.file_path
            for target in job.targets:
                if self._should_skip_target(target):
                    continue
                if target.scheduled_at and target.scheduled_at.tzinfo is None:
                    raise ValueError("scheduled_at must be timezone-aware")
                if target.scheduled_at and target.scheduled_at < now and target.state == "PENDING":
                    logger.warning(
                        "Target scheduled in the past treated as due now: %s %s %s",
                        target.platform,
                        target.account_id,
                        target.scheduled_at,
                    )
                if self.is_target_due(target, now):
                    self._notify("target_due", job, target)
                    self._start_target(job, target)
            job.state = job.aggregate_state
            self._notify("job_update", job)

    def _start_target(self, job: UploadJob, target: UploadTarget):
        if not self._semaphore.acquire(blocking=False):
            return

        def runner():
            try:
                self._run_target(job, target)
            finally:
                self._semaphore.release()

        threading.Thread(target=runner, daemon=True).start()

    def _run_target(self, job: UploadJob, target: UploadTarget):
        if target.state == "UPLOADING":
            return
        if target.result_id and target.state in {"DONE", "PUBLISHED"}:
            logger.info("Skipping already completed target %s", target.fingerprint)
            return

        target.state = "UPLOADING"
        target.next_retry_at = None
        job.state = job.aggregate_state
        self._notify("target_state_changed", job, target)
        try:
            processed_job = self._apply_protections(job)
            schedule = self._resolve_schedule(target)
            target.result_id = self._dispatch_upload(processed_job, target, schedule)
            target.state = "DONE"
            target.last_error = None
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._handle_target_failure(job, target, exc)
        finally:
            job.state = job.aggregate_state
            self._notify("target_state_changed", job, target)

    def _handle_target_failure(self, job: UploadJob, target: UploadTarget, exc: Exception):
        target.last_error = str(exc)
        retryable = self._is_retryable_error(exc)
        if retryable and target.retry_count < len(self.RETRY_BACKOFF_SECONDS):
            delay = self.RETRY_BACKOFF_SECONDS[target.retry_count]
            target.retry_count += 1
            target.next_retry_at = datetime.now(tz=ZoneInfo("UTC")) + timedelta(seconds=delay)
            target.state = "FAILED"
            self._notify("target_retry_scheduled", job, target)
            logger.warning(
                "Retryable error for %s; scheduling retry #%s at %s", target.fingerprint, target.retry_count, target.next_retry_at
            )
        else:
            target.next_retry_at = None
            target.state = "FAILED"
            logger.error("Non-retryable error for %s: %s", target.fingerprint, exc)

    def _apply_protections(self, job: UploadJob) -> UploadJob:
        if job.original_path is None:
            job.original_path = job.file_path
        if not self.protector:
            return job
        fixed_path, status = self.protector.scan_and_fix(job.file_path.as_posix())
        job.copyright_status = status
        if status == "failed":
            raise RuntimeError("Copyright scan failed; upload skipped")
        job.file_path = Path(fixed_path)
        return job

    def _resolve_schedule(self, target: UploadTarget) -> Optional[str]:
        if target.mode in {"LOCAL_SCHEDULE", "NATIVE_SCHEDULE"} and target.scheduled_at:
            return target.scheduled_at.isoformat()
        return None

    def _dispatch_upload(self, job: UploadJob, target: UploadTarget, schedule: Optional[str]) -> str:
        if target.platform in ("youtube", "youtube_long", "youtube_shorts"):
            return upload_video(job.file_path, job.title, job.description, schedule)
        if target.platform in ("facebook", "instagram"):
            return upload_reel(job.file_path, job.title, job.description, schedule)
        if target.platform == "tiktok":
            return upload_tiktok(job.file_path, job.title, job.description, schedule)
        raise ValueError(f"Unsupported platform: {target.platform}")

    def _compute_fingerprints(self, job: UploadJob):
        base = job.file_path.resolve().as_posix()
        for target in job.targets:
            sched_str = target.scheduled_at.isoformat() if target.scheduled_at else "immediate"
            target.fingerprint = f"{base}|{target.platform}|{target.account_id}|{sched_str}|{job.title}"

    def _validate_job(self, job: UploadJob):
        for target in job.targets:
            if target.scheduled_at and target.scheduled_at.tzinfo is None:
                target.scheduled_at = target.scheduled_at.replace(tzinfo=ZoneInfo("Europe/Warsaw"))

    def _should_skip_target(self, target: UploadTarget) -> bool:
        if target.state == "UPLOADING":
            return True
        if target.result_id and target.state in {"DONE", "PUBLISHED"}:
            return True
        return False

    @staticmethod
    def is_target_due(target: UploadTarget, now: datetime) -> bool:
        if target.state not in {"PENDING", "FAILED"}:
            return False
        if target.state == "FAILED" and target.next_retry_at is None:
            return False
        due_time = target.next_retry_at or target.scheduled_at or now
        return due_time <= now

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status is not None:
            if status == 429 or 500 <= status <= 599:
                return True
            if status in {400, 401, 403}:
                return False
        message = str(exc).lower()
        retryable_markers = ["timeout", "timed out", "connection", "temporarily unavailable", "429"]
        non_retryable_markers = ["file not found", "invalid", "bad request", "unauthorized"]
        if any(marker in message for marker in non_retryable_markers):
            return False
        if any(marker in message for marker in retryable_markers):
            return True
        return False

    def _notify(self, event: str, job: UploadJob | None, target: UploadTarget | None = None):
        for cb in self.callbacks:
            try:
                cb(event=event, job=job, target=target)
            except Exception:
                logger.exception("Callback error")
