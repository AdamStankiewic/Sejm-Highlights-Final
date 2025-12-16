import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.manager import UploadManager
from uploader.models import UploadJob, UploadTarget
from uploader.store import UploadStore


def make_job(file_path: Path, targets: list[UploadTarget]) -> UploadJob:
    return UploadJob(
        file_path=file_path,
        title="Test",
        description="Desc",
        targets=targets,
        tags=["tag1", "tag2"],
        thumbnail_path=file_path.with_suffix(".jpg"),
    )


def test_store_persists_and_loads_jobs(tmp_path: Path):
    db_path = tmp_path / "uploader.db"
    store = UploadStore(db_path)

    file_path = tmp_path / "video.mp4"
    file_path.write_text("data")
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")),
        result_id="vid1",
        result_url="https://example.com/watch?v=vid1",
    )
    job = make_job(file_path, [target])

    store.upsert_job(job)
    store.upsert_target(job.job_id, target)

    loaded = store.load_jobs_with_targets()
    assert len(loaded) == 1
    loaded_job = loaded[0]
    assert loaded_job.file_path == file_path
    assert loaded_job.created_at.tzinfo is not None
    assert loaded_job.tags == ["tag1", "tag2"]
    assert loaded_job.thumbnail_path == file_path.with_suffix(".jpg")
    assert len(loaded_job.targets) == 1
    loaded_target = loaded_job.targets[0]
    assert loaded_target.platform == target.platform
    assert loaded_target.scheduled_at.tzinfo is not None
    assert loaded_target.result_id == "vid1"
    assert loaded_target.result_url == "https://example.com/watch?v=vid1"


def test_update_target_state_is_persisted(tmp_path: Path):
    db_path = tmp_path / "uploader.db"
    store = UploadStore(db_path)

    file_path = tmp_path / "video.mp4"
    file_path.write_text("data")
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) - timedelta(minutes=1),
    )
    job = make_job(file_path, [target])
    store.upsert_job(job)
    store.upsert_target(job.job_id, target)

    store.update_target_state(
        target.target_id,
        "FAILED",
        last_error="boom",
        retry_count=1,
        result_url="https://example.com/boom",
    )

    loaded_target = store.load_jobs_with_targets()[0].targets[0]
    assert loaded_target.state == "FAILED"
    assert loaded_target.last_error == "boom"
    assert loaded_target.retry_count == 1
    assert loaded_target.result_url == "https://example.com/boom"


def test_restart_sets_uploading_to_failed_and_schedules_retry(tmp_path: Path):
    db_path = tmp_path / "uploader.db"
    store = UploadStore(db_path)

    file_path = tmp_path / "video.mp4"
    file_path.write_text("data")
    target = UploadTarget(
        platform="youtube",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) - timedelta(minutes=1),
        state="UPLOADING",
    )
    job = make_job(file_path, [target])
    store.upsert_job(job)
    store.upsert_target(job.job_id, target)

    manager = UploadManager(store=store, tick_seconds=0.2)
    manager._dispatch_upload = lambda *_, **__: "ok"  # type: ignore
    manager.start()
    manager.stop()

    reloaded_target = store.load_jobs_with_targets()[0].targets[0]
    assert reloaded_target.state == "FAILED"
    assert reloaded_target.retry_count == 1
    assert reloaded_target.next_retry_at is not None
    assert reloaded_target.next_retry_at > datetime.now(tz=ZoneInfo("UTC"))
