from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.models import UploadJob, UploadTarget
from uploader import youtube


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    path.write_text("data")
    return path


def test_native_schedule_sets_publish_at(monkeypatch: pytest.MonkeyPatch, video_file: Path):
    captured: dict = {}

    def fake_upload_video(_youtube, file_path, *, title, description, tags, category_id, privacy_status, publish_at_iso):
        captured.update(
            {
                "file_path": file_path,
                "title": title,
                "description": description,
                "tags": tags,
                "category_id": category_id,
                "privacy_status": privacy_status,
                "publish_at_iso": publish_at_iso,
            }
        )
        return "vid123"

    monkeypatch.setattr(youtube, "upload_video", fake_upload_video)

    scheduled_at = datetime.now(tz=ZoneInfo("UTC")) + timedelta(hours=1)
    target = UploadTarget(
        platform="youtube",
        account_id="channel_main",
        scheduled_at=scheduled_at,
        mode="NATIVE_SCHEDULE",
    )
    job = UploadJob(
        file_path=video_file,
        title="Native Publish",
        description="Some desc",
        targets=[target],
        kind="LONG",
    )

    video_id = youtube.upload_target(
        job,
        target,
        accounts_config={"youtube": {"channel_main": {"credential_profile": "yt_main", "default_privacy": "unlisted", "category_id": 22}}},
        youtube_client=object(),
    )

    assert video_id == "vid123"
    assert captured["privacy_status"] == "private"
    assert captured["publish_at_iso"] == scheduled_at.astimezone(ZoneInfo("UTC")).isoformat()
    assert captured["category_id"] == "22"


def test_shorts_metadata_appended(monkeypatch: pytest.MonkeyPatch, video_file: Path):
    captured: dict = {}

    def fake_upload_video(_youtube, file_path, *, title, description, tags, category_id, privacy_status, publish_at_iso):
        captured.update({"description": description, "tags": tags or []})
        return "vid999"

    monkeypatch.setattr(youtube, "upload_video", fake_upload_video)

    target = UploadTarget(
        platform="youtube_shorts",
        account_id="default",
        scheduled_at=datetime.now(tz=ZoneInfo("UTC")) - timedelta(minutes=1),
    )
    job = UploadJob(
        file_path=video_file,
        title="Short",
        description="Short description",
        targets=[target],
        kind="SHORT",
        tags=["custom"],
    )

    youtube.upload_target(
        job,
        target,
        accounts_config={"youtube": {"default": {"credential_profile": "default", "tags": ["base"]}}},
        youtube_client=object(),
    )

    assert "#shorts" in captured["description"].lower()
    assert "shorts" in {t.lower() for t in captured["tags"]}
    assert "custom" in captured["tags"]
    assert "base" in captured["tags"]
