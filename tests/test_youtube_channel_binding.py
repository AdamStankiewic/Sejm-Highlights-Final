from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.models import UploadJob, UploadTarget
from uploader import youtube


class FakeYouTube:
    def __init__(self, channel_id: str):
        self._channel_id = channel_id

    def channels(self):
        return self

    def list(self, part: str, mine: bool):  # pragma: no cover - interface completeness
        return self

    def execute(self):
        return {"items": [{"id": self._channel_id}]}


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    path = tmp_path / "video.mp4"
    path.write_text("data")
    return path


def test_channel_binding_success(monkeypatch: pytest.MonkeyPatch, video_file: Path):
    monkeypatch.setattr(youtube, "upload_video", lambda *args, **kwargs: "vid-ok")
    account_cfg = {
        "youtube": {
            "channel_main": {
                "credential_profile": "yt_main",
                "expected_channel_id": "UC123",
            }
        }
    }
    job = UploadJob(
        file_path=video_file,
        title="Test",
        description="desc",
        targets=[
            UploadTarget(
                platform="youtube",
                account_id="channel_main",
                scheduled_at=youtube.datetime.now(tz=ZoneInfo("UTC")),
                mode="LOCAL_SCHEDULE",
            )
        ],
    )

    video_id = youtube.upload_target(job, job.targets[0], accounts_config=account_cfg, youtube_client=FakeYouTube("UC123"))

    assert video_id == "vid-ok"


def test_channel_binding_mismatch(monkeypatch: pytest.MonkeyPatch, video_file: Path):
    monkeypatch.setattr(youtube, "upload_video", lambda *args, **kwargs: "should-not-upload")
    account_cfg = {
        "youtube": {
            "channel_main": {
                "credential_profile": "yt_main",
                "expected_channel_id": "UC_expected",
            }
        }
    }
    job = UploadJob(
        file_path=video_file,
        title="Test",
        description="desc",
        targets=[
            UploadTarget(
                platform="youtube",
                account_id="channel_main",
                scheduled_at=youtube.datetime.now(tz=ZoneInfo("UTC")),
                mode="LOCAL_SCHEDULE",
            )
        ],
    )

    with pytest.raises(youtube.YouTubeUploadError) as excinfo:
        youtube.upload_target(job, job.targets[0], accounts_config=account_cfg, youtube_client=FakeYouTube("UC_other"))

    assert "expected=UC_expected" in str(excinfo.value)
    assert excinfo.value.status_code == 400


def test_missing_account_configuration(monkeypatch: pytest.MonkeyPatch, video_file: Path):
    monkeypatch.setattr(youtube, "upload_video", lambda *args, **kwargs: "should-not-upload")
    job = UploadJob(
        file_path=video_file,
        title="Test",
        description="desc",
        targets=[
            UploadTarget(
                platform="youtube",
                account_id="unknown",  # not in config
                scheduled_at=youtube.datetime.now(tz=ZoneInfo("UTC")),
                mode="LOCAL_SCHEDULE",
            )
        ],
    )

    with pytest.raises(youtube.YouTubeUploadError) as excinfo:
        youtube.upload_target(job, job.targets[0], accounts_config={"youtube": {}}, youtube_client=FakeYouTube("UC123"))

    assert "Unknown YouTube account_id" in str(excinfo.value)
    assert excinfo.value.status_code == 400
