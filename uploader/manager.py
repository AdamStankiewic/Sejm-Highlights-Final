"""Upload manager with background queue."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
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
        if "FAILED" in states:
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
    def __init__(self, protector=None):
        self.queue: Queue[UploadJob] = Queue()
        self.worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.callbacks: List[Callable[[str, UploadJob, UploadTarget | None], None]] = []
        self.protector = protector

    def add_callback(self, cb: Callable[[str, UploadJob, UploadTarget | None], None]):
        self.callbacks.append(cb)

    def enqueue(self, job: UploadJob):
        logger.info("Enqueue upload: %s", job.file_path)
        self.queue.put(job)
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
            try:
                job: UploadJob = self.queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                job.state = "UPLOADING"
                self._notify("job_update", job)
                self._process_job(job)
                job.state = "DONE"
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Upload failed for %s: %s", job.file_path, exc)
                job.state = "FAILED"
            self._notify("job_update", job)
            self.queue.task_done()

    def _process_job(self, job: UploadJob):
        if job.original_path is None:
            job.original_path = job.file_path
        if self.protector:
            fixed_path, status = self.protector.scan_and_fix(job.file_path.as_posix())
            job.copyright_status = status
            if status == "failed":
                raise RuntimeError("Copyright scan failed; upload skipped")
            job.file_path = Path(fixed_path)
        for target in job.targets:
            target.state = "UPLOADING"
            job.state = job.aggregate_state
            self._notify("target_update", job, target)
            try:
                schedule = self._resolve_schedule(target)
                target.result_id = self._dispatch_upload(job, target, schedule)
                target.state = "DONE"
                target.last_error = None
            except Exception as exc:
                target.state = "FAILED"
                target.last_error = str(exc)
                job.state = job.aggregate_state
                self._notify("target_update", job, target)
                raise
            job.state = job.aggregate_state
            self._notify("target_update", job, target)

    def _resolve_schedule(self, target: UploadTarget) -> Optional[str]:
        if target.mode == "LOCAL_SCHEDULE" and target.scheduled_at:
            return target.scheduled_at.isoformat()
        if target.mode == "NATIVE_SCHEDULE" and target.scheduled_at:
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

    def _notify(self, event: str, job: UploadJob, target: UploadTarget | None = None):
        for cb in self.callbacks:
            try:
                cb(event=event, job=job, target=target)
            except Exception:
                logger.exception("Callback error")
