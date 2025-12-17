import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.meta import ManualRequiredUploadError, NonRetryableUploadError, RetryableUploadError
from uploader.models import UploadJob, UploadTarget
from uploader.tiktok import TikTokClient, upload_tiktok_target, upload_tiktok_video


class _FakeClient(TikTokClient):
    def __init__(self, responses):
        super().__init__("token", base_url="https://example.com")
        self._responses = list(responses)
        self.calls = []

    def api_post(self, path: str, *, data: dict | None = None, files=None):
        self.calls.append((path, data, files is not None))
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _job_and_target(tmp_path: Path):
    video = tmp_path / "video.mp4"
    video.write_text("video")
    job = UploadJob(file_path=video, title="Title", description="Desc", targets=[])
    target = UploadTarget(platform="tiktok", account_id="tt_main")
    job.targets.append(target)
    return job, target


def test_missing_token_triggers_manual_required(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"tiktok": {"tt_main": {"mode": "OFFICIAL_API", "access_token_env": "TT_TOKEN"}}}
    monkeypatch.delenv("TT_TOKEN", raising=False)
    with pytest.raises(ManualRequiredUploadError):
        upload_tiktok_target(job, target, accounts_config=accounts)


def test_retryable_error_bubbles(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"tiktok": {"tt_main": {"mode": "OFFICIAL_API", "access_token_env": "TT_TOKEN"}}}
    monkeypatch.setenv("TT_TOKEN", "secret")
    responses = [RetryableUploadError("rate limited", status_code=429)]

    def factory(_token):
        return _FakeClient(responses)

    with pytest.raises(RetryableUploadError):
        upload_tiktok_target(job, target, accounts_config=accounts, client_factory=factory)


def test_manual_required_when_not_supported(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"tiktok": {"tt_main": {"mode": "OFFICIAL_API", "access_token_env": "TT_TOKEN"}}}
    monkeypatch.setenv("TT_TOKEN", "secret")
    responses = [{"data": {"message": "not supported for this account"}}]

    def factory(_token):
        return _FakeClient(responses)

    with pytest.raises(ManualRequiredUploadError):
        upload_tiktok_target(job, target, accounts_config=accounts, client_factory=factory)


def test_success_returns_video_id(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"tiktok": {"tt_main": {"mode": "OFFICIAL_API", "access_token_env": "TT_TOKEN"}}}
    monkeypatch.setenv("TT_TOKEN", "secret")
    responses = [{"data": {"video_id": "vid123"}}]

    def factory(_token):
        return _FakeClient(responses)

    video_id = upload_tiktok_target(job, target, accounts_config=accounts, client_factory=factory)
    assert video_id == "vid123"


def test_upload_video_handles_missing_id(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("video")
    account = type("Account", (), {"advertiser_id": None})
    client = _FakeClient([{"data": {"message": "something"}}])
    with pytest.raises(NonRetryableUploadError):
        upload_tiktok_video(video, "caption", account, client)

