from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo


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
    target_id: str = ""


@dataclass
class UploadJob:
    file_path: Path
    title: str
    description: str
    targets: List[UploadTarget]
    job_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=ZoneInfo("UTC")))
    copyright_status: str = "pending"
    original_path: Path | None = None
    state: Literal["PENDING", "UPLOADING", "DONE", "FAILED"] = "PENDING"
    kind: str | None = None

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
