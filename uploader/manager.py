"""Upload manager with background queue."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue, Empty
from typing import Callable, Dict, List, Optional

from .youtube import upload_video
from .meta import upload_reel
from .tiktok import upload_tiktok

logger = logging.getLogger(__name__)


@dataclass
class UploadJob:
    file_path: Path
    title: str
    description: str
    platforms: Dict[str, bool]
    schedule: Optional[str] = None
    status: str = "Waiting"
    result_ids: Dict[str, str] = field(default_factory=dict)


class UploadManager:
    def __init__(self):
        self.queue: Queue[UploadJob] = Queue()
        self.worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.callbacks: List[Callable[[UploadJob], None]] = []

    def add_callback(self, cb: Callable[[UploadJob], None]):
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
                job.status = "Uploading"
                self._notify(job)
                self._process_job(job)
                job.status = "Done"
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Upload failed for %s: %s", job.file_path, exc)
                job.status = "Failed"
            self._notify(job)
            self.queue.task_done()

    def _process_job(self, job: UploadJob):
        if job.platforms.get("youtube_long") or job.platforms.get("youtube_shorts"):
            job.result_ids["youtube"] = upload_video(job.file_path, job.title, job.description, job.schedule)
        if job.platforms.get("facebook") or job.platforms.get("instagram"):
            job.result_ids["meta"] = upload_reel(job.file_path, job.title, job.description, job.schedule)
        if job.platforms.get("tiktok"):
            job.result_ids["tiktok"] = upload_tiktok(job.file_path, job.title, job.description, job.schedule)

    def _notify(self, job: UploadJob):
        for cb in self.callbacks:
            try:
                cb(job)
            except Exception:
                logger.exception("Callback error")
