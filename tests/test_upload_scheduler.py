import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from uploader.manager import UploadJob, UploadManager, UploadTarget


class DummyError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@pytest.fixture
def file_path(tmp_path: Path) -> Path:
    test_file = tmp_path / "video.mp4"
    test_file.write_text("dummy")
    return test_file


def make_job(file_path: Path, target: UploadTarget) -> UploadJob:
    return UploadJob(
        file_path=file_path,
        title="Test",
        description="Desc",
        targets=[target],
    )


def wait_for(predicate, timeout: float = 2.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_future_target_does_not_start(file_path: Path):
    manager = UploadManager(tick_seconds=0.1)
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) + timedelta(seconds=5),
    )
    job = make_job(file_path, target)

    called = False

    def _dispatch(*_args, **_kwargs):
        nonlocal called
        called = True
        return "result"

    manager._dispatch_upload = _dispatch  # type: ignore
    manager.enqueue(job)
    time.sleep(0.3)
    manager.stop()

    assert not called
    assert target.state == "PENDING"


def test_due_target_starts(file_path: Path):
    manager = UploadManager(tick_seconds=0.1)
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) - timedelta(seconds=1),
    )
    job = make_job(file_path, target)

    manager._dispatch_upload = lambda *_args, **_kwargs: "ok"  # type: ignore
    manager.enqueue(job)

    assert wait_for(lambda: target.state == "DONE"), "Target should finish"
    manager.stop()
    assert target.result_id == "ok"


def test_retryable_error_schedules_retry(file_path: Path):
    manager = UploadManager(tick_seconds=0.1)
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) - timedelta(seconds=1),
    )
    job = make_job(file_path, target)

    def _dispatch(*_args, **_kwargs):
        raise DummyError("Too many requests", status_code=429)

    manager._dispatch_upload = _dispatch  # type: ignore
    manager.enqueue(job)

    assert wait_for(lambda: target.retry_count == 1), "Retry count should increment"
    manager.stop()
    assert target.state == "FAILED"
    assert target.next_retry_at is not None


def test_non_retryable_error_fails(file_path: Path):
    manager = UploadManager(tick_seconds=0.1)
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) - timedelta(seconds=1),
    )
    job = make_job(file_path, target)

    def _dispatch(*_args, **_kwargs):
        raise DummyError("Bad request", status_code=400)

    manager._dispatch_upload = _dispatch  # type: ignore
    manager.enqueue(job)

    assert wait_for(lambda: target.state == "FAILED"), "Target should fail"
    manager.stop()
    assert target.next_retry_at is None
    assert target.retry_count == 0


def test_idempotent_skip_completed_target(file_path: Path):
    manager = UploadManager(tick_seconds=0.1)
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) - timedelta(seconds=1),
        state="DONE",
        result_id="existing",
    )
    job = make_job(file_path, target)

    called = False

    def _dispatch(*_args, **_kwargs):
        nonlocal called
        called = True
        return "new"

    manager._dispatch_upload = _dispatch  # type: ignore
    manager.enqueue(job)
    time.sleep(0.3)
    manager.stop()

    assert not called
    assert target.result_id == "existing"
